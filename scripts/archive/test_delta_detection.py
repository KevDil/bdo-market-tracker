"""
Test script for Delta Detection with DB check
"""

import sys

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

sys.path.insert(0, "c:\\Users\\kdill\\Desktop\\market_tracker")

from database import get_connection
from tracker import MarketTracker
import datetime

# Clear test data
conn = get_connection()
cur = conn.cursor()
cur.execute("DELETE FROM transactions WHERE item_name LIKE 'Test Item%'")
conn.commit()

print("🧪 Testing Delta Detection with DB check\n")

# Scenario: Two purchases of same item at same minute
test_time = datetime.datetime(2025, 10, 11, 14, 30, 0)

# First purchase - insert directly
print("1️⃣ Inserting first purchase: Test Item x10 for 100,000")
cur.execute("""
    INSERT INTO transactions (item_name, quantity, price, transaction_type, timestamp, tx_case)
    VALUES (?, ?, ?, ?, ?, ?)
""", ("Test Item", 10, 100000, "buy", test_time, "buy_collect"))
conn.commit()

# Check DB
cur.execute("SELECT * FROM transactions WHERE item_name = 'Test Item'")
results = cur.fetchall()
print(f"   ✅ DB has {len(results)} transaction(s)\n")

# Simulate second scan with SAME item at SAME timestamp (but different transaction)
print("2️⃣ Simulating second purchase: Test Item x20 for 200,000 (same timestamp)")

# Create fake OCR text with TWO transactions at same timestamp
ocr_text = """Central Market Warehouse Balance 74,153,643,082 2025.10.11 14.30 2025.10.11 14.30 Purchased Test Item x10 for 100,000 Silver Transaction of Test Item x10 worth 100,000 Silver has been completed. Purchased Test Item x20 for 200,000 Silver Transaction of Test Item x20 worth 200,000 Silver has been completed. Orders Completed"""

tracker = MarketTracker(debug=True)
tracker.last_overview_text = "Central Market Warehouse Balance 74,153,643,082 2025.10.11 14.30 Purchased Test Item x10 for 100,000 Silver Transaction of Test Item x10 worth 100,000 Silver has been completed. Orders Completed"

print("   Processing OCR text with two transactions...")
tracker.process_ocr_text(ocr_text)

# Check final DB state
cur.execute("SELECT * FROM transactions WHERE item_name = 'Test Item' ORDER BY timestamp")
results = cur.fetchall()
print(f"\n3️⃣ Final DB state:")
for row in results:
    print(f"   - {row[1]} x{row[2]} for {row[3]:,} Silver @ {row[5]} ({row[6]})")

if len(results) == 2:
    print("\n✅ SUCCESS: Both transactions saved (no false duplicate detection)")
else:
    print(f"\n❌ FAILED: Expected 2 transactions, got {len(results)}")

# Cleanup
cur.execute("DELETE FROM transactions WHERE item_name LIKE 'Test Item%'")
conn.commit()
print("\n🧹 Test data cleaned up")
