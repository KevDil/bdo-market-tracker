"""
Integration test: Replay exact user scenario
- Historical Birch Sap transaction (old log entry)
- Fresh Magical Shard sale (relist)
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

print("🎬 Replaying exact user scenario from 2025-10-11 14:32\n")
print("="*70)

# Clean up test data
conn = get_connection()
cur = conn.cursor()
cur.execute("DELETE FROM transactions WHERE item_name IN ('Birch Sap', 'Magical Shard') AND timestamp >= '2025-10-11 14:00:00'")
conn.commit()

tracker = MarketTracker(debug=True)

print("\n📸 SCAN 1: Buy Overview (with old Birch Sap transaction)")
print("="*70)

# First scan: buy_overview with historical Birch Sap
ocr_text_1 = """Central Market Warehouse Balance @ 73,871,786,082 Buy 2025.10.11 14.17 2025.10.11 14.14 2025.10.11 14.14 2025.10.11 14.14 Listed Magical Shard x200 for 646,000,000 Silver: The price of enhancement I Placed order of Birch Sap x5,000 for 66,000,000 Silver Withdrew order of Birch Sap x4,670 for 60,243,000 silver Transaction of Birch Sap x330 worth 4,257,000 Silver has been completed Orders Completed Collect All"""

tracker.process_ocr_text(ocr_text_1)

print("\n📸 SCAN 2: Sell Overview (fresh Magical Shard sale)")
print("="*70)

# Second scan: sell_overview with fresh Magical Shard transaction
ocr_text_2 = """Central Market Warehouse Balance @ 74,444,949,582 Buy 2025.10.11 14.32 2025.10.11 14.32 2025.10.11 14.17 2025.10.11 14.14 Listed Magical Shard x200 for 630,000,000 Silver. The price of enhancement m_. Transaction of Magical Shard x200 worth 573,163,500 Silver has been complet__ Listed Magical Shard x200 for 646,000,000 Silver: The price of enhancement Placed order of Birch Sap x5,000 for 66,000,000 Silver Items Listed 756 Sales Completed"""

tracker.process_ocr_text(ocr_text_2)

# Check final DB state
print("\n" + "="*70)
print("📊 Final Database State:")
print("="*70)

cur.execute("SELECT * FROM transactions WHERE item_name IN ('Birch Sap', 'Magical Shard') AND timestamp >= '2025-10-11 14:00:00' ORDER BY timestamp")
results = cur.fetchall()

for row in results:
    print(f"   {row[4].upper():4s} | {row[1]:20s} | x{row[2]:<5d} | {row[3]:>13,.0f} Silver | {row[5]} | {row[6]}")

print("\n" + "="*70)
print("Expected results:")
print("  1. BUY  | Birch Sap            | x330   |     4,257,000 Silver | 2025-10-11 14:17:00 | buy_collect")
print("  2. SELL | Magical Shard        | x200   |   573,163,500 Silver | 2025-10-11 14:32:00 | sell_relist_full")
print()

if len(results) == 2:
    print("✅ SUCCESS: Both transactions saved correctly!")
else:
    print(f"❌ FAILED: Expected 2 transactions, got {len(results)}")

# Cleanup
cur.execute("DELETE FROM transactions WHERE item_name IN ('Birch Sap', 'Magical Shard') AND timestamp >= '2025-10-11 14:00:00'")
conn.commit()
print("\n🧹 Cleaned up test data")
