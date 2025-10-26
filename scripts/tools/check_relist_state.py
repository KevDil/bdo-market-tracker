"""
Quick Test: Check Current Database State
=========================================
Shows current preorders and recent transactions for Trace of Nature
"""

import sqlite3
from datetime import datetime

conn = sqlite3.connect('bdo_tracker.db')
cur = conn.cursor()

print("="*80)
print("CURRENT DATABASE STATE - Trace of Nature")
print("="*80)

# Preorders
print("\n[PREORDERS]")
cur.execute('''
    SELECT id, quantity, quantity_filled, price, status, timestamp, collected_at
    FROM preorders
    WHERE item_name = 'Trace of Nature'
    ORDER BY timestamp DESC
''')

preorders = cur.fetchall()
if preorders:
    for p in preorders:
        status_icon = "✅" if p[4] == 'collected' else "🔵" if p[4] == 'active' else "❌"
        print(f"{status_icon} ID={p[0]}: {p[1]:,}x (filled: {p[2]:,}x) @ {p[3]:,} Silver")
        print(f"   Status: {p[4]}, Placed: {p[5]}, Collected: {p[6] or 'N/A'}")
else:
    print("   (No preorders found)")

# Transactions
print("\n[TRANSACTIONS]")
cur.execute('''
    SELECT id, quantity, price, transaction_type, tx_case, timestamp
    FROM transactions
    WHERE item_name = 'Trace of Nature'
    ORDER BY timestamp DESC
    LIMIT 10
''')

transactions = cur.fetchall()
if transactions:
    for t in transactions:
        print(f"   ID={t[0]}: {t[1]:,}x @ {t[2]:,} Silver")
        print(f"      Type: {t[3]}, Case: {t[4]}, Time: {t[5]}")
else:
    print("   (No transactions found)")

# Summary
print("\n[SUMMARY]")
cur.execute("SELECT COUNT(*) FROM preorders WHERE item_name = 'Trace of Nature' AND status = 'active'")
active_preorders = cur.fetchone()[0]

cur.execute("SELECT COUNT(*) FROM transactions WHERE item_name = 'Trace of Nature' AND timestamp >= datetime('now', '-1 hour')")
recent_tx = cur.fetchone()[0]

print(f"   Active Preorders: {active_preorders}")
print(f"   Recent Transactions (last 1h): {recent_tx}")

conn.close()

print("\n" + "="*80)
print("EXPECTED STATE AFTER RELIST TEST:")
print("="*80)
print("""
PREORDERS:
✅ OLD: 5000x @ 770M, status='collected'
🔵 NEW: 4979x @ 766,766,000, status='active'

TRANSACTIONS:
1. Auto-Collect: 5000x @ 770M
2. Instant Buy: 21x @ 3,234,000

Total: 1 active preorder, 2 recent transactions
""")
