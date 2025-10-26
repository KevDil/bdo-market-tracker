#!/usr/bin/env python3
"""
EasyOCR Parameter Tuning Benchmark

Tests verschiedene canvas_size und threshold-Kombinationen
auf echten BDO Screenshots um die optimale Balance zwischen
Geschwindigkeit und Accuracy zu finden.

Usage:
    python scripts/utils/benchmark_easyocr_tuning.py
"""

import sys
import os
import time
from pathlib import Path
import cv2
import numpy as np

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

print("="*80)
print("EASYOCR PARAMETER TUNING BENCHMARK")
print("="*80)

# Import EasyOCR
try:
    import easyocr
    print(f"✅ EasyOCR imported")
except ImportError:
    print("❌ EasyOCR not installed!")
    sys.exit(1)

# Check GPU
import torch
gpu_available = torch.cuda.is_available()
if gpu_available:
    print(f"✅ GPU: {torch.cuda.get_device_name(0)}")
else:
    print("⚠️  GPU not available - using CPU")

# Initialize reader
print("\n📋 Initializing EasyOCR reader...")
reader = easyocr.Reader(['en'], gpu=gpu_available, verbose=False)
print("✅ Reader initialized")

# Load test images
print("\n📁 Loading test images...")
debug_dir = Path("debug")

test_images = {
    # Small ROIs (~5k-16k px)
    'warehouse_sell': debug_dir / "debug_warehouse_sell_item_proc.png",
    'warehouse_buy': debug_dir / "debug_warehouse_buy_item_proc.png",
    'balance': debug_dir / "debug_balance_buy_item_proc.png",
    'item_name': debug_dir / "debug_item_name_buy_item_proc.png",
    
    # Medium ROIs (~40k-60k px)
    'preorder_input': debug_dir / "debug_preorder_input_proc.png",
    
    # Large ROIs (>100k px)
    'label': debug_dir / "debug_label_proc.png",
    'log': debug_dir / "debug_log_proc.png",
}

images = {}
for name, path in test_images.items():
    if path.exists():
        img = cv2.imread(str(path))
        if img is not None:
            h, w = img.shape[:2]
            px_count = h * w
            images[name] = img
            print(f"   ✅ {name:20s}: {w:4d}x{h:3d} = {px_count:6,d} px")
        else:
            print(f"   ⚠️  {name:20s}: Failed to load")
    else:
        print(f"   ⚠️  {name:20s}: Not found")

if not images:
    print("\n❌ No test images found!")
    sys.exit(1)

print(f"\n✅ Loaded {len(images)} test images")

# Define test configurations
# Format: (canvas_size, text_threshold, batch_size, description)
configs = [
    # Current baseline (from utils.py)
    (700, 0.68, 3, "CURRENT - Small ROI"),
    (800, 0.68, 3, "CURRENT - Detail ROI"),
    (1200, 0.68, 3, "CURRENT - Medium ROI"),
    (1500, 0.68, 3, "CURRENT - Large ROI"),
    
    # Aggressive speed optimizations
    (600, 0.65, 3, "FAST - Lower canvas + threshold"),
    (650, 0.62, 3, "FAST+ - Balanced"),
    (700, 0.60, 3, "FAST++ - More aggressive"),
    
    # Accuracy-focused
    (800, 0.72, 3, "ACCURATE - Higher threshold"),
    (900, 0.70, 2, "ACCURATE+ - Bigger canvas, lower batch"),
    
    # Extreme speed (may lose accuracy)
    (500, 0.60, 4, "EXTREME - Maximum speed"),
    (550, 0.58, 4, "EXTREME+ - Even faster"),
]

print(f"\n🧪 Testing {len(configs)} configurations...")
print("\n" + "="*80)

results = []

