"""
Database layer — SQLite storage for receipts and settings.
"""

import os
import json
import sqlite3
from datetime import datetime


class ReceiptDB:
    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.path.join(os.path.dirname(__file__), 'receipts.db')
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        cursor = conn.cursor()

        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                store_name TEXT NOT NULL,
                date TEXT NOT NULL,
                items TEXT NOT NULL DEFAULT '[]',
                discounts TEXT NOT NULL DEFAULT '[]',
                total_amount REAL NOT NULL DEFAULT 0,
                total_savings REAL NOT NULL DEFAULT 0,
                image_path TEXT,
                user_id INTEGER,
                paid_by INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (paid_by) REFERENCES users(id)
            )
        ''')

        # Migrate: add discounts column if missing (for existing databases)
        try:
            cursor.execute('SELECT discounts FROM receipts LIMIT 1')
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE receipts ADD COLUMN discounts TEXT NOT NULL DEFAULT '[]'")
            cursor.execute("ALTER TABLE receipts ADD COLUMN total_savings REAL NOT NULL DEFAULT 0")

        # Migrate: add user_id column if missing
        try:
            cursor.execute('SELECT user_id FROM receipts LIMIT 1')
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE receipts ADD COLUMN user_id INTEGER")

        # Migrate: add paid_by column; older receipts were paid by whoever uploaded them
        try:
            cursor.execute('SELECT paid_by FROM receipts LIMIT 1')
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE receipts ADD COLUMN paid_by INTEGER")
            cursor.execute("UPDATE receipts SET paid_by = user_id")

        # Migrate: PINs are no longer used
        cols = [r['name'] for r in cursor.execute('PRAGMA table_info(users)')]
        if 'pin' in cols:
            cursor.execute('ALTER TABLE users DROP COLUMN pin')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                residents INTEGER NOT NULL DEFAULT 1,
                period_start TEXT,
                period_end TEXT
            )
        ''')

        # Insert default settings if not present
        cursor.execute('INSERT OR IGNORE INTO settings (id, residents) VALUES (1, 1)')

        # Migrate: admin password (hashed) lives in settings
        cols = [r['name'] for r in cursor.execute('PRAGMA table_info(settings)')]
        if 'admin_password_hash' not in cols:
            cursor.execute('ALTER TABLE settings ADD COLUMN admin_password_hash TEXT')

        conn.commit()
        conn.close()

    # ─── Receipts ────────────────────────────────────────────────────

    def add_receipt(self, store_name, date, items, total_amount, image_path='',
                    discounts=None, total_savings=0, user_id=None, paid_by=None):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO receipts (store_name, date, items, discounts, total_amount,
                                  total_savings, image_path, user_id, paid_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            store_name,
            date,
            json.dumps(items),
            json.dumps(discounts or []),
            total_amount,
            total_savings,
            image_path,
            user_id,
            paid_by,
            datetime.now().isoformat()
        ))
        receipt_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return receipt_id

    # Receipts with the uploader's and payer's names attached
    RECEIPT_SELECT = '''
        SELECT r.*, up.name AS uploaded_by_name, pb.name AS paid_by_name
        FROM receipts r
        LEFT JOIN users up ON up.id = r.user_id
        LEFT JOIN users pb ON pb.id = r.paid_by
    '''

    def get_all_receipts(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(self.RECEIPT_SELECT + ' ORDER BY r.date DESC, r.created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def get_receipt(self, receipt_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(self.RECEIPT_SELECT + ' WHERE r.id = ?', (receipt_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    def delete_receipt(self, receipt_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM receipts WHERE id = ?', (receipt_id,))
        conn.commit()
        conn.close()

    def get_receipts_in_period(self, start_date='', end_date=''):
        conn = self._get_conn()
        cursor = conn.cursor()

        where, params = [], []
        if start_date:
            where.append('r.date >= ?')
            params.append(start_date)
        if end_date:
            where.append('r.date <= ?')
            params.append(end_date)
        sql = self.RECEIPT_SELECT
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        cursor.execute(sql + ' ORDER BY r.date DESC', params)

        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def _row_to_dict(self, row):
        d = dict(row)
        d['items'] = json.loads(d.get('items', '[]'))
        d['discounts'] = json.loads(d.get('discounts', '[]'))
        d['total_savings'] = d.get('total_savings', 0)
        return d

    # ─── Settings ────────────────────────────────────────────────────

    def get_settings(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM settings WHERE id = 1')
        row = cursor.fetchone()
        conn.close()
        if not row:
            return {'id': 1, 'residents': 1, 'period_start': '', 'period_end': ''}
        settings = dict(row)
        settings.pop('admin_password_hash', None)
        return settings

    def update_settings(self, residents=1, period_start='', period_end=''):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE settings SET residents = ?, period_start = ?, period_end = ?
            WHERE id = 1
        ''', (residents, period_start, period_end))
        conn.commit()
        conn.close()

    def get_admin_password_hash(self):
        conn = self._get_conn()
        row = conn.execute('SELECT admin_password_hash FROM settings WHERE id = 1').fetchone()
        conn.close()
        return row['admin_password_hash'] if row else None

    def set_admin_password_hash(self, password_hash):
        conn = self._get_conn()
        conn.execute('UPDATE settings SET admin_password_hash = ? WHERE id = 1', (password_hash,))
        conn.commit()
        conn.close()

    # ─── Users ───────────────────────────────────────────────────

    def add_user(self, name):
        """Add a new user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO users (name, created_at) VALUES (?, ?)',
                       (name, datetime.now().isoformat()))
        user_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return user_id

    def get_all_users(self):
        """Get all users."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, created_at FROM users ORDER BY name')
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_user_by_id(self, user_id):
        """Get user details by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT id, name, created_at FROM users WHERE id = ?', (user_id,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def user_has_receipts(self, user_id):
        """True if the user uploaded or paid for any receipt."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM receipts WHERE user_id = ? OR paid_by = ? LIMIT 1',
                       (user_id, user_id))
        row = cursor.fetchone()
        conn.close()
        return row is not None

    def delete_user(self, user_id):
        """Delete a user."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        conn.close()
