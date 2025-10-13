import sys, os

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from tracker import MarketTracker

text = (
    "Central Market Ww Warehouse Balance 100,073,705,073 Buy Manage WWarehouse Warehouse Capacity 1 6,616.6 11,000 VT Sell Pearl Item Selling Limit "
    "2025.10.10 11:38 2025.10.10 11.38 2025.10.10 11.37 2025.10.10 11.37 "
    "Placed order of Black Stone Powder x5,000 for 23,500,000 Silver "
    "Transaction of Black Stone Powder x5,000 worth 23,800,000 Silver has been completed. "
    "Placed order of Dehkias Fragment x1 for 51,000,000 Silver "
    "Purchased Dehkia's Fragment x3 for 153,000,000 Silver 31.590 Sell Enter a search term Enter a search term. Orders 108010 Orders Completed 2633 "
)

mt = MarketTracker(debug=True)
mt.process_ocr_text(text)
print('Done.')
