#!/usr/bin/env python3
"""Check Monk's Branch entries in database"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

db_path = Path(__file__).parent.parent / 'bdo_tracker.db'

conn = sqlite3.connect(db_path)
cur = conn.cursor()

cur.execute('''
    SELECT id, timestamp, transaction_type, item_name, quantity, price, tx_case 
    FROM transactions 
    WHERE item_name LIKE ? 
    ORDER BY id
''', ('%Monk%',))

rows = cur.fetchall()

print(f"\n{'='*70}")
print(f"Found {len(rows)} Monk's Branch entries:")
print('='*70)

for i, r in enumerate(rows, 1):
    print(f"\nEntry {i}:")
    print(f"  ID: {r[0]}")
    print(f"  Timestamp: {r[1]}")
    print(f"  Type: {r[2]}")
    print(f"  Item: {r[3]}")
    print(f"  Quantity: {r[4]}")
    print(f"  Price: {r[5]:,.0f} Silver")
    print(f"  Unit Price: {r[5]/r[4]:,.2f} Silver/unit")
    print(f"  Case: {r[6]}")

conn.close()

print(f"\n{'='*70}")
print(f"Expected: 1 entry (88x for 1,980,000 Silver = 22,500 Silver/unit)")
print(f"Actual: {len(rows)} entries")
print('='*70)
