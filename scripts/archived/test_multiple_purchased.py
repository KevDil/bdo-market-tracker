"""
Test für Bug: Zwei separate 'purchased' Events mit gleichem Timestamp aber unterschiedlichen Preisen
Szenario: Zwei Käufe von 5000x Snowfield Cedar Sap für unterschiedliche Preise (196000000 und 195966400)
Erwartung: BEIDE Transaktionen werden gespeichert (nicht nur eine)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker import MarketTracker
from database import get_cursor, get_connection

print("=" * 60)
print("Test: Multiple Purchased Events with Different Prices")
print("=" * 60)

# Reset DB for clean test
cur = get_cursor()
cur.execute("DELETE FROM transactions WHERE item_name = 'Snowfield Cedar Sap'")
get_connection().commit()

# Simulate OCR text with TWO separate purchased events
# This is the actual OCR from the user's log
ocr_text = """Central Market Warehouse Balance W =3 77,481,933,002 Buy Manage Warehouse 2025.10.12 01:17 2025.10.12 01:16 2025.10.12 01:16 2025.10.12 01:16 Placed order of Snowfield Cedar Sap x5,000 for 170,500,000 Silver Purchased Snowfield Cedar Sap x5,000 for 196,000,000 Silver Purchased Snowfield Cedar Sap x5,000 for 195,966,400 Silver Withdrew order of Snowfield Cedar Sap x5,000 for 169,500,000 silver"""

tracker = MarketTracker(debug=True)

print("\n[1] Processing OCR text with 2 purchased events...")
tracker.process_ocr_text(ocr_text)

print("\n[2] Checking database...")
cur.execute("""
    SELECT item_name, quantity, price, transaction_type, timestamp, tx_case 
    FROM transactions 
    WHERE item_name = 'Snowfield Cedar Sap' 
    AND transaction_type = 'buy'
    ORDER BY price DESC
""")
results = cur.fetchall()

print(f"\n[3] Results: Found {len(results)} transactions")
for row in results:
    item, qty, price, ttype, ts, case = row
    print(f"   OK {ttype.upper()} - {qty}x {item} for {price:,} Silver @ {ts} [{case}]")

print("\n" + "=" * 60)
if len(results) == 2:
    # Check both prices are present
    prices = {row[2] for row in results}
    if 196000000 in prices and 195966400 in prices:
        print("TEST PASSED - Both purchased events were saved correctly!")
        print(f"   - Transaction 1: 5000x for 196,000,000 Silver")
        print(f"   - Transaction 2: 5000x for 195,966,400 Silver")
    else:
        print(f"TEST FAILED - Wrong prices: {prices}")
        print(f"   Expected: 196000000 and 195966400")
elif len(results) == 1:
    print("TEST FAILED - Only ONE transaction saved (should be TWO!)")
    print(f"   Saved: {results[0][2]:,} Silver")
    print(f"   Missing: {'196,000,000' if results[0][2] != 196000000 else '195,966,400'} Silver")
elif len(results) == 0:
    print("TEST FAILED - NO transactions saved!")
else:
    print(f"TEST FAILED - Wrong count: {len(results)} (expected 2)")

print("=" * 60)
