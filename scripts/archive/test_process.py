import sys, os

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from tracker import MarketTracker

sample_text = (
"Central Market Ww Warehouse Balance 89,563,100,202 2025.10.09 21.55 2025.10.09 21.55 2025.10.09 21.52 2025.10.09 21.52 "
"Listed Magical Shard x2OO for 676,000,000 Silver. The price of enhancement m_. "
"Transaction of Magical Shard x2OO worth 596,232,000 Silver has been complet___ "
"Placed order of Sealed Black Magic Crystal x886 for 2,516,240,000 Silver "
"Withdrew order of Sealed Black Magic Crystal x516 for 455,120,000 silver _ Warehouse Capacity 4,400.2 11,000 VT Pearl Item Selling Limit 31.590 "
"Sell Sell Buy Z5L Enter a search term_ Enter a search term. Items Listed 699 Sales Completed Colllect All VT Magical Shard Registration Count 200 / Sales Completed 2025 10-0g 3,380,000 Collect Re-list SCCO"
)

mt = MarketTracker(debug=True)
mt.process_ocr_text(sample_text)
print('Done.')
