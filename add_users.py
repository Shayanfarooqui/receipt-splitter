"""
Add household members from the command line. Existing names are skipped.

    python add_users.py Hasib Pavel Toriq
"""
import sys
from db import ReceiptDB

db = ReceiptDB()
existing = {u['name'].lower() for u in db.get_all_users()}
for name in sys.argv[1:]:
    name = name.strip()
    if not name or name.lower() in existing:
        print(f'skip   {name} (already exists)')
        continue
    db.add_user(name)
    existing.add(name.lower())
    print(f'added  {name}')
