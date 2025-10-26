import sqlite3
from datetime import datetime

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

print("=== Before Cleanup ===\n")
c.execute("""
    SELECT id, timestamp, transaction_type, item_name, quantity, price, tx_case
    FROM transactions 
    WHERE item_name LIKE '%mushroom%'
      AND timestamp >= datetime('now', '-1 day')
    ORDER BY timestamp DESC
""")
before = c.fetchall()
for row in before:
    id, ts, tx_type, item, qty, price, case = row
    print(f"ID {id}: {ts} | {tx_type} | {qty}x {item} | {price:,} | {case}")

# Find the duplicate entry (14:55:00 with occurrence_index=0)
print("\n\n=== Removing Duplicate ===\n")
c.execute("""
    SELECT id, timestamp, occurrence_index
    FROM transactions 
    WHERE item_name LIKE '%Special Hump Mushroom%'
      AND quantity = 953
      AND price = 28590000
      AND transaction_type = 'buy'
    ORDER BY timestamp DESC
""")
duplicates = c.fetchall()

if len(duplicates) > 1:
    # Keep the earlier one (14:37), remove the later one (14:55)
    for dup in duplicates:
        id, ts, occ = dup
        print(f"Found: ID {id}, Timestamp {ts}, Occurrence {occ}")
    
    # Remove the newer duplicate (14:55)
    newer_id = duplicates[0][0]  # First in DESC order = newest
    c.execute("DELETE FROM transactions WHERE id = ?", (newer_id,))
    conn.commit()
    print(f"\n✅ Deleted duplicate with ID {newer_id}")
else:
    print("No duplicates found (only one entry exists)")

print("\n\n=== After Cleanup ===\n")
c.execute("""
    SELECT id, timestamp, transaction_type, item_name, quantity, price, tx_case, occurrence_index
    FROM transactions 
    WHERE item_name LIKE '%mushroom%'
      AND timestamp >= datetime('now', '-1 day')
    ORDER BY timestamp DESC
""")
after = c.fetchall()
for row in after:
    id, ts, tx_type, item, qty, price, case, occ = row
    print(f"ID {id}: {ts} | {tx_type} | {qty}x {item} | {price:,} | {case} | Occ: {occ}")

if len(after) == 1:
    print("\n✅ SUCCESS: Only one mushroom transaction remains")
else:
    print(f"\n⚠️ WARNING: {len(after)} mushroom transactions found")

conn.close()
