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


@app.route('/users')
def users_page():
    """User management page."""
    users = db.get_all_users()
    return render_template('index.html', page='users', users=users)


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
        total_savings=float(data.get('total_savings', 0)),
        user_id=data.get('user_id')
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


# ─── User Management API ────────────────────────────────────────

@app.route('/api/users', methods=['GET'])
def get_users():
    """Get all users."""
    users = db.get_all_users()
    return jsonify({'success': True, 'users': users})


@app.route('/api/users', methods=['POST'])
def add_user():
    """Add a new user."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    name = data.get('name', '').strip()
    pin = data.get('pin', '').strip()

    if not name:
        return jsonify({'error': 'Name is required'}), 400

    if not pin or len(pin) != 6 or not pin.isdigit():
        return jsonify({'error': 'PIN must be exactly 6 digits'}), 400

    try:
        user_id = db.add_user(name, pin)
        return jsonify({'success': True, 'id': user_id})
    except Exception as e:
        return jsonify({'error': f'Failed to add user: {str(e)}'}), 500


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user."""
    try:
        db.delete_user(user_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': f'Failed to delete user: {str(e)}'}), 500


@app.route('/api/users/<int:user_id>/pin', methods=['PUT'])
def update_user_pin(user_id):
    """Update a user's PIN."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    new_pin = data.get('pin', '').strip()

    if not new_pin or len(new_pin) != 6 or not new_pin.isdigit():
        return jsonify({'error': 'PIN must be exactly 6 digits'}), 400

    try:
        db.update_user_pin(user_id, new_pin)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': f'Failed to update PIN: {str(e)}'}), 500


@app.route('/api/users/verify', methods=['POST'])
def verify_user_pin():
    """Verify a user's PIN."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    user_id = data.get('user_id')
    pin = data.get('pin', '').strip()

    if not user_id or not pin:
        return jsonify({'error': 'User ID and PIN are required'}), 400

    is_valid = db.verify_pin(user_id, pin)
    if is_valid:
        user = db.get_user_by_id(user_id)
        return jsonify({'success': True, 'valid': True, 'user': user})
    else:
        return jsonify({'success': True, 'valid': False})


if __name__ == '__main__':
    app.run(debug=True, port=5000)
