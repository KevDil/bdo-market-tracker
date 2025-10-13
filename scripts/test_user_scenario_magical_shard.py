"""
Comprehensive Test: OCR-Fehler mit fehlenden führenden Ziffern
Simuliert das reale User-Szenario vom 2025-10-12 04:04:00
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracker import MarketTracker
import sqlite3

# Cleanup
conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()
c.execute("DELETE FROM transactions WHERE item_name = 'Magical Shard' AND strftime('%H:%M', timestamp) = '04:04'")
c.execute("DELETE FROM tracker_state")
conn.commit()
conn.close()

print("=" * 80)
print("TEST: OCR-Fehler mit fehlenden führenden Ziffern (Real User Scenario)")
print("=" * 80)

# Simuliere OCR-Text mit KORREKTEM Preis (erster Scan um 04:04:08)
text1 = (
    "Central Market @ Buy Warehouse Balance 89,949,386,348 "
    "2025.10.12 04:04 "
    "Listed Magical Shard x200 for 662,000,000 Silver. "
    "Transaction of Magical Shard x200 worth 585,585,000 Silver has been completed. "
    "Items Listed 578 Sales Completed 201 Collect All"
)

# Simuliere OCR-Text mit FALSCHEM Preis (zweiter Scan um 04:04:13 - fehlende Ziffern)
text2 = (
    "Central Market @ Buy Warehouse Balance 89,949,386,348 "
    "2025.10.12 04:04 "
    "Listed Magical Shard x200 for 662,000,000 Silver "
    "Transaction of Magical Shard x200 worth 126,184 Silver has been completed "
    "Items Listed 578 Sales Completed 201 Collect All"
)

mt = MarketTracker(debug=True)

print("\n--- Scan 1: Korrekter Preis (585,585,000) ---")
mt.process_ocr_text(text1)

print("\n--- Scan 2: OCR-Fehler (126,184 statt 585,585,000) ---")
mt.process_ocr_text(text2)

# Verify database
conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()
c.execute("""
    SELECT timestamp, transaction_type, item_name, quantity, price, tx_case 
    FROM transactions 
    WHERE item_name = 'Magical Shard' 
      AND strftime('%H:%M', timestamp) = '04:04'
    ORDER BY id DESC
    LIMIT 5
""")

print("\n" + "=" * 80)
print("DATABASE VERIFICATION:")
print("=" * 80)

rows = c.fetchall()
if len(rows) == 1:
    ts, tx_type, item, qty, price, case = rows[0]
    print(f"Found 1 transaction: {ts} | {tx_type} | {qty}x {item} | Price: {price:,} | Case: {case}")
    
    if price >= 500_000_000 and price <= 600_000_000:
        print("\n✅ SUCCESS: Correct price saved (500M-600M range)")
        print(f"   Price: {price:,} Silver")
    else:
        print(f"\n❌ FAIL: Wrong price saved: {price:,} Silver")
        print(f"   Expected: 585,585,000 Silver")
elif len(rows) == 0:
    print("❌ FAIL: No transaction saved")
else:
    print(f"⚠️ WARNING: {len(rows)} transactions saved (expected 1)")
    for row in rows:
        ts, tx_type, item, qty, price, case = row
        print(f"  - {ts} | {tx_type} | {qty}x {item} | Price: {price:,} | Case: {case}")

conn.close()

print("=" * 80)
print("Test complete")
print("=" * 80)
