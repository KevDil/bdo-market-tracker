#!/usr/bin/env python3
"""
EXHAUSTIVE per-ROI EasyOCR parameter optimization.
Tests ALL reasonable parameter combinations for EACH ROI type individually.

SAFETY: Uses only GPU-safe values to prevent system freeze.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import cv2
import time
import numpy as np
from itertools import product

print("="*80)
print("EXHAUSTIVE PER-ROI EASYOCR OPTIMIZATION")
print("="*80)

# Initialize EasyOCR
try:
    import easyocr
    print("✅ EasyOCR imported")
except ImportError:
    print("❌ EasyOCR not found!")
    sys.exit(1)

# Check GPU
import torch
if torch.cuda.is_available():
    gpu_name = torch.cuda.get_device_name(0)
    print(f"✅ GPU: {gpu_name}")
else:
    print("⚠️  CPU mode (slow!)")

# Initialize reader
print("\n📋 Initializing EasyOCR reader...")
reader = easyocr.Reader(['en'], gpu=True)
print("✅ Reader initialized")

# Load test images (use debug preprocessed images)
print("\n📁 Loading test images...")
test_images = {
    'warehouse_buy': 'debug/debug_warehouse_buy_item_proc.png',
    'warehouse_sell': 'debug/debug_warehouse_sell_item_proc.png',
    'balance': 'debug/debug_balance_buy_item_proc.png',
    'item_name': 'debug/debug_item_name_buy_item_proc.png',
    'label': 'debug/debug_label_proc.png',
    'log': 'debug/debug_log_proc.png',
    'metrics': 'debug/debug_metrics_proc.png',
}

images = {}
for name, path in test_images.items():
    img_path = Path(path)
    if img_path.exists():
        img = cv2.imread(str(img_path))
        if img is not None:
            # Convert to RGB
            rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            images[name] = rgb
            h, w = img.shape[:2]
            pixels = h * w
            print(f"   ✅ {name:20s}: {w:4d}x{h:3d} = {pixels:7,} px")
        else:
            print(f"   ⚠️  {name:20s}: Failed to load")
    else:
        print(f"   ⚠️  {name:20s}: Not found")

if not images:
    print("\n❌ No test images loaded!")
    sys.exit(1)

print(f"\n✅ Loaded {len(images)} test images")

# =============================================================================
# PARAMETER SEARCH SPACE (TWO-PHASE APPROACH)
# =============================================================================

# PHASE 1: PRIMARY PARAMETERS (most impactful)
# These are tested exhaustively per ROI

CANVAS_SIZES = {
    'warehouse_sell': [280, 320, 380, 450, 500, 550],       # TINY (4.8k px)
    'warehouse_buy': [400, 450, 500, 550, 600, 700],        # SMALL (14.8k px)
    'balance': [400, 450, 500, 550, 600, 700],              # SMALL (13k px)
    'item_name': [450, 500, 550, 600, 700, 800],            # MEDIUM (16k px)
    'label': [600, 700, 800, 900, 1000, 1200],              # LARGE (92k px)
    'log': [900, 1000, 1200, 1400, 1600],                   # HUGE (182k px)
    'metrics': [600, 700, 800, 900, 1000],                  # MEDIUM-LARGE (metrics ROI)
}

TEXT_THRESHOLDS = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]
BATCH_SIZES = [2, 3, 4, 6, 8]  # RTX 4070 can handle up to 8

# PHASE 2: SECONDARY PARAMETERS (fine-tuning)
# These use defaults in Phase 1, then optimized for top configs

CONTRAST_THS_PHASE2 = [0.22, 0.26, 0.28, 0.32]
ADJUST_CONTRAST_PHASE2 = [0.25, 0.30, 0.35, 0.40, 0.50]
LOW_TEXT_PHASE2 = [0.32, 0.36, 0.40, 0.44]
LINK_THRESHOLD_PHASE2 = [0.32, 0.36, 0.40]

# PHASE 1: Use these defaults for secondary params
DEFAULT_CONTRAST_THS = 0.28
DEFAULT_ADJUST_CONTRAST = 0.30
DEFAULT_LOW_TEXT = 0.36
DEFAULT_LINK_THRESHOLD = 0.36

# Fixed parameters
PARAGRAPH = False  # Always False for BDO (single-line ROIs)
DETAIL = 1  # Detection detail level

# =============================================================================
# WARMUP GPU
# =============================================================================

print("\n🔥 Warming up GPU with 5 dummy runs...")
warmup_img = list(images.values())[0]
for i in range(5):
    _ = reader.readtext(warmup_img, canvas_size=500, text_threshold=0.6, batch_size=4)
    print(f"   Warmup {i+1}/5 complete")
print("✅ GPU warmed up!\n")

# =============================================================================
# EXHAUSTIVE SEARCH PER ROI
# =============================================================================

results = {}

for img_name, img in images.items():
    print("="*80)
    print(f"🔬 PHASE 1: PRIMARY PARAMETERS - {img_name}")
    print("="*80)
    
    # Get parameter ranges for this ROI
    canvas_range = CANVAS_SIZES.get(img_name, [500, 700, 900])
    
    # PHASE 1: Test primary parameters only (canvas, threshold, batch)
    param_combinations_phase1 = list(product(
        canvas_range,
        TEXT_THRESHOLDS,
        BATCH_SIZES,
    ))
    
    total_configs_phase1 = len(param_combinations_phase1)
    print(f"📊 Testing {total_configs_phase1} primary configurations...")
    print()
    
    # Test each Phase 1 configuration
    config_results_phase1 = []
    
    for i, (canvas, thresh, batch) in enumerate(param_combinations_phase1):
        # Run 3 times for stable measurement
        times = []
        last_result = None
        
        for run in range(3):
            try:
                start = time.time()
                result = reader.readtext(
                    img,
                    detail=DETAIL,
                    paragraph=PARAGRAPH,
                    canvas_size=canvas,
                    text_threshold=thresh,
                    batch_size=batch,
                    contrast_ths=DEFAULT_CONTRAST_THS,
                    adjust_contrast=DEFAULT_ADJUST_CONTRAST,
                    low_text=DEFAULT_LOW_TEXT,
                    link_threshold=DEFAULT_LINK_THRESHOLD,
                )
                elapsed = (time.time() - start) * 1000
                times.append(elapsed)
                last_result = result
            except Exception as e:
                print(f"   ⚠️  Config {i+1}/{total_configs_phase1} FAILED: {e}")
                times.append(9999)  # Penalty
                break
        
        if not times:
            continue
        
        avg_time = np.mean(times)
        
        # Extract text
        texts = []
        if last_result:
            for entry in last_result:
                if len(entry) >= 2:
                    texts.append(entry[1])
        extracted_text = " ".join(texts)
        
        config_results_phase1.append({
            'canvas': canvas,
            'threshold': thresh,
            'batch': batch,
            'contrast_ths': DEFAULT_CONTRAST_THS,
            'adjust_contrast': DEFAULT_ADJUST_CONTRAST,
            'low_text': DEFAULT_LOW_TEXT,
            'link_threshold': DEFAULT_LINK_THRESHOLD,
            'avg_time': avg_time,
            'text': extracted_text,
        })
        
        # Progress update every 20 configs
        if (i + 1) % 20 == 0 or (i + 1) == total_configs_phase1:
            print(f"   Progress: {i+1}/{total_configs_phase1} configs tested ({(i+1)/total_configs_phase1*100:.1f}%)")
    
    # Sort by speed
    config_results_phase1.sort(key=lambda x: x['avg_time'])
    
    print()
    print(f"✅ Phase 1 complete! Top 3 configs:")
    for rank, cfg in enumerate(config_results_phase1[:3], 1):
        print(f"   {rank}. {cfg['avg_time']:6.1f}ms | canvas={cfg['canvas']}, thresh={cfg['threshold']:.2f}, batch={cfg['batch']}")
    
    # =============================================================================
    # PHASE 2: FINE-TUNE SECONDARY PARAMETERS FOR TOP 3 CONFIGS
    # =============================================================================
    
    print()
    print("="*80)
    print(f"🔬 PHASE 2: SECONDARY PARAMETERS - {img_name}")
    print("="*80)
    
    top_3_configs = config_results_phase1[:3]
    config_results_phase2 = []
    
    for top_idx, top_cfg in enumerate(top_3_configs, 1):
        print(f"\n🎯 Fine-tuning config #{top_idx} (canvas={top_cfg['canvas']}, thresh={top_cfg['threshold']}, batch={top_cfg['batch']})...")
        
        # Generate secondary parameter combinations
        secondary_combinations = list(product(
            CONTRAST_THS_PHASE2,
            ADJUST_CONTRAST_PHASE2,
            LOW_TEXT_PHASE2,
            LINK_THRESHOLD_PHASE2,
        ))
        
        total_secondary = len(secondary_combinations)
        print(f"   Testing {total_secondary} secondary combinations...")
        
        for i, (contrast_ths, adjust_contrast, low_text, link_threshold) in enumerate(secondary_combinations):
            # Run 3 times
            times = []
            last_result = None
            
            for run in range(3):
                try:
                    start = time.time()
                    result = reader.readtext(
                        img,
                        detail=DETAIL,
                        paragraph=PARAGRAPH,
                        canvas_size=top_cfg['canvas'],
                        text_threshold=top_cfg['threshold'],
                        batch_size=top_cfg['batch'],
                        contrast_ths=contrast_ths,
                        adjust_contrast=adjust_contrast,
                        low_text=low_text,
                        link_threshold=link_threshold,
                    )
                    elapsed = (time.time() - start) * 1000
                    times.append(elapsed)
                    last_result = result
                except Exception as e:
                    times.append(9999)
                    break
            
            if not times:
                continue
            
            avg_time = np.mean(times)
            
            # Extract text
            texts = []
            if last_result:
                for entry in last_result:
                    if len(entry) >= 2:
                        texts.append(entry[1])
            extracted_text = " ".join(texts)
            
            config_results_phase2.append({
                'canvas': top_cfg['canvas'],
                'threshold': top_cfg['threshold'],
                'batch': top_cfg['batch'],
                'contrast_ths': contrast_ths,
                'adjust_contrast': adjust_contrast,
                'low_text': low_text,
                'link_threshold': link_threshold,
                'avg_time': avg_time,
                'text': extracted_text,
            })
    
    # Combine Phase 1 and Phase 2 results
    all_configs = config_results_phase1 + config_results_phase2
    all_configs.sort(key=lambda x: x['avg_time'])
    
    # Store results
    results[img_name] = all_configs
    
    print()
    print(f"✅ Phase 2 complete! Total configs tested: {len(all_configs)}")
    
    # Print TOP 10 fastest configs
    print()
    print(f"🏆 TOP 10 FASTEST CONFIGS for {img_name}:")
    print("-" * 80)
    for rank, cfg in enumerate(all_configs[:10], 1):
        print(f"{rank:2d}. {cfg['avg_time']:6.1f}ms | "
              f"canvas={cfg['canvas']:4d}, thresh={cfg['threshold']:.2f}, batch={cfg['batch']}, "
              f"contrast={cfg['contrast_ths']:.2f}, adjust={cfg['adjust_contrast']:.2f}")
        print(f"     Text: {cfg['text'][:70]}")
    print()

# =============================================================================
# FINAL SUMMARY
# =============================================================================

print("="*80)
print("📊 FINAL RECOMMENDATIONS PER ROI")
print("="*80)

for img_name, configs in results.items():
    if not configs:
        continue
    
    best = configs[0]
    print()
    print(f"🎯 {img_name}:")
    print(f"   ⏱️  Best Time: {best['avg_time']:.1f}ms")
    print(f"   📐 canvas_size = {best['canvas']}")
    print(f"   🎚️  text_threshold = {best['threshold']}")
    print(f"   📦 batch_size = {best['batch']}")
    print(f"   🔆 contrast_ths = {best['contrast_ths']}")
    print(f"   🎨 adjust_contrast = {best['adjust_contrast']}")
    print(f"   🔤 low_text = {best['low_text']}")
    print(f"   🔗 link_threshold = {best['link_threshold']}")
    print(f"   📝 Text: {best['text'][:60]}...")

# =============================================================================
# SAVE RESULTS TO FILE
# =============================================================================

output_file = Path("docs/EASYOCR_EXHAUSTIVE_RESULTS_2025-10-22.md")
output_file.parent.mkdir(exist_ok=True)

with open(output_file, 'w', encoding='utf-8') as f:
    f.write("# Exhaustive EasyOCR Parameter Optimization Results\n\n")
    f.write(f"**Date:** 2025-10-22\n")
    f.write(f"**GPU:** {gpu_name if torch.cuda.is_available() else 'CPU'}\n")
    f.write(f"**Total Configurations Tested:** {sum(len(c) for c in results.values())}\n\n")
    f.write("---\n\n")
    
    for img_name, configs in results.items():
        if not configs:
            continue
        
        f.write(f"## {img_name}\n\n")
        f.write(f"**Total Configs Tested:** {len(configs)}\n\n")
        
        # Top 20 results
        f.write(f"### Top 20 Fastest Configurations\n\n")
        f.write("| Rank | Time | Canvas | Threshold | Batch | Contrast | Adjust | LowText | Link | Text Preview |\n")
        f.write("|------|------|--------|-----------|-------|----------|--------|---------|------|-------------|\n")
        
        for rank, cfg in enumerate(configs[:20], 1):
            f.write(f"| {rank} | {cfg['avg_time']:.1f}ms | {cfg['canvas']} | {cfg['threshold']:.2f} | "
                   f"{cfg['batch']} | {cfg['contrast_ths']:.2f} | {cfg['adjust_contrast']:.2f} | "
                   f"{cfg['low_text']:.2f} | {cfg['link_threshold']:.2f} | {cfg['text'][:40]}... |\n")
        
        f.write("\n")
        
        # Best config summary
        best = configs[0]
        f.write(f"### ⭐ Recommended Configuration\n\n")
        f.write(f"```python\n")
        f.write(f"# {img_name} (Fastest: {best['avg_time']:.1f}ms)\n")
        f.write(f"canvas_size = {best['canvas']}\n")
        f.write(f"text_threshold = {best['threshold']}\n")
        f.write(f"batch_size = {best['batch']}\n")
        f.write(f"contrast_ths = {best['contrast_ths']}\n")
        f.write(f"adjust_contrast = {best['adjust_contrast']}\n")
        f.write(f"low_text = {best['low_text']}\n")
        f.write(f"link_threshold = {best['link_threshold']}\n")
        f.write(f"```\n\n")
        f.write(f"**Extracted Text:** `{best['text']}`\n\n")
        f.write("---\n\n")

print()
print("="*80)
print(f"✅ Results saved to: {output_file}")
print("="*80)
