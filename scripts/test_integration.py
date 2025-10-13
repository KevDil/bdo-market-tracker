"""
Integration test: Replay the exact scenario from ocr_log.txt
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

print("🎬 Replaying exact scenario from ocr_log.txt\n")
print("="*70)

# Clean up any test data
conn = get_connection()
cur = conn.cursor()
cur.execute("DELETE FROM transactions WHERE item_name = 'Spirit''S Leaf' AND timestamp = '2025-10-11 14:01:00'")
conn.commit()

# Simulate app start with persistent baseline
tracker = MarketTracker(debug=True)

print("\n📸 SCAN 1: Buy Overview (with Spirit's Leaf transaction)")
print("="*70)

# The exact OCR text from 14:13:56
ocr_text_1 = """Central Market Ww Warehouse Balance 74,153,643,082 2025.10.11 14.01 2025.10.11 14.01 2025.10.11 14.01 2025.10.11 14.01 Placed order of Spirit's Leaf x5,000 for 20,200,000 Silver Transaction of Spirit's Leaf x5,000 worth 20,300,000 Silver has been completed: Placed order of Grim Reaper's Elixir x2,000 for 418,000,000 Silver Withdrew order of Grim Reaper's Elixir xl,991 for 416,119,000 silver Manage Warehouse Warehouse Capacity 4,155.8 / 11,000 VT 31.590 Sell Pearl Item Selling Limit 0 / 35 Sell Buy Kfse KVeo Enter search term:  Enter a search term: Items Listed   556 Sales Completed Jceeel VT Traditional Mattress Registration Count Sales Completed 2024 04-26 16.02 690,000 Cancel Re-list"""

tracker.process_ocr_text(ocr_text_1)

# Check DB
cur.execute("SELECT * FROM transactions WHERE item_name LIKE '%Spirit%Leaf%' ORDER BY timestamp DESC")
results = cur.fetchall()
print(f"\n📊 Database after scan 1: {len(results)} transaction(s)")
for row in results:
    print(f"   - {row[1]} x{row[2]} for {row[3]:,.0f} Silver @ {row[5]} ({row[6]})")

print("\n" + "="*70)
print("✅ Expected: 1 transaction for Spirit's Leaf saved")
print(f"{'✅ PASS' if len(results) == 1 else '❌ FAIL'}: Got {len(results)} transaction(s)")

# Cleanup
cur.execute("DELETE FROM transactions WHERE item_name LIKE '%Spirit%Leaf%'")
conn.commit()
print("\n🧹 Cleaned up test data")
