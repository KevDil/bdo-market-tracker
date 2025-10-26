#!/usr/bin/env python3
"""
Test DIRECT extract_text() calls (bypassing cache) to measure pure OCR speed.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import cv2
import time
from utils import extract_text

print("="*80)
print("Direct OCR Test (No Cache)")
print("="*80)

# Test images
tests = [
    ('Balance', 'debug/debug_balance_buy_item_proc.png'),
    ('Warehouse', 'debug/debug_warehouse_buy_item_proc.png'),
    ('Item Name', 'debug/debug_item_name_buy_item_proc.png'),
    ('Label', 'debug/debug_label_proc.png'),
]

print("\n🧪 Testing DIRECT extract_text() on real BDO screenshots...\n")

results = []
for name, path in tests:
    img_path = Path(path)
    if not img_path.exists():
        print(f"⚠️  {name:15s}: Not found")
        continue
    
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"⚠️  {name:15s}: Failed to load")
        continue
    
    # Run DIRECT OCR (5 times for stable measurement)
    times = []
    last_text = None
    for _ in range(5):
        start = time.time()
        text = extract_text(img, use_roi=False, method='easyocr', fast_mode=True)
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
        last_text = text
    
    avg_time = sum(times) / len(times)
    results.append((name, avg_time, last_text))
    
    print(f"✅ {name:15s}: {avg_time:6.1f}ms | Text: {last_text[:60]}")

# Summary
if results:
    avg_all = sum(r[1] for r in results) / len(results)
    print(f"\n⏱️  Average Direct OCR Time: {avg_all:.1f}ms")
    print("\n" + "="*80)
    print("✅ TEST COMPLETE")
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
