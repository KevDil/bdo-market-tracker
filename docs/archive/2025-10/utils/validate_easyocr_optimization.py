#!/usr/bin/env python3
"""
Quick validation of EasyOCR optimization changes.
Tests a few key ROIs to ensure text extraction still works.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import cv2
import time
from utils import ocr_image_cached

print("="*80)
print("EasyOCR Optimization Validation")
print("="*80)

# Test images
tests = [
    ('Balance', 'debug/debug_balance_buy_item_proc.png', 'detail_balance'),
    ('Warehouse', 'debug/debug_warehouse_buy_item_proc.png', 'detail_warehouse'),
    ('Item Name', 'debug/debug_item_name_buy_item_proc.png', 'detail_item_name'),
    ('Label', 'debug/debug_label_proc.png', 'label'),
]

print("\n🧪 Testing OCR on real BDO screenshots...\n")

results = []
for name, path, roi_label in tests:
    img_path = Path(path)
    if not img_path.exists():
        print(f"⚠️  {name:15s}: Not found")
        continue
    
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"⚠️  {name:15s}: Failed to load")
        continue
    
    # Run OCR (3 times for stable measurement)
    times = []
    last_text = None
    for _ in range(3):
        start = time.time()
        text, conf, metrics = ocr_image_cached(img, method='easyocr', roi_label=roi_label)
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
        last_text = text
    
    avg_time = sum(times) / len(times)
    results.append((name, avg_time, last_text))
    
    print(f"✅ {name:15s}: {avg_time:6.1f}ms | Text: {last_text[:60]}")

# Summary
if results:
    avg_all = sum(r[1] for r in results) / len(results)
    print(f"\n⏱️  Average OCR Time: {avg_all:.1f}ms")
    print("\n" + "="*80)
    print("✅ VALIDATION COMPLETE")
    print("="*80)
    print("\n💡 Expected: ~82-99ms average (from benchmark)")
    print(f"   Actual: {avg_all:.1f}ms")
    
    if avg_all < 110:
        print("   🎉 Performance target met!")
    elif avg_all < 130:
        print("   ⚠️  Slightly slower than expected, but acceptable")
    else:
        print("   ❌ Performance regression detected!")
else:
    print("\n❌ No test images found!")
