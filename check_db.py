import sqlite3

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

# Find all Magical Shard transactions today
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, tx_case 
    FROM transactions 
    WHERE item_name = 'Magical Shard' 
      AND date(timestamp) = date('now')
    ORDER BY timestamp DESC
""")

print("All Magical Shard transactions today:")
for row in c.fetchall():
    ts, tx_type, item, qty, price, case = row
    print(f"  {ts} | {tx_type} | {qty}x {item} | Price: {price:,} Silver | Case: {case}")

# Find any transaction with price around 126184
print("\n\nAny transaction with suspicious low price (< 500,000):")
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, tx_case 
    FROM transactions 
    WHERE price < 500000
      AND date(timestamp) = date('now')
    ORDER BY timestamp DESC
    LIMIT 10
""")

for row in c.fetchall():
    ts, tx_type, item, qty, price, case = row
    print(f"  {ts} | {tx_type} | {qty}x {item} | Price: {price:,} Silver | Case: {case}")

conn.close()
