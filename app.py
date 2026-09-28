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
from settle import compute_settlement

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
    total = sum(r['total_amount'] for r in receipts)
    members = len(db.get_all_users())
    per_person = total / members if members > 0 else total
    return render_template('index.html',
                           page='dashboard',
                           receipts=receipts,
                           total=total,
                           members=members,
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


@app.route('/settle')
def settle_page():
    """Settle expenses page."""
    settings = db.get_settings()
    return render_template('index.html', page='settle', settings=settings)


@app.route('/split')
def split_page():
    return redirect(url_for('settle_page'))


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

    uploaded_by = data.get('user_id')
    paid_by = data.get('paid_by')
    if not db.get_user_by_id(uploaded_by):
        return jsonify({'error': 'Please choose who is uploading'}), 400
    if not db.get_user_by_id(paid_by):
        return jsonify({'error': 'Please choose who paid'}), 400

    receipt_id = db.add_receipt(
        store_name=data.get('store_name', 'Unknown Store'),
        date=data.get('date', datetime.now().strftime('%Y-%m-%d')),
        items=data.get('items', []),
        total_amount=float(data.get('total_amount', 0)),
        image_path=data.get('image_path', ''),
        discounts=data.get('discounts', []),
        total_savings=float(data.get('total_savings', 0)),
        user_id=uploaded_by,
        paid_by=paid_by
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
        residents=len(db.get_all_users()) or 1,
        period_start=data.get('period_start', ''),
        period_end=data.get('period_end', '')
    )
    return jsonify({'success': True})


@app.route('/api/settle', methods=['GET'])
def calculate_settlement():
    """Work out shares, balances and who pays whom for the selected period."""
    period_start = request.args.get('start', '')
    period_end = request.args.get('end', '')
    receipts = db.get_receipts_in_period(period_start, period_end)
    result = compute_settlement(receipts, db.get_all_users())
    result.update({'period_start': period_start, 'period_end': period_end})
    return jsonify(result)


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
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    try:
        user_id = db.add_user(name)
        return jsonify({'success': True, 'id': user_id})
    except Exception as e:
        return jsonify({'error': f'Failed to add user: {str(e)}'}), 500


@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user who has no receipts."""
    if db.user_has_receipts(user_id):
        return jsonify({'error': 'This user has receipts, so they cannot be deleted'}), 400
    try:
        db.delete_user(user_id)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': f'Failed to delete user: {str(e)}'}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
