"""Analyze actual ROI content to optimize OCR parameters."""
from PIL import Image, ImageDraw, ImageFont
import os

debug_path = 'debug'

def analyze_roi(roi_name, window_type):
    """Analyze ROI image and suggest optimizations."""
    filename = f'debug_{roi_name}_{window_type}_orig.png'
    filepath = os.path.join(debug_path, filename)
    
    if not os.path.exists(filepath):
        return None
    
    img = Image.open(filepath)
    w, h = img.size
    pixels = w * h
    
    # Analyze content
    proc_filename = f'debug_{roi_name}_{window_type}_proc.png'
    proc_filepath = os.path.join(debug_path, proc_filename)
    has_preprocessing = os.path.exists(proc_filepath)
    
    # Heuristics for optimization
    suggestions = []
    
    # Very small ROIs (<10k px) - aggressive optimization
    if pixels < 10000:
        suggestions.append("TINY ROI - Use canvas=600, minimal preprocessing")
        optimal_canvas = 600
    # Small ROIs (10k-20k px) - balanced
    elif pixels < 20000:
        suggestions.append("SMALL ROI - Use canvas=700-800")
        optimal_canvas = 700
    # Medium ROIs (20k-50k px) - standard
    else:
        suggestions.append("MEDIUM ROI - Use canvas=800-1000")
        optimal_canvas = 800
    
    # Check aspect ratio
    aspect = w / h if h > 0 else 0
    if aspect > 5:  # Very wide
        suggestions.append(f"WIDE ROI (aspect={aspect:.1f}) - May benefit from paragraph=True")
    elif aspect < 0.5:  # Very tall
        suggestions.append(f"TALL ROI (aspect={aspect:.1f}) - Check if rotation needed")
    
    return {
        'size': (w, h),
        'pixels': pixels,
        'aspect': aspect,
        'has_proc': has_preprocessing,
        'optimal_canvas': optimal_canvas,
        'suggestions': suggestions
    }

print("=" * 80)
print("ROI OPTIMIZATION ANALYSIS")
print("=" * 80)

rois = [
    ('item_name', 'Item Name'),
    ('balance', 'Balance'),
    ('warehouse', 'Warehouse'),
    ('preorder_input', 'Preorder Input'),
]

for window_type in ['sell_item', 'buy_item']:
    print(f"\n{'='*80}")
    print(f"{window_type.upper().replace('_', ' ')} - OPTIMIZATION RECOMMENDATIONS")
    print(f"{'='*80}\n")
    
    for roi_key, roi_display in rois:
        analysis = analyze_roi(roi_key, window_type)
        if analysis:
            print(f"{roi_display}:")
            print(f"  Size: {analysis['size'][0]} x {analysis['size'][1]} = {analysis['pixels']:,} pixels")
            print(f"  Aspect Ratio: {analysis['aspect']:.2f}")
            print(f"  Optimal Canvas: {analysis['optimal_canvas']}")
            print(f"  Current Preprocessing: {'YES' if analysis['has_proc'] else 'NO'}")
            for sug in analysis['suggestions']:
                print(f"  → {sug}")
            print()

# Special analysis for combined approach
print("\n" + "="*80)
print("ALTERNATIVE APPROACHES")
print("="*80)

print("\n1. PARALLEL OCR (Current individual ROIs):")
print("   PRO: Smallest total pixels, can use optimal canvas per ROI")
print("   PRO: Can skip item_name after first scan (cache)")
print("   CON: 3 separate GPU calls = 3x setup overhead")
print("   PERFORMANCE: Item(500ms, once) + Balance(500ms) + Warehouse(200ms) = 700ms after first scan")

print("\n2. COMBINED ROI (One large ROI):")
print("   PRO: Only 1 GPU call = 1x setup overhead")
print("   CON: 4-5x more pixels = slower OCR")
print("   CON: Post-processing to extract individual values")
print("   PERFORMANCE: Estimated 800-1200ms for larger canvas")

print("\n3. SMART SKIP (Skip unchanging fields):")
print("   - Item Name: Cache (DONE ✅)")
print("   - Balance: ALWAYS changes during relist → MUST scan")
print("   - Warehouse: ALWAYS changes during relist → MUST scan")
print("   VERDICT: Can't skip Balance or Warehouse!")

print("\n4. CANVAS OPTIMIZATION (Reduce canvas size further):")
print("   Current: canvas=800 for detail ROIs")
print("   Test: canvas=600 for tiny ROIs (<10k px)")
print("   Risk: May hurt OCR accuracy")
print("   Benefit: ~30-40% faster OCR")

print("\n" + "="*80)
print("RECOMMENDATION")
print("="*80)
print("""
✅ KEEP individual ROI approach (separate Balance + Warehouse scans)
✅ Use canvas=600 for Warehouse ROI (4.8k pixels - TINY!)
✅ Keep canvas=800 for Balance ROI (13k pixels - small)
✅ Item Name already cached (saves 500ms on scans 2+)

Expected Performance:
  Baseline: Item(500ms) + Balance(500ms) + Warehouse(150ms) = 1150ms
  Scan 2+:  Balance(500ms) + Warehouse(150ms) = 650ms

Target: Need Balance OCR from 500ms → 300ms!
How: Switch from EasyOCR to PaddleOCR for Balance ROI (typically 30-40% faster)
""")
