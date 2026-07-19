"""Quick test script to verify OCR output on a receipt image."""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from ocr import ReceiptOCR

uploads_dir = os.path.join(os.path.dirname(__file__), 'uploads')
files = sorted(os.listdir(uploads_dir), reverse=True)
test_image = os.path.join(uploads_dir, files[0])
print(f"Testing: {test_image}")
print("=" * 60)

ocr = ReceiptOCR()
result = ocr.scan(test_image)

print(f"\n  Store: {result['store_name']}")
print(f"  Date:  {result['date']}")
print(f"  Total: GBP {result['total_amount']:.2f}")
print(f"  Savings: GBP {result.get('total_savings', 0):.2f}")

print(f"\n  Items ({len(result['items'])}):")
for item in result['items']:
    print(f"    - {item['name']}: GBP {item['price']:.2f}")

discounts = result.get('discounts', [])
print(f"\n  Discounts ({len(discounts)}):")
for d in discounts:
    print(f"    - {d['name']}: GBP {d['price']:.2f}")

# Expected from the receipt photo:
#   TOILET ROLL / KITCHEN ROLL  8.50
#   CLOTHS                      3.68
#   SCOURERS                    2.98
#   CLEANING                    1.50
#   WASH UP                     1.68
#   WASH UP                     1.27
#   BIN LINER                   2.54
#   Colleague Disc             -3.51
#   Total:                     19.91
