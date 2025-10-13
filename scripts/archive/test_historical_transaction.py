"""
Test historical transaction detection (isolated Transaction-only entries)
"""
import sys

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

sys.path.insert(0, "c:\\Users\\kdill\\Desktop\\market_tracker")

from tracker import MarketTracker
from database import get_connection

print("🧪 Testing historical transaction detection\n")
print("="*70)

# Clean up test data
conn = get_connection()
cur = conn.cursor()
cur.execute("DELETE FROM transactions WHERE item_name LIKE 'Birch Sap'")
conn.commit()

# Simulate the exact scenario from ocr_log.txt
tracker = MarketTracker(debug=True)

print("\n📸 SCAN: Buy Overview with historical Birch Sap transaction")
print("="*70)

# The exact OCR text from 14:32:36 (first buy_overview scan)
ocr_text = """Central Market Warehouse Balance @ 73,871,786,082 Buy 2025.10.11 14.17 2025.10.11 14.14 2025.10.11 14.14 2025.10.11 14.14 Listed Magical Shard x200 for 646,000,000 Silver: The price of enhancement I Placed order of Birch Sap x5,000 for 66,000,000 Silver Withdrew order of Birch Sap x4,670 for 60,243,000 silver Transaction of Birch Sap x330 worth 4,257,000 Silver has been completed Orders Completed Collect All"""

tracker.process_ocr_text(ocr_text)

# Check DB
cur.execute("SELECT * FROM transactions WHERE item_name LIKE '%Birch%Sap%' ORDER BY timestamp DESC")
results = cur.fetchall()
print(f"\n📊 Database after scan: {len(results)} transaction(s)")
for row in results:
    print(f"   - {row[1]} x{row[2]} for {row[3]:,.0f} Silver @ {row[5]} ({row[6]})")

print("\n" + "="*70)
print("✅ Expected: 1 transaction for Birch Sap (buy_collect - historical entry)")
print(f"{'✅ PASS' if len(results) == 1 else '❌ FAIL'}: Got {len(results)} transaction(s)")

if len(results) == 1:
    tx_case = results[0][6]
    expected_case = 'buy_collect'
    print(f"Case check: {tx_case} {'✅' if tx_case == expected_case else '❌ Expected: ' + expected_case}")

# Cleanup
cur.execute("DELETE FROM transactions WHERE item_name LIKE '%Birch%Sap%'")
conn.commit()
print("\n🧹 Cleaned up test data")
