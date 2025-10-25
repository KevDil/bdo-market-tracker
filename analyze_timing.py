import sqlite3
from datetime import datetime

conn = sqlite3.connect('bdo_tracker.db')
conn.row_factory = sqlite3.Row

print("=== PREORDER TIMING ANALYSIS ===\n")

preorders = [dict(row) for row in conn.execute(
    "SELECT * FROM preorders WHERE id >= 20 ORDER BY id"
).fetchall()]

for po in preorders:
    created_dt = datetime.fromisoformat(po['created_at'])
    timestamp_dt = datetime.fromisoformat(po['timestamp'])
    
    if po['collected_at']:
        collected_dt = datetime.fromisoformat(po['collected_at'])
        duration = (collected_dt - created_dt).total_seconds()
        print(f"ID {po['id']}: COLLECTED")
    else:
        print(f"ID {po['id']}: ACTIVE")
    
    print(f"  Created:    {po['created_at']}")
    print(f"  Timestamp:  {po['timestamp']}")
    print(f"  Quantity:   {po['quantity']}")
    print(f"  Price:      {po['price']:,.0f}")
    
    if po['collected_at']:
        print(f"  Collected:  {po['collected_at']}")
        print(f"  Duration:   {duration:.3f}s")
    
    print()

print("\n=== TRANSACTION ===")
tx = dict(conn.execute(
    "SELECT * FROM transactions WHERE id = 5"
).fetchone())

print(f"ID {tx['id']}:")
print(f"  Timestamp:  {tx['timestamp']}")
print(f"  Item:       {tx['item_name']}")
print(f"  Quantity:   {tx['quantity']}")
print(f"  Price:      {tx['price']:,.0f}")
print(f"  Type:       {tx['transaction_type']}")
print(f"  Case:       {tx['tx_case']}")

conn.close()
