import sqlite3

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

print("=" * 80)
print("LAST 20 TRANSACTIONS (ALL):")
print("=" * 80)
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, content_hash 
    FROM transactions 
    ORDER BY id DESC
    LIMIT 20
""")
for row in c.fetchall():
    ts, ttype, item, qty, price, chash = row
    formatted_price = f"{price:,.0f}" if price else "N/A"
    print(f"{ts} | {ttype:6} | {qty:4}x {item:30} | {formatted_price:>15} | {chash}")

print("\n" + "=" * 80)
print("MUSHROOM TRANSACTIONS:")
print("=" * 80)
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, content_hash 
    FROM transactions 
    WHERE item_name LIKE '%Mushroom%'
    ORDER BY timestamp DESC
""")
for row in c.fetchall():
    ts, ttype, item, qty, price, chash = row
    formatted_price = f"{price:,.0f}" if price else "N/A"
    print(f"{ts} | {ttype:6} | {qty:4}x {item:30} | {formatted_price:>15} | {chash}")

print("\n" + "=" * 80)
print("TRANSACTIONS AROUND 23:07 OR 21:07:")
print("=" * 80)
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, content_hash 
    FROM transactions 
    WHERE timestamp LIKE '%23:07%' OR timestamp LIKE '%21:07%'
    ORDER BY timestamp DESC
""")
for row in c.fetchall():
    ts, ttype, item, qty, price, chash = row
    formatted_price = f"{price:,.0f}" if price else "N/A"
    print(f"{ts} | {ttype:6} | {qty:4}x {item:30} | {formatted_price:>15} | {chash}")

conn.close()
