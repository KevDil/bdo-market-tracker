"""Check if Gem of Void transactions exist in database"""
import sqlite3
from pathlib import Path

db_path = Path(__file__).resolve().parents[1] / "bdo_tracker.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

results = cur.execute(
    "SELECT timestamp, transaction_type, item_name, quantity, price "
    "FROM transactions "
    "WHERE item_name LIKE '%Gem%Void%' "
    "ORDER BY timestamp DESC"
).fetchall()

print("=" * 80)
print("GEM OF VOID TRANSACTIONS IN DATABASE")
print("=" * 80)

if results:
    for r in results:
        print(f"{r[0]} | {r[1]:12} | {r[2]:20} | {r[3]:5} x {r[4]:,}")
else:
    print("❌ NO GEM OF VOID TRANSACTIONS FOUND")
    print("\nExpected transaction:")
    print("  2025-10-12 11:06:00 | buy (purchased) | Gem of Void | 10 x 368,000,000")

conn.close()
print("=" * 80)
