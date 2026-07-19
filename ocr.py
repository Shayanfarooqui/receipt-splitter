"""
OCR module — Tesseract-based receipt scanning and text parsing.
Tuned for UK supermarket receipts (Tesco, Asda, Sainsbury's, Aldi, Lidl, etc.)

Key design choices:
- No binarization (destroys price data on receipt photos)
- Heavy contrast + sharpness for best text clarity
- PSM 6 (assume uniform block of text) works best for receipts
- Fuzzy price matching to handle minor OCR garbling
- Post-savings total selection
"""

import re
import os
from datetime import datetime
import pytesseract
from PIL import Image, ImageFilter, ImageEnhance, ImageOps

# Configure Tesseract path for Windows
TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


class ReceiptOCR:
    def __init__(self):
        self.skip_keywords = [
            'subtotal', 'sub total', 'sub-total',
            'vat', 'tax summary', 'tax total',
            'change due', 'change',
            'cash', 'card', 'visa', 'mastercard', 'amex', 'debit', 'credit',
            'balance due', 'balance', 'payment', 'paid', 'tendered', 'tend',
            'amount due', 'loyalty', 'clubcard', 'nectar', 'points',
            'thank you', 'thanks', 'served by', 'cashier',
            'tel', 'telephone', 'phone', 'vat no', 'vat reg',
            'www.', 'http', '.com', '.co.uk',
            'items sold', 'no. items', 'rate', 'net',
            'delivery', 'collection', 'shop online',
            'stores ltd', 'store ltd', 'storehelp',
            'manager', 'stevenage', 'arafat',
        ]

        self.total_keywords = ['total', 'grand total', 'total to pay', 'to pay',
                               'amount due', 'balance due', 'total due']

        self.discount_keywords = [
            'discount', 'disc', 'dise', 'disg',  # OCR variants of 'disc'
            'colleague',  # Asda colleague discount
            'savings', 'saving', 'save', 'saved',
            'offer', 'promo', 'promotion', 'reduced', 'reduction',
            'multibuy', 'multi-buy', 'meal deal', 'price cut',
            'clubcard price', 'nectar price', 'money off', 'coupon', 'voucher',
            'rewards',
        ]

    def scan(self, image_path):
        """Scan a receipt image and extract structured data."""
        img = self._preprocess(image_path)

        # PSM 6 = assume a single uniform block of text — best for receipts
        custom_config = r'--oem 3 --psm 6'
        raw_text = pytesseract.image_to_string(img, lang='eng', config=custom_config)

        parsed = self._parse_receipt(raw_text)
        parsed['raw_text'] = raw_text
        return parsed

    def _preprocess(self, image_path):
        """
        Pre-process receipt image for best OCR accuracy.
        NO binarization — it destroys price data on photos of receipts.
        """
        img = Image.open(image_path)

        # Auto-orient (phone photos are often rotated)
        img = ImageOps.exif_transpose(img)

        # Convert to grayscale
        img = img.convert('L')

        # Auto-contrast to normalise brightness
        img = ImageOps.autocontrast(img, cutoff=1)

        # Strong contrast boost
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.0)

        # Strong sharpness boost
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(2.0)

        # Scale up small images — Tesseract needs decent resolution
        width, height = img.size
        if width < 1200:
            ratio = 1200 / width
            img = img.resize((int(width * ratio), int(height * ratio)), Image.LANCZOS)

        return img

    def _parse_receipt(self, text):
        """Parse OCR text into structured receipt data."""
        lines = text.strip().split('\n')
        lines = [l.strip() for l in lines if l.strip()]
        lines = [self._clean_line(l) for l in lines]
        lines = [l for l in lines if l]

        store_name = self._extract_store_name(lines)
        date = self._extract_date(text)
        items, discounts = self._extract_items_and_discounts(lines)
        total = self._extract_total(lines, items, discounts)
        total_savings = round(sum(abs(d['price']) for d in discounts), 2)

        return {
            'store_name': store_name,
            'date': date,
            'items': items,
            'discounts': discounts,
            'total_amount': total,
            'total_savings': total_savings
        }

    def _clean_line(self, line):
        """Clean common OCR artefacts."""
        line = line.replace('|', 'l')
        line = line.replace('}{', 'H')
        if re.match(r'^[\-=\*_~\.]{3,}$', line):
            return ''
        return line

    # ─── Price extraction ──────────────────────────────────────────

    def _extract_price_from_line(self, line):
        """
        Extract a price from a line. Returns (price_float, is_negative) or (None, False).
        Handles: £8.50, £3.68, 1.2?, {1.68, etc.
        """
        is_negative = False

        # Check for negative markers in the price portion (right side of line)
        mid = len(line) // 3  # prices are usually in the right third
        right_portion = line[mid:]
        if '-' in right_portion or '~' in right_portion:
            is_negative = True

        # Pattern 1: Clean £X.XX
        match = re.search(r'£(\d+\.\d{2})\b', line)
        if match:
            return float(match.group(1)), is_negative

        # Pattern 2: £ with space before digits: "£ 2.98"  or  "£ 1.50"
        match = re.search(r'£\s+(\d+\.\d{2})\b', line)
        if match:
            return float(match.group(1)), is_negative

        # Pattern 3: OCR garbled £ sign as { or ( or similar, followed by clean price
        # e.g., "{1.68" or "(1.68"
        match = re.search(r'[\{\(\[](\d+\.\d{2})\b', line)
        if match:
            return float(match.group(1)), is_negative

        # Pattern 4: Price with space in decimal: "£3. 68" or "£ 2. 98"
        match = re.search(r'£\s*(\d+)\s*\.\s*(\d{2})\b', line)
        if match:
            return float(f"{match.group(1)}.{match.group(2)}"), is_negative

        # Pattern 5: Clean number at end of line: "1.27" or "2.54"
        match = re.search(r'\b(\d+\.\d{2})\s*$', line)
        if match:
            return float(match.group(1)), is_negative

        # Pattern 6: Price with ? replacing a digit: "1.2?" → assume last digit
        match = re.search(r'(\d+)\.(\d)[?\*xX]\s*$', line)
        if match:
            # Can't know the exact digit, approximate with 0
            return float(f"{match.group(1)}.{match.group(2)}0"), is_negative

        # Pattern 7: OCR read £ as 'e' or 't' + price
        match = re.search(r'[et](\d+\.\d{2})\b', line)
        if match:
            return float(match.group(1)), is_negative

        # Pattern 8: Number without decimal but with space pattern: "£8 50"
        match = re.search(r'£(\d+)\s+(\d{2})\s*$', line)
        if match:
            return float(f"{match.group(1)}.{match.group(2)}"), is_negative

        return None, False

    def _extract_item_name(self, line):
        """Extract item name from a line (text before the price area)."""
        # Find where the price portion starts — look for gap + price chars
        match = re.search(r'^(.+?)\s{2,}[\£\$\d\-~\{\(\[]', line)
        if match:
            name = match.group(1).strip()
        else:
            # Try single space before £
            match = re.search(r'^(.+?)\s+£', line)
            if match:
                name = match.group(1).strip()
            else:
                # Take everything before the last cluster of digits/symbols
                match = re.search(r'^(.+?)\s+[\d\£]', line)
                if match:
                    name = match.group(1).strip()
                else:
                    name = line.strip()

        # Clean the name
        name = re.sub(r'[^A-Za-z0-9\s&\'/\-\(\)]', '', name).strip()
        name = re.sub(r'\s+', ' ', name)
        # Remove trailing dots from OCR
        name = name.rstrip('.')
        return name

    # ─── Store name ────────────────────────────────────────────────

    def _extract_store_name(self, lines):
        """Extract store name."""
        known_stores = [
            'tesco', 'asda', 'sainsbury', 'sainsburys', "sainsbury's",
            'morrisons', 'aldi', 'lidl', 'waitrose', 'co-op', 'coop',
            'iceland', 'marks & spencer', 'm&s', 'spar', 'nisa',
            'costcutter', 'londis', 'budgens', 'farmfoods', 'heron',
            'home bargains', 'b&m', 'poundland', 'wilko',
        ]

        for line in lines[:10]:
            line_lower = line.lower().strip()
            for store in known_stores:
                if store in line_lower:
                    return store.title().replace("'S", "'s")

        for line in lines[:5]:
            cleaned = re.sub(r'[^A-Za-z\s&\']', '', line).strip()
            if len(cleaned) >= 3 and cleaned == cleaned.upper():
                return cleaned.title()

        return 'Unknown Store'

    # ─── Date ──────────────────────────────────────────────────────

    def _extract_date(self, text):
        """Extract date from receipt text."""
        patterns = [
            r'(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
            r'(\d{4}[/\-\.]\d{2}[/\-\.]\d{2})',
            r'(\d{2}[/\-\.]\d{2}[/\-\.]\d{2})',
            r'(\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[\s,]*\d{2,4})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return self._normalise_date(match.group(1))
        return datetime.now().strftime('%Y-%m-%d')

    def _normalise_date(self, date_str):
        """Convert various date formats to YYYY-MM-DD."""
        date_str = re.sub(r'[,]', '', date_str).strip()
        date_str = re.sub(r'\s+', ' ', date_str)
        formats = [
            '%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y',
            '%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d',
            '%d/%m/%y', '%d-%m-%y', '%d.%m.%y',
            '%d %B %Y', '%d %b %Y', '%d %B %y', '%d %b %y',
        ]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
            except ValueError:
                continue
        return date_str

    # ─── Items and discounts ───────────────────────────────────────

    def _extract_items_and_discounts(self, lines):
        """Extract product items and discounts from receipt lines."""
        items = []
        discounts = []

        # Find the items section boundaries
        items_start = self._find_items_start(lines)
        items_end = self._find_items_end(lines, items_start)

        for i in range(items_start, items_end):
            line = lines[i]
            line_lower = line.lower().strip()

            if len(line) < 3:
                continue

            # Skip non-item lines
            if self._is_skip_line(line_lower):
                continue

            # Skip total lines
            if self._is_total_line(line_lower):
                continue

            # Try to extract a price
            price, is_negative = self._extract_price_from_line(line)

            if price is not None and price > 0:
                name = self._extract_item_name(line)

                if name and len(name) >= 2:
                    is_disc = self._is_discount_line(line_lower) or is_negative
                    if is_disc:
                        discounts.append({'name': name, 'price': -abs(price)})
                    else:
                        items.append({'name': name, 'price': price})
            else:
                # No price found — likely an item whose price OCR couldn't read.
                # Add it with price 0 so the user can fill it in.
                name = re.sub(r'[^A-Za-z0-9\s&\'/\-]', '', line).strip()
                if name and len(name) >= 3 and name.upper() == name:
                    items.append({'name': name, 'price': 0.0})

        return items, discounts

    def _find_items_start(self, lines):
        """Find where the items section starts (after header/address)."""
        start = 0
        for i, line in enumerate(lines[:15]):
            ll = line.lower()
            # Items start AFTER these header markers
            if any(kw in ll for kw in ['st.', 'tr.', 'te.', 'storehelp', 'op.']):
                start = max(start, i + 1)
            if 'stores ltd' in ll or 'store ltd' in ll:
                start = max(start, i + 1)
            if '.com' in ll:
                start = max(start, i + 1)
        return start

    def _find_items_end(self, lines, items_start):
        """Find where the items section ends (first TOTAL line after items)."""
        for i in range(items_start, len(lines)):
            ll = lines[i].lower().strip()
            # Stop at first TOTAL line (skip "total savings")
            if re.search(r'\btotal\s*:', ll) and 'saving' not in ll and 'tax' not in ll:
                return i
        return len(lines)

    def _is_skip_line(self, line_lower):
        """Check if a line should be skipped."""
        for kw in self.skip_keywords:
            if kw in line_lower:
                return True
        alpha = sum(1 for c in line_lower if c.isalpha())
        if alpha < 2:
            return True
        return False

    def _is_total_line(self, line_lower):
        """Check if this is a TOTAL line."""
        return bool(re.search(r'\btotal\b', line_lower))

    def _is_discount_line(self, line_lower):
        """Check if this is a discount/savings line."""
        for kw in self.discount_keywords:
            if kw in line_lower:
                return True
        return False

    # ─── Total ─────────────────────────────────────────────────────

    def _extract_total(self, lines, items, discounts):
        """
        Extract the FINAL total (the one AFTER 'total savings').
        On UK receipts the order is:
          TOTAL: £23.42         (subtotal before savings)
          TOTAL SAVINGS: -£3.51
          TOTAL: £19.91         (final total ← we want THIS one)
        """
        totals = []
        savings_line_idx = -1

        for i, line in enumerate(lines):
            ll = line.lower().strip()

            # Find the savings line
            if 'saving' in ll:
                savings_line_idx = i
                continue

            # Find TOTAL lines (not tax total, not total savings)
            if re.search(r'\btotal\s*:', ll) and 'saving' not in ll and 'tax' not in ll:
                price, _ = self._extract_price_from_line(line)
                if price is not None and price > 0:
                    totals.append({'value': price, 'line_index': i})

        # If we found a savings line, prefer the total AFTER it
        if savings_line_idx >= 0:
            after_totals = [t for t in totals if t['line_index'] > savings_line_idx]
            if after_totals:
                return after_totals[0]['value']

        # Otherwise, use the last total
        if totals:
            return totals[-1]['value']

        # Fallback: sum items minus discounts
        if items:
            item_sum = sum(it['price'] for it in items)
            disc_sum = sum(abs(d['price']) for d in discounts)
            return round(item_sum - disc_sum, 2)

        return 0.0
