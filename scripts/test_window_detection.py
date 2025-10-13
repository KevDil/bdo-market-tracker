"""
Test window detection with ambiguous OCR text
"""
import sys

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

sys.path.insert(0, "c:\\Users\\kdill\\Desktop\\market_tracker")

from utils import detect_window_type

# The actual OCR text from your log at 14:13:56
ocr_text = """Central Market Ww Warehouse Balance 74,153,643,082 2025.10.11 14.01 2025.10.11 14.01 2025.10.11 14.01 2025.10.11 14.01 Placed order of Spirit's Leaf x5,000 for 20,200,000 Silver Transaction of Spirit's Leaf x5,000 worth 20,300,000 Silver has been completed: Placed order of Grim Reaper's Elixir x2,000 for 418,000,000 Silver Withdrew order of Grim Reaper's Elixir xl,991 for 416,119,000 silver Manage Warehouse Warehouse Capacity 4,155.8 / 11,000 VT 31.590 Sell Pearl Item Selling Limit 0 / 35 Sell Buy Kfse KVeo Enter search term:  Enter a search term: Items Listed   556 Sales Completed Jceeel VT Traditional Mattress Registration Count Sales Completed 2024 04-26 16.02 690,000 Cancel Re-list 2669 2393 1556 696 502 [Manor] Seesaw Registration Count 2024 04-26 16.02 700,000 Cancel 342 Sales Completed Re-list 166 156 Wooden Baduk Board Registration Count Sales Completed 2025 09-09 20.03 1,860,000 Cancel Re-list 464 135 Fish Wind Chime Registration Count : 2025 09-09 20.04 625,000 Cancel 387 116 Sales Completed Re-list 289 260 [Manor] Olvian Bookshelf Registration Count Sales Completed 2025 09-09 20.03 15,500,000 Cancel Re-list 248 235 [Manor] Olvian Bed Registration Count 2025 09-09 20.03 15,500,000 Cancel Sales Completed Re-list Buy"""

print("🧪 Testing window detection with ambiguous text\n")
print("OCR text contains:")
print("  - 'Placed order of...' (buy anchor)")
print("  - 'Transaction of ... worth' (neutral, but in buy context)")
print("  - 'Sales Completed' (from UI, not from log)")
print()

window_type = detect_window_type(ocr_text)
print(f"Detected window: {window_type}")

if window_type == "buy_overview":
    print("✅ CORRECT! Strong buy anchor 'Placed order' recognized")
elif window_type == "sell_overview":
    print("❌ WRONG! Misdetected as sell_overview (ignoring buy anchors)")
else:
    print(f"❌ WRONG! Got unexpected: {window_type}")

# Test with pure sell overview
print("\n" + "="*60)
print("Testing with pure SELL overview text:\n")

sell_text = """Central Market 2025.10.11 12.30 2025.10.11 12.30 Transaction of Magical Shard x100 worth 300,000,000 Silver has been completed. Listed Magical Shard x200 for 600,000,000 Silver Sales Completed 200"""

sell_window = detect_window_type(sell_text)
print(f"Detected window: {sell_window}")
print("✅ CORRECT" if sell_window == "sell_overview" else "❌ WRONG")

# Test with pure buy overview
print("\n" + "="*60)
print("Testing with pure BUY overview text:\n")

buy_text = """Central Market 2025.10.11 14.30 Purchased Test Item x10 for 100,000 Silver Transaction of Test Item x10 worth 100,000 Silver has been completed Orders Completed"""

buy_window = detect_window_type(buy_text)
print(f"Detected window: {buy_window}")
print("✅ CORRECT" if buy_window == "buy_overview" else "❌ WRONG")
