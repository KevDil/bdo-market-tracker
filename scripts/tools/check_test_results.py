"""Check test results from database."""
from database import get_connection

conn = get_connection()
cur = conn.cursor()

print('='*60)
print('PREORDERS TABLE')
print('='*60)
cur.execute('''
    SELECT id, item_name, quantity, quantity_filled, price, status, 
           timestamp, collected_at 
    FROM preorders 
    ORDER BY id DESC 
    LIMIT 10
''')
for row in cur.fetchall():
    print(f"ID={row[0]}: {row[1]}")
    print(f"  Quantity: {row[2]:,}x (filled: {row[3]:,}x)")
    print(f"  Price: {row[4]:,.0f} Silver")
    print(f"  Status: {row[5]}")
    print(f"  Placed: {row[6]}")
    print(f"  Collected: {row[7]}")
    print()

print('='*60)
print('TRANSACTIONS TABLE (last 10)')
print('='*60)
cur.execute('''
    SELECT id, item_name, quantity, price, transaction_type, 
           tx_case, timestamp 
    FROM transactions 
    ORDER BY id DESC 
    LIMIT 10
''')
for row in cur.fetchall():
    print(f"ID={row[0]}: {row[1]}")
    print(f"  {row[2]:,}x @ {row[3]:,.0f} Silver")
    print(f"  Type: {row[4]}, Case: {row[5]}")
    print(f"  Time: {row[6]}")
    print()

conn.close()
