"""Test: First snapshot should NOT adjust old transactions"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass

from tracker import MarketTracker

# Simulate first overview with BOTH old (10:56) and new (11:05) transactions
text = """Central Market @ Sell Warehouse Balance 76,570,794,077
2025.10.11 11.05 2025.10.11 10.56 2025.10.11 10.50 2025.10.11 10.50
Listed Magical Shard x200 for 640,000,000 Silver
Transaction of Magical Shard x130 worth 367,942,575 Silver has been completed
Placed order of Spirit's Leaf x5,000 for 20,300,000 Silver
Withdrew order of Spirit's Leaf x985 for 3,999,100 Silver
Items Listed   636 Sales Completed   120 Collect All"""

print("=" * 60)
print("TEST: First snapshot with old transaction (10:56)")
print("=" * 60)
print("\nExpected behavior:")
print("- 130x Magical Shard should keep timestamp 10:56 (NOT adjusted to 11:05)")
print("- Reason: Only one timestamp for Magical Shard (no drift)")
print("\nRunning test...\n")

mt = MarketTracker(debug=True)
mt.process_ocr_text(text)

print("\n" + "=" * 60)
print("Check ocr_log.txt for:")
print("- 'structured: 2025-10-11 10:56:00 transaction' (CORRECT)")
print("- 'DB SAVE: ... ts=2025-10-11 10:56:00' (CORRECT)")
print("- NOT 'ts=2025-10-11 11:05:00' (WRONG)")
print("=" * 60)
