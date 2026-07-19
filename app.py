"""
Receipt Splitter — Flask Application
Scan supermarket receipts, track expenses, and split costs among residents.
"""

import os
import json
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from werkzeug.utils import secure_filename
from db import ReceiptDB
from ocr import ReceiptOCR

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'bmp', 'tiff', 'webp'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = ReceiptDB()
ocr = ReceiptOCR()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ─── Pages ───────────────────────────────────────────────────────────

@app.route('/')
def index():
    """Dashboard / home page."""
    receipts = db.get_all_receipts()
    settings = db.get_settings()
    total = sum(r['total_amount'] for r in receipts)
    residents = settings.get('residents', 1)
    per_person = total / residents if residents > 0 else total
    return render_template('index.html',
                           page='dashboard',
                           receipts=receipts,
                           total=total,
                           residents=residents,
                           per_person=per_person)


@app.route('/upload', methods=['GET'])
def upload_page():
    """Receipt upload page."""
    return render_template('index.html', page='upload')


@app.route('/receipts')
def receipts_page():
    """All receipts list."""
    receipts = db.get_all_receipts()
    return render_template('index.html', page='receipts', receipts=receipts)


@app.route('/split')
def split_page():
    """Expense splitting page."""
    settings = db.get_settings()
    return render_template('index.html', page='split', settings=settings)


# ─── API Endpoints ───────────────────────────────────────────────────

@app.route('/api/scan', methods=['POST'])
def scan_receipt():
    """Upload and scan a receipt image."""
    if 'receipt' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['receipt']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Allowed: png, jpg, jpeg, bmp, tiff, webp'}), 400

    filename = secure_filename(file.filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], timestamp + filename)
    file.save(filepath)

    try:
        result = ocr.scan(filepath)
        return jsonify({
            'success': True,
            'data': result,
            'filepath': filepath
        })
    except Exception as e:
        return jsonify({'error': f'OCR failed: {str(e)}'}), 500


@app.route('/api/receipts', methods=['POST'])
def save_receipt():
    """Save a receipt to the database."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    receipt_id = db.add_receipt(
        store_name=data.get('store_name', 'Unknown Store'),
        date=data.get('date', datetime.now().strftime('%Y-%m-%d')),
        items=data.get('items', []),
        total_amount=float(data.get('total_amount', 0)),
        image_path=data.get('image_path', ''),
        discounts=data.get('discounts', []),
        total_savings=float(data.get('total_savings', 0))
    )
    return jsonify({'success': True, 'id': receipt_id})


@app.route('/api/receipts/<int:receipt_id>', methods=['DELETE'])
def delete_receipt(receipt_id):
    """Delete a receipt."""
    db.delete_receipt(receipt_id)
    return jsonify({'success': True})


@app.route('/api/settings', methods=['POST'])
def update_settings():
    """Update app settings (residents, period)."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    db.update_settings(
        residents=int(data.get('residents', 1)),
        period_start=data.get('period_start', ''),
        period_end=data.get('period_end', '')
    )
    return jsonify({'success': True})


@app.route('/api/split', methods=['GET'])
def calculate_split():
    """Calculate the expense split for the selected period."""
    period_start = request.args.get('start', '')
    period_end = request.args.get('end', '')
    settings = db.get_settings()
    residents = settings.get('residents', 1)

    receipts = db.get_receipts_in_period(period_start, period_end)
    total = sum(r['total_amount'] for r in receipts)
    per_person = total / residents if residents > 0 else total

    return jsonify({
        'total': round(total, 2),
        'residents': residents,
        'per_person': round(per_person, 2),
        'receipt_count': len(receipts),
        'period_start': period_start,
        'period_end': period_end,
        'receipts': receipts
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
