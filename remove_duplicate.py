import sqlite3

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

# Find the duplicate (keep the earlier one, remove the later one)
c.execute("""
    SELECT id, timestamp FROM transactions 
    WHERE item_name = 'Magical Shard' 
      AND quantity = 55 
      AND price = 146396250 
      AND transaction_type = 'sell'
    ORDER BY timestamp ASC
""")

rows = c.fetchall()
print(f"Found {len(rows)} Magical Shard transactions with same values")

if len(rows) > 1:
    # Keep first (earliest), delete others
    keep_id = rows[0][0]
    keep_ts = rows[0][1]
    
    for row in rows[1:]:
        del_id = row[0]
        del_ts = row[1]
        print(f"Deleting duplicate: ID {del_id} @ {del_ts} (keeping ID {keep_id} @ {keep_ts})")
        c.execute("DELETE FROM transactions WHERE id = ?", (del_id,))
    
    conn.commit()
    print(f"\n✓ Removed {len(rows)-1} duplicate(s)")
else:
    print("No duplicates to remove")

conn.close()
