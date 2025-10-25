import sqlite3
import pprint
from datetime import datetime

conn = sqlite3.connect('bdo_tracker.db')
conn.row_factory = sqlite3.Row

print("=== PREORDERS ===")
preorders = [dict(row) for row in conn.execute('SELECT * FROM preorders ORDER BY id').fetchall()]
pprint.pprint(preorders)

print("\n=== TRANSACTIONS (Sharp Black Crystal Shard) ===")
txs = [dict(row) for row in conn.execute(
    "SELECT * FROM transactions WHERE item_name LIKE '%Sharp Black Crystal%' ORDER BY id DESC LIMIT 10"
).fetchall()]
pprint.pprint(txs)

conn.close()
