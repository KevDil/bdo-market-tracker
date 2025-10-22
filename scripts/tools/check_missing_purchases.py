import sqlite3
from datetime import datetime

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

print("=== Checking for Missing Purchases ===\n")

# Check for Maple Sap around 16:25
print("1. Maple Sap (2564x) around 16:25:")
c.execute("""
    SELECT id, timestamp, transaction_type, item_name, quantity, price, tx_case
    FROM transactions 
    WHERE item_name LIKE '%Maple%Sap%'
      AND date(timestamp) = date('now')
    ORDER BY timestamp DESC
""")
maple_results = c.fetchall()
if maple_results:
    for row in maple_results:
        id, ts, tx_type, item, qty, price, case = row
        print(f"  ✅ FOUND: ID {id} | {ts} | {tx_type} | {qty}x {item} | {price:,} | {case}")
else:
    print("  ❌ NOT FOUND in database")

print("\n2. Pure Powder Reagent (5000x) around 16:26:")
c.execute("""
    SELECT id, timestamp, transaction_type, item_name, quantity, price, tx_case
    FROM transactions 
    WHERE item_name LIKE '%Pure%Powder%Reagent%'
      AND date(timestamp) = date('now')
    ORDER BY timestamp DESC
""")
powder_results = c.fetchall()
if powder_results:
    for row in powder_results:
        id, ts, tx_type, item, qty, price, case = row
        print(f"  ✅ FOUND: ID {id} | {ts} | {tx_type} | {qty}x {item} | {price:,} | {case}")
else:
    print("  ❌ NOT FOUND in database")

# Check all purchases around 16:25-16:27
print("\n\n=== All BUY transactions between 16:20 and 16:30 ===\n")
c.execute("""
    SELECT timestamp, item_name, quantity, price, tx_case
    FROM transactions 
    WHERE transaction_type = 'buy'
      AND timestamp BETWEEN '2025-10-13 16:20:00' AND '2025-10-13 16:30:00'
    ORDER BY timestamp DESC
""")
recent = c.fetchall()
if recent:
    for row in recent:
        ts, item, qty, price, case = row
        print(f"{ts} | {qty}x {item} | {price:,} | {case}")
else:
    print("❌ No buy transactions found in this timeframe")

# Check for any transactions with similar names
print("\n\n=== Fuzzy search for 'sap' or 'reagent' ===\n")
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price
    FROM transactions 
    WHERE (item_name LIKE '%sap%' OR item_name LIKE '%reagent%')
      AND date(timestamp) = date('now')
    ORDER BY timestamp DESC
    LIMIT 10
""")
fuzzy = c.fetchall()
if fuzzy:
    for row in fuzzy:
        ts, tx_type, item, qty, price = row
        print(f"{ts} | {tx_type} | {qty}x {item} | {price:,}")
else:
    print("No matches found")

conn.close()
