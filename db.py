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
                created_at TEXT NOT NULL
            )
        ''')

        # Migrate: add discounts column if missing (for existing databases)
        try:
            cursor.execute('SELECT discounts FROM receipts LIMIT 1')
        except sqlite3.OperationalError:
            cursor.execute("ALTER TABLE receipts ADD COLUMN discounts TEXT NOT NULL DEFAULT '[]'")
            cursor.execute("ALTER TABLE receipts ADD COLUMN total_savings REAL NOT NULL DEFAULT 0")

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

        conn.commit()
        conn.close()

    # ─── Receipts ────────────────────────────────────────────────────

    def add_receipt(self, store_name, date, items, total_amount, image_path='',
                    discounts=None, total_savings=0):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO receipts (store_name, date, items, discounts, total_amount,
                                  total_savings, image_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            store_name,
            date,
            json.dumps(items),
            json.dumps(discounts or []),
            total_amount,
            total_savings,
            image_path,
            datetime.now().isoformat()
        ))
        receipt_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return receipt_id

    def get_all_receipts(self):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM receipts ORDER BY date DESC, created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return [self._row_to_dict(r) for r in rows]

    def get_receipt(self, receipt_id):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM receipts WHERE id = ?', (receipt_id,))
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

        if start_date and end_date:
            cursor.execute(
                'SELECT * FROM receipts WHERE date >= ? AND date <= ? ORDER BY date DESC',
                (start_date, end_date)
            )
        elif start_date:
            cursor.execute(
                'SELECT * FROM receipts WHERE date >= ? ORDER BY date DESC',
                (start_date,)
            )
        elif end_date:
            cursor.execute(
                'SELECT * FROM receipts WHERE date <= ? ORDER BY date DESC',
                (end_date,)
            )
        else:
            cursor.execute('SELECT * FROM receipts ORDER BY date DESC')

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
        return dict(row) if row else {'id': 1, 'residents': 1, 'period_start': '', 'period_end': ''}

    def update_settings(self, residents=1, period_start='', period_end=''):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE settings SET residents = ?, period_start = ?, period_end = ?
            WHERE id = 1
        ''', (residents, period_start, period_end))
        conn.commit()
        conn.close()
