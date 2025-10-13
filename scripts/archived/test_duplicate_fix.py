import sqlite3
from datetime import datetime, timedelta

# Connect to database
conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

print("=" * 80)
print("CURRENT DATABASE STATE:")
print("=" * 80)

# Show all Magical Shard transactions
c.execute("""
    SELECT id, timestamp, transaction_type, quantity, price, content_hash 
    FROM transactions 
    WHERE item_name = 'Magical Shard'
    ORDER BY timestamp DESC
""")

rows = c.fetchall()
if rows:
    for row in rows:
        id_, ts, ttype, qty, price, chash = row
        print(f"ID {id_}: {ts} | {ttype:6} | {qty:4}x | {price:>15,} | {chash}")
    
    # Check for potential duplicates
    print("\n" + "=" * 80)
    print("DUPLICATE ANALYSIS:")
    print("=" * 80)
    
    # Group by qty+price+type
    groups = {}
    for row in rows:
        id_, ts, ttype, qty, price, chash = row
        key = (qty, price, ttype)
        if key not in groups:
            groups[key] = []
        groups[key].append((id_, ts, chash))
    
    for (qty, price, ttype), entries in groups.items():
        if len(entries) > 1:
            print(f"\n⚠️  DUPLICATE FOUND: {ttype.upper()} {qty}x @ {price:,}")
            for id_, ts, chash in entries:
                # Parse timestamps to show time difference
                try:
                    ts_dt = datetime.fromisoformat(ts)
                    print(f"   ID {id_}: {ts} (hash={chash})")
                except Exception:
                    print(f"   ID {id_}: {ts} (hash={chash})")
            
            # Show time difference
            if len(entries) == 2:
                try:
                    ts1 = datetime.fromisoformat(entries[0][1])
                    ts2 = datetime.fromisoformat(entries[1][1])
                    diff_seconds = abs((ts1 - ts2).total_seconds())
                    diff_minutes = diff_seconds / 60
                    print(f"   Time difference: {diff_minutes:.1f} minutes")
                except Exception:
                    pass
        else:
            print(f"✓ {ttype.upper()} {qty}x @ {price:,} - No duplicates")
else:
    print("No Magical Shard transactions found")

print("\n" + "=" * 80)
print("MAPLE SAP TRANSACTIONS:")
print("=" * 80)

c.execute("""
    SELECT id, timestamp, transaction_type, quantity, price, content_hash 
    FROM transactions 
    WHERE item_name = 'Maple Sap'
    ORDER BY timestamp DESC
    LIMIT 5
""")

rows = c.fetchall()
if rows:
    for row in rows:
        id_, ts, ttype, qty, price, chash = row
        print(f"ID {id_}: {ts} | {ttype:6} | {qty:4}x | {price:>15,} | {chash}")
else:
    print("No Maple Sap transactions found")

conn.close()

print("\n" + "=" * 80)
print("EXPECTED BEHAVIOR:")
print("=" * 80)
print("✓ No duplicate Magical Shard with same qty+price+type within 5 minutes")
print("✓ All Maple Sap transactions should be unique")
