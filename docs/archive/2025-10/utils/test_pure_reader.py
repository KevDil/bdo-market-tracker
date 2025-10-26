#!/usr/bin/env python3
"""
Test PURE reader.readtext() calls (bypassing extract_text) to match benchmark.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import cv2
import time
from utils import reader

print("="*80)
print("Pure EasyOCR Reader Test (Exact Benchmark Match)")
print("="*80)

# Test images (same as benchmark)
tests = [
    ('Balance', 'debug/debug_balance_buy_item_proc.png'),
    ('Warehouse', 'debug/debug_warehouse_buy_item_proc.png'),
    ('Item Name', 'debug/debug_item_name_buy_item_proc.png'),
    ('Label', 'debug/debug_label_proc.png'),
]

print("\n🔥 Warming up GPU with 3 dummy runs...\n")

# Benchmark winner params
CANVAS = 500
THRESHOLD = 0.60
BATCH = 4

# Load first image for warmup
warmup_img = cv2.imread(str(Path(tests[0][1])))
warmup_rgb = cv2.cvtColor(warmup_img, cv2.COLOR_BGR2RGB)

# Warmup runs
for i in range(3):
    _ = reader.readtext(warmup_rgb, canvas_size=CANVAS, text_threshold=THRESHOLD, batch_size=BATCH)
    print(f"  Warmup run {i+1}/3 complete")

print("✅ GPU warmed up!\n")
print("🧪 Testing PURE reader.readtext() on real BDO screenshots...\n")

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
    
    # Convert to RGB (OpenCV loads as BGR)
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Label needs slightly more canvas
    canvas = 700 if name == 'Label' else CANVAS
    
    # Run PURE reader.readtext() (5 times for stable measurement)
    times = []
    last_text = None
    for _ in range(5):
        start = time.time()
        result = reader.readtext(
            rgb,
            detail=1,
            canvas_size=canvas,
            text_threshold=THRESHOLD,
            paragraph=False,
            batch_size=BATCH,
            contrast_ths=0.28,
            adjust_contrast=0.30,  # Match benchmark exactly
            low_text=0.36,
            link_threshold=0.36,
        )
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
        # Extract text
        last_text = ' '.join([text for (bbox, text, conf) in result])
    
    avg_time = sum(times) / len(times)
    results.append((name, avg_time, last_text))
    
    print(f"✅ {name:15s}: {avg_time:6.1f}ms | Text: {last_text[:60]}")

# Summary
if results:
    avg_all = sum(r[1] for r in results) / len(results)
    print(f"\n⏱️  Average Pure OCR Time: {avg_all:.1f}ms")
    print("\n" + "="*80)
    print("✅ TEST COMPLETE")
    print("="*80)
    print("\n💡 Expected: ~82-99ms average (from benchmark)")
    print(f"   Actual: {avg_all:.1f}ms")
    
    if avg_all < 100:
        print("   🎉 Performance target met!")
    elif avg_all < 130:
        print("   ⚠️  Slightly slower than expected, but acceptable")
    else:
        print("   ❌ Performance regression detected!")
else:
    print("\n❌ No test images found!")
