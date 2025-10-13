import sys, os

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from parsing import extract_details_from_entry

cases = [
    ('2025.10.10 11.37', 'Transaction of Magical Shard x65 worth 182,241,150 Silver has been completed.'),
    ('2025.10.10 11.37', "Purchased Dehkia's Fragment x1 for 51,500,000 Silver"),
    ('2025.10.10 11.37', "Purchased Dehkia's Fragment x3 for 153,000,000 Silver 31.590"),
]

for ts, txt in cases:
    print('INPUT:', txt)
    print('OUTPUT:', extract_details_from_entry(ts, txt))
