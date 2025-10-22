from database import get_cursor

cur = get_cursor()
cur.execute("""
    SELECT id, item_name, quantity, price, transaction_type, timestamp, tx_case 
    FROM transactions 
    ORDER BY id DESC 
    LIMIT 20
""")

print("Recent transactions:")
print("-" * 120)
print(f"{'ID':<5} | {'Item':<30} | {'Qty':<6} | {'Price':<15} | {'Type':<4} | {'Timestamp':<19} | {'Case':<15}")
print("-" * 120)

for row in cur.fetchall():
    item_name = row[1][:30]
    print(f"{row[0]:<5} | {item_name:<30} | {row[2]:<6} | {row[3]:<15,} | {row[4]:<4} | {row[5]:<19} | {row[6]:<15}")
