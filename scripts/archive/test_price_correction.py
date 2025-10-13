import sys, os

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from tracker import MarketTracker

# Simulate Sealed Black Magic Crystal first snapshot with under-read total
text = (
    "Central Market ... "
    "2025.10.10 12.37 2025.10.10 12.37 2025.10.10 12.37 2025.10.10 12.36 "
    "Placed order of Sealed Black Magic Crystal x876 for 2,382,720,000 Silver "  # unit 2,720,000
    "Withdrew order of Sealed Black Magic Crystal x258 for 696,600,000 silver "  # unit 2,700,000
    "Transaction of Sealed Black Magic Crystal x593 worth 601,100,000 Silver has been completed. "  # should be 1,601,100,000
)

mt = MarketTracker(debug=True)
mt.process_ocr_text(text)
print('Done.')
