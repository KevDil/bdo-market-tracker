"""Test: Exact reproduction of user's scenario"""
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

# Exact OCR from user's first scan (11:07:17)
text1 = """Central Market Ww Warehouse Balance 76,570,794,077 Manage Warehouse 
2025.10.11 11.05 2025.10.11 10.56 2025.10.11 10.50 2025.10.11 10.50 
Listed Magical Shard x2OO for 640,000,000 Silver: The price of enhancement m_. 
Transaction of Magical Shard xl3O worth 367,942,575 Silver has been complet___ 
Placed order of Spirit's Leaf x5,000 for 20,300,000 Silver 
Withdrew order of Spirit's Leaf x985 for 3,999,100 silver 
Warehouse Capacity 4,267.9 / 11,000 VT 31.590 Sell 206 = Pearl Item Selling Limit 
Sell Enter search term Enter a search term: Items Listed   636 Sales Completed   120 Collect AlI"""

print("=" * 80)
print("TEST: User scenario - First overview with old transaction")
print("=" * 80)
print("\nScenario:")
print("- User opens market window at 11:07")
print("- Old transaction visible: 130x Magical Shard sold at 10:56 for 367,942,575")
print("- New listing visible: 200x Magical Shard listed at 11:05 for 640,000,000")
print("\nExpected:")
print("- 130x Magical Shard should have timestamp 10:56 (NOT 11:05)")
print("\n" + "=" * 80)
print("Running first scan...")
print("=" * 80 + "\n")

mt = MarketTracker(debug=True)
mt.process_ocr_text(text1)

print("\n" + "=" * 80)
print("CHECK THE LOGS ABOVE FOR:")
print("- 'first snapshot: item 'magical shard' has drift' -> Should NOT appear!")
print("- 'structured: 2025-10-11 10:XX:00 transaction item='Magical Shard'")
print("- 'DB SAVE: ... ts=2025-10-11 10:56:00' (or 10:50 depending on parsing)")
print("=" * 80)
