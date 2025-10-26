import sqlite3
from datetime import datetime, timedelta

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

# Find mushroom transactions from today
print("=== Special Hump Mushroom Transactions (last 24h) ===\n")
c.execute("""
    SELECT id, timestamp, transaction_type, item_name, quantity, price, tx_case, occurrence_index
    FROM transactions 
    WHERE item_name LIKE '%mushroom%'
      AND timestamp >= datetime('now', '-1 day')
    ORDER BY timestamp DESC
""")

rows = c.fetchall()
for row in rows:
    id, ts, tx_type, item, qty, price, case, occ_idx = row
    print(f"ID: {id}")
    print(f"  Time: {ts}")
    print(f"  Type: {tx_type} | {qty}x {item}")
    print(f"  Price: {price:,} Silver")
    print(f"  Case: {case} | Occurrence: {occ_idx}")
    print()

# Check for duplicates (same item, qty, price, type)
print("\n=== Checking for Duplicates ===\n")
c.execute("""
    SELECT item_name, quantity, price, transaction_type, COUNT(*) as count, 
           GROUP_CONCAT(timestamp) as timestamps,
           GROUP_CONCAT(id) as ids
    FROM transactions 
    WHERE item_name LIKE '%mushroom%'
      AND timestamp >= datetime('now', '-1 day')
    GROUP BY item_name, quantity, price, transaction_type
    HAVING count > 1
    ORDER BY timestamps
""")

duplicates = c.fetchall()
if duplicates:
    print("⚠️ DUPLICATES FOUND:")
    for dup in duplicates:
        item, qty, price, tx_type, count, timestamps, ids = dup
        print(f"\n{count}x duplicate: {tx_type} {qty}x {item} @ {price:,} Silver")
        print(f"  Timestamps: {timestamps}")
        print(f"  IDs: {ids}")
else:
    print("✅ No duplicates found")

# Check new purchases from today
print("\n\n=== Recent BUY Transactions (last 2 hours) ===\n")
c.execute("""
    SELECT timestamp, item_name, quantity, price, tx_case
    FROM transactions 
    WHERE transaction_type = 'buy'
      AND timestamp >= datetime('now', '-2 hours')
    ORDER BY timestamp DESC
    LIMIT 20
""")

recent_buys = c.fetchall()
if recent_buys:
    for row in recent_buys:
        ts, item, qty, price, case = row
        print(f"{ts} | {qty}x {item} | {price:,} Silver | Case: {case}")
else:
    print("❌ No recent buy transactions found in the last 2 hours")

conn.close()