for config_idx, (canvas, thresh, batch, desc) in enumerate(configs, 1):
    print(f"\n{'='*80}")
    print(f"Config {config_idx}/{len(configs)}: {desc}")
    print(f"  canvas_size={canvas}, text_threshold={thresh}, batch_size={batch}")
    print(f"{'='*80}\n")
    
    config_results = {
        'config': desc,
        'canvas': canvas,
        'threshold': thresh,
        'batch': batch,
        'times': {},
        'texts': {},
        'avg_time': 0,
    }
    
    times = []
    
    for img_name, img in images.items():
        # Convert to RGB
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        # Warmup run (nicht gemessen)
        if config_idx == 1:
            _ = reader.readtext(
                rgb,
                detail=1,
                paragraph=False,
                text_threshold=thresh,
                canvas_size=canvas,
                batch_size=batch,
                contrast_ths=0.28,
                adjust_contrast=0.30,
                low_text=0.36,
                link_threshold=0.36,
            )
        
        # Measured runs (3x for stability)
        run_times = []
        for run in range(3):
            start = time.time()
            res = reader.readtext(
                rgb,
                detail=1,
                paragraph=False,
                text_threshold=thresh,
                canvas_size=canvas,
                batch_size=batch,
                contrast_ths=0.28,
                adjust_contrast=0.30,
                low_text=0.36,
                link_threshold=0.36,
            )
            elapsed = (time.time() - start) * 1000
            run_times.append(elapsed)
        
        # Calculate mean time
        mean_time = np.mean(run_times)
        times.append(mean_time)
        
        # Extract text
        texts = []
        for entry in res:
            if len(entry) >= 2:
                texts.append(entry[1])
        
        extracted_text = " ".join(texts)
        
        config_results['times'][img_name] = mean_time
        config_results['texts'][img_name] = extracted_text
        
        print(f"  {img_name:20s}: {mean_time:6.1f}ms | Text: {extracted_text[:60]}")
    
    avg_time = np.mean(times)
    config_results['avg_time'] = avg_time
    results.append(config_results)
    
    print(f"\n  ⏱️  Average: {avg_time:.1f}ms")

# Summary
print("\n" + "="*80)
print("📊 BENCHMARK RESULTS")
print("="*80)

print("\n⏱️  Performance Ranking (fastest to slowest):")
sorted_results = sorted(results, key=lambda x: x['avg_time'])

baseline_time = None
for idx, r in enumerate(sorted_results, 1):
    # Find baseline
    if "CURRENT" in r['config'] and baseline_time is None:
        baseline_time = r['avg_time']
    
    if baseline_time:
        speedup = baseline_time / r['avg_time']
        speedup_str = f" ({speedup:.2f}x vs baseline)" if speedup != 1.0 else " [BASELINE]"
    else:
        speedup_str = ""
    
    print(f"{idx:2d}. {r['config']:35s}: {r['avg_time']:6.1f}ms{speedup_str}")
    print(f"    canvas={r['canvas']}, threshold={r['threshold']}, batch={r['batch']}")

# Text quality comparison
print("\n" + "="*80)
print("📝 TEXT EXTRACTION QUALITY")
print("="*80)

# Pick one image to compare text quality
comparison_img = 'balance' if 'balance' in images else list(images.keys())[0]
print(f"\nComparing text extraction on: {comparison_img}")
print("-"*80)

baseline_text = None
for r in results:
    if "CURRENT" in r['config'] and baseline_text is None:
        baseline_text = r['texts'].get(comparison_img, "")

for r in sorted_results[:5]:  # Top 5 fastest
    text = r['texts'].get(comparison_img, "")
    match = "✅" if text == baseline_text else "⚠️"
    print(f"\n{match} {r['config']:35s} ({r['avg_time']:.1f}ms)")
    print(f"   Text: {text}")

# Recommendation
print("\n" + "="*80)
print("💡 RECOMMENDATIONS")
print("="*80)

# Find fastest config with same text as baseline
best_config = None
best_speedup = 1.0

for r in sorted_results:
    if r == sorted_results[0]:  # Skip absolute fastest (may lose accuracy)
        continue
    
    # Check if text matches baseline for key images
    text_match = all(
        r['texts'].get(img_name) == results[0]['texts'].get(img_name)
        for img_name in ['balance', 'warehouse_buy', 'item_name']
        if img_name in images
    )
    
    if text_match and baseline_time:
        speedup = baseline_time / r['avg_time']
        if speedup > best_speedup:
            best_speedup = speedup
            best_config = r

if best_config:
    print(f"\n🎯 Best Config: {best_config['config']}")
    print(f"   canvas_size = {best_config['canvas']}")
    print(f"   text_threshold = {best_config['threshold']}")
    print(f"   batch_size = {best_config['batch']}")
    print(f"   Average Time: {best_config['avg_time']:.1f}ms")
    print(f"   Speedup: {best_speedup:.2f}x faster than baseline")
    print(f"   ✅ Text quality maintained")
else:
    print("\n⚠️  No faster config found that maintains text quality")
    print("   Current configuration is already optimal!")

print("\n" + "="*80)
print("✅ BENCHMARK COMPLETE")
print("="*80)
