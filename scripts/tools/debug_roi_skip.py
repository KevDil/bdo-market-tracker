"""Quick debug script to test ROI skipping."""

from tracker import MarketTracker
import numpy as np
from PIL import Image
from unittest.mock import patch
import tracker as tracker_mod

# Create deterministic image (numpy array in BGR format, like mss captures)
np.random.seed(42)
img = np.random.randint(0, 255, (700, 1100, 3), dtype=np.uint8)  # Already numpy array!

# Initialize tracker
t = MarketTracker()
print(f"Initial debug mode: {t.debug}")
t.debug = True
print(f"After setting: {t.debug}")
t._stable_window = 'sell_overview'
t._window_detection_history = ['sell_overview', 'sell_overview']
print(f"Tracker initialized, debug={t.debug}")

# Mock OCR
mock_ocr_text = 'Orders: 10\nOrders Completed: 5\nRemaining Price: 1,000,000 Silver'

import utils as utils_mod

def mock_detect_metrics_roi(img):
    print(f"    [MOCK] detect_metrics_roi called, returning (0, 350, 1100, 700)")
    return (0, 350, 1100, 700)

def mock_ocr_cached(*args, **kwargs):
    print(f"    [MOCK] ocr_image_cached called with roi_label={kwargs.get('roi_label', 'unknown')}")
    return (mock_ocr_text, False, {'cache_size': 0, 'cache_age': 0.0})

with patch.object(utils_mod, 'ocr_image_cached', side_effect=mock_ocr_cached), \
     patch.object(utils_mod, 'detect_window_type', return_value='sell_overview'), \
     patch.object(utils_mod, 'detect_log_roi', return_value=(0, 0, 1100, 350)), \
     patch.object(utils_mod, 'detect_metrics_roi', side_effect=mock_detect_metrics_roi), \
     patch.object(utils_mod, 'detect_window_label_roi', return_value=(0, 0, 1100, 100)):
    
    print("Running 5 scans...")
    for i in range(5):
        print(f"\n=== SCAN {i+1} ===")
        print(f"  Before: log_skips={t._roi_skip_counters.get('log', 0)}, metrics_skips={t._roi_skip_counters.get('metrics', 0)}, pending={t._pending_metrics_refresh}")
        
        t._process_image(img, context='test')
        
        print(f"  After:  log_skips={t._roi_skip_counters.get('log', 0)}, metrics_skips={t._roi_skip_counters.get('metrics', 0)}, pending={t._pending_metrics_refresh}")

print(f"\n\n=== FINAL STATE ===")
print(f"Log skips: {t._roi_skip_counters.get('log', 0)}")
print(f"Metrics skips: {t._roi_skip_counters.get('metrics', 0)}")
print(f"Pending metrics: {t._pending_metrics_refresh}")
print(f"Last signatures: log={t._last_roi_signatures.get('log')}, metrics={t._last_roi_signatures.get('metrics')}")
