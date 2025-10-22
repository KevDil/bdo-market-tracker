import sqlite3

conn = sqlite3.connect('bdo_tracker.db')
cur = conn.cursor()

print('=' * 80)
print('PREORDERS - Caphras Tree Sap')
print('=' * 80)
cur.execute('''
    SELECT id, quantity, quantity_filled, price, status, timestamp, collected_at
    FROM preorders
    WHERE item_name LIKE "%Caphras%"
    ORDER BY timestamp DESC
''')

for row in cur.fetchall():
    print(f"ID={row[0]}: {row[1]:,}x (filled: {row[2]:,}x) @ {row[3]:,.0f} Silver")
    print(f"   Status: {row[4]}, Placed: {row[5]}, Collected: {row[6] or 'N/A'}")

print('\n' + '=' * 80)
print('TRANSACTIONS - Caphras Tree Sap')
print('=' * 80)
cur.execute('''
    SELECT id, quantity, price, transaction_type, tx_case, timestamp
    FROM transactions
    WHERE item_name LIKE "%Caphras%"
    ORDER BY timestamp DESC
    LIMIT 10
''')

transactions = cur.fetchall()
if transactions:
    for row in transactions:
        print(f"ID={row[0]}: {row[1]:,}x @ {row[2]:,.0f} Silver")
        print(f"   Type: {row[3]}, Case: {row[4]}, Time: {row[5]}")
else:
    print("(No transactions found)")

conn.close()
