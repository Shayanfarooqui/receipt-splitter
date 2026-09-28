"""
Set (or change) the admin password. Run this on the laptop:

    python set_admin_password.py
"""
from getpass import getpass
from werkzeug.security import generate_password_hash
from db import ReceiptDB

password = getpass('New admin password: ')
if len(password) < 6:
    raise SystemExit('Password must be at least 6 characters')
if getpass('Repeat password: ') != password:
    raise SystemExit('Passwords do not match')

ReceiptDB().set_admin_password_hash(generate_password_hash(password))
print('Admin password saved.')
