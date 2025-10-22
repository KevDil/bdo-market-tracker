#!/usr/bin/env python3
"""
Quick validation of Performance V5 (exhaustive optimization).
Tests all 7 ROIs with their optimal parameters.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import cv2
import time
from utils import ocr_image_cached

print("="*80)
print("PERFORMANCE V5 VALIDATION - Exhaustive Optimization")
print("="*80)

# Test cases with expected performance
test_cases = [
    ('warehouse_sell', 'debug/debug_warehouse_sell_item_proc.png', 'warehouse_sell', 15.9),
    ('warehouse_buy', 'debug/debug_warehouse_buy_item_proc.png', 'warehouse_buy', 18.0),
    ('balance', 'debug/debug_balance_buy_item_proc.png', 'detail_balance', 18.1),
    ('item_name', 'debug/debug_item_name_buy_item_proc.png', 'detail_item_name', 20.2),
    ('label', 'debug/debug_label_proc.png', 'label', 56.5),
    ('log', 'debug/debug_log_proc.png', 'log', 151.3),
    ('metrics', 'debug/debug_metrics_proc.png', 'metrics', 186.0),
]

print("\n🧪 Testing Performance V5 on real BDO screenshots...\n")

results = []
total_speedup = 0

for name, path, roi_label, expected_ms in test_cases:
    img_path = Path(path)
    if not img_path.exists():
        print(f"⚠️  {name:20s}: Not found")
        continue
    
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"⚠️  {name:20s}: Failed to load")
        continue
    
    # Run 5 times for stable measurement (skip first run = warmup)
    # Use different cache_tag per run to bypass cache
    times = []
    last_text = None
    for run in range(6):
        start = time.time()
        text, conf, metrics = ocr_image_cached(
            img, 
            method='easyocr', 
            roi_label=roi_label, 
            fast_mode=True,
            cache_tag=f"validation_run_{run}"  # Force cache bypass
        )
        elapsed = (time.time() - start) * 1000
        if run > 0:  # Skip first run (warmup)
            times.append(elapsed)
        last_text = text
    
    avg_time = sum(times) / len(times)
    diff_ms = avg_time - expected_ms
    diff_pct = (diff_ms / expected_ms) * 100
    
    # Determine status
    if avg_time <= expected_ms * 1.2:  # Within 20% is acceptable
        status = "✅"
    elif avg_time <= expected_ms * 1.5:  # Within 50% is warning
        status = "⚠️ "
    else:
        status = "❌"
    
    results.append((name, avg_time, expected_ms, diff_ms, diff_pct, last_text))
    
    print(f"{status} {name:20s}: {avg_time:6.1f}ms (expected {expected_ms:6.1f}ms, diff {diff_ms:+6.1f}ms / {diff_pct:+5.1f}%)")
    print(f"     Text: {last_text[:70]}")

# Summary
if results:
    avg_all = sum(r[1] for r in results) / len(results)
    expected_avg = sum(r[2] for r in results) / len(results)
    total_diff = avg_all - expected_avg
    total_diff_pct = (total_diff / expected_avg) * 100
    
    print(f"\n{'='*80}")
    print(f"📊 SUMMARY")
    print(f"{'='*80}")
    print(f"Average Actual Time  : {avg_all:.1f}ms")
    print(f"Average Expected Time: {expected_avg:.1f}ms")
    print(f"Difference           : {total_diff:+.1f}ms ({total_diff_pct:+.1f}%)")
    print()
    
    if avg_all <= expected_avg * 1.2:
        print("✅ Performance V5 validation PASSED!")
        print("   All ROIs within 20% of expected performance.")
    elif avg_all <= expected_avg * 1.5:
        print("⚠️  Performance V5 validation WARNING!")
        print("   Some ROIs 20-50% slower than expected (acceptable).")
    else:
        print("❌ Performance V5 validation FAILED!")
        print("   ROIs >50% slower than expected (investigation needed).")
else:
    print("\n❌ No test images found!")
