#!/usr/bin/env python3
"""Check Pure Powder Reagent preorders and transactions."""

from database import get_connection

conn = get_connection()
cur = conn.cursor()

print("=" * 80)
print("PREORDERS - Pure Powder Reagent:")
print("=" * 80)

cur.execute('''
    SELECT id, quantity, quantity_filled, price, status, 
           datetime(timestamp, 'localtime') as placed,
           datetime(collected_at, 'localtime') as collected
    FROM preorders
    WHERE item_name LIKE '%Pure Powder Reagent%'
    ORDER BY timestamp DESC
    LIMIT 10
''')

for row in cur.fetchall():
    preorder_id, qty, filled, price, status, placed, collected = row
    print(f"\nID={preorder_id}: {qty:,}x (filled: {filled:,}x) @ {price:,} Silver")
    print(f"   Status: {status}, Placed: {placed}", end="")
    if collected:
        print(f", Collected: {collected}")
    else:
        print()

print("\n" + "=" * 80)
print("TRANSACTIONS - Pure Powder Reagent:")
print("=" * 80)

cur.execute('''
    SELECT id, quantity, price, transaction_type, tx_case,
           datetime(timestamp, 'localtime') as tx_time
    FROM transactions
    WHERE item_name LIKE '%Pure Powder Reagent%'
    ORDER BY timestamp DESC
    LIMIT 10
''')

rows = cur.fetchall()
if rows:
    for row in rows:
        tx_id, qty, price, tx_type, tx_case, tx_time = row
        unit_price = price / qty if qty > 0 else 0
        print(f"\nID={tx_id}: {qty:,}x @ {unit_price:,.0f} = {price:,} Silver")
        print(f"   Type: {tx_type}, Case: {tx_case}, Time: {tx_time}")
else:
    print("\n(No transactions found)")

print("\n" + "=" * 80)
