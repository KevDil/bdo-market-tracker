import cv2

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

import os
import sys
# Ensure project root is on sys.path
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from utils import extract_text, preprocess
from tracker import MarketTracker

BASE = os.path.join(os.getcwd(), 'dev-screenshots', 'listings_and_preorders')
FILES = [
    'full_buy.png',
    'partial_buy.png',
    'no_buy.png',
    'full_sell.png',
    'partial_sell.png',
    'no_sell.png',
]

def ocr_file(path):
    img = cv2.imread(path)
    if img is None:
        raise FileNotFoundError(path)
    proc = preprocess(img)
    text = extract_text(proc)
    return text

if __name__ == '__main__':
    mt = MarketTracker(debug=True)
    for f in FILES:
        p = os.path.join(BASE, f)
        try:
            text = ocr_file(p)
        except Exception as e:
            print(f"[ERROR] {f}: {e}")
            continue
        wtype = 'unknown'
        try:
            from utils import detect_window_type
            wtype = detect_window_type(text)
        except Exception:
            pass
        print('\n===', f, '===', 'window=', wtype)
        # debug preview
        print('TEXT PREVIEW:\n', (text or '')[:1200].replace('\n',' '))
        buy = mt._extract_buy_ui_metrics(text)
        sell = mt._extract_sell_ui_metrics(text)
        if buy:
            print('BUY metrics:')
            for k, v in buy.items():
                print(' ', v)
        if sell:
            print('SELL metrics:')
            for k, v in sell.items():
                print(' ', v)
        if not buy and not sell:
            print('No metrics found')
