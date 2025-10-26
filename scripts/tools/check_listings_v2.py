"""Check Magical Shard listings with correct schema."""
import sqlite3

db = sqlite3.connect('bdo_tracker.db')
c = db.cursor()

print("=" * 80)
print("ALL MAGICAL SHARD LISTINGS:")
print("=" * 80)
c.execute('''
    SELECT id, item_name, quantity, quantity_sold, price, timestamp, status, collected_at
    FROM listings 
    WHERE item_name="Magical Shard" 
    ORDER BY id DESC
''')
for r in c.fetchall():
    id, item, qty, sold, price, ts, status, collected = r
    print(f'ID={id}: {qty}x @ {price:,.0f} Silver')
    print(f'  Sold: {sold}x | Status: {status}')
    print(f'  Timestamp: {ts}')
    print(f'  Collected: {collected}')
    print()

print("=" * 80)
print("EXPECTED vs ACTUAL:")
print("=" * 80)
print("EXPECTED:")
print("  Old: 200x @ 654,000,000 - Status: collected ✅")
print("  New: 172x @ 569,320,000 - Status: active ❌ MISSING!")
print()
print("ACTUAL:")
print("  Only old listing exists, marked as collected ✅")
print("  New listing was NOT created! ❌")
