import sqlite3

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

print("=" * 80)
print("SEARCH 1: Items with 'Ancient' or 'Mushroom' in name:")
print("=" * 80)
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, content_hash 
    FROM transactions 
    WHERE item_name LIKE '%Ancient%' OR item_name LIKE '%Mushroom%'
    ORDER BY timestamp DESC
    LIMIT 20
""")
for row in c.fetchall():
    ts, ttype, item, qty, price, chash = row
    formatted_price = f"{price:,.0f}" if price else "N/A"
    print(f"{ts} | {ttype:6} | {qty:4}x {item:30} | {formatted_price:>15} | {chash}")

print("\n" + "=" * 80)
print("SEARCH 2: Transactions with price near 146,800:")
print("=" * 80)
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, content_hash 
    FROM transactions 
    WHERE price BETWEEN 140000 AND 150000
    ORDER BY timestamp DESC
    LIMIT 20
""")
for row in c.fetchall():
    ts, ttype, item, qty, price, chash = row
    formatted_price = f"{price:,.0f}" if price else "N/A"
    print(f"{ts} | {ttype:6} | {qty:4}x {item:30} | {formatted_price:>15} | {chash}")

print("\n" + "=" * 80)
print("SEARCH 3: Transactions with quantity = 4:")
print("=" * 80)
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, content_hash 
    FROM transactions 
    WHERE quantity = 4
    ORDER BY timestamp DESC
    LIMIT 20
""")
for row in c.fetchall():
    ts, ttype, item, qty, price, chash = row
    formatted_price = f"{price:,.0f}" if price else "N/A"
    print(f"{ts} | {ttype:6} | {qty:4}x {item:30} | {formatted_price:>15} | {chash}")

print("\n" + "=" * 80)
print("SEARCH 4: All items with 'Special' in name:")
print("=" * 80)
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, content_hash 
    FROM transactions 
    WHERE item_name LIKE '%Special%'
    ORDER BY timestamp DESC
    LIMIT 20
""")
for row in c.fetchall():
    ts, ttype, item, qty, price, chash = row
    formatted_price = f"{price:,.0f}" if price else "N/A"
    print(f"{ts} | {ttype:6} | {qty:4}x {item:30} | {formatted_price:>15} | {chash}")

conn.close()
