"""Check Magical Shard listings."""
import sqlite3

db = sqlite3.connect('bdo_tracker.db')
c = db.cursor()

print("ALL MAGICAL SHARD LISTINGS:")
c.execute('SELECT * FROM listings WHERE item_name="Magical Shard" ORDER BY id DESC')
for r in c.fetchall():
    print(f'ID={r[0]}: {r[2]}x @ {r[3]:,.0f} | Status={r[4]}')
    print(f'  Created: {r[5]} | Collected: {r[6]}')
