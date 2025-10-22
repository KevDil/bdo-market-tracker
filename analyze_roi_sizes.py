"""Analyze ROI sizes from debug screenshots."""
from PIL import Image
import os

debug_path = 'debug'
rois = ['item_name', 'balance', 'warehouse', 'preorder_input']
types = ['sell_item', 'buy_item']

print("=" * 60)
print("ROI SIZE ANALYSIS")
print("=" * 60)

for window_type in types:
    print(f"\n{window_type.upper().replace('_', ' ')}:")
    print("-" * 60)
    total_pixels = 0
    
    for roi in rois:
        filename = f'debug_{roi}_{window_type}_orig.png'
        filepath = os.path.join(debug_path, filename)
        
        if os.path.exists(filepath):
            img = Image.open(filepath)
            w, h = img.size
            pixels = w * h
            total_pixels += pixels
            print(f"  {roi:20s}: {w:4d} x {h:3d} = {pixels:7,d} pixels")
        else:
            print(f"  {roi:20s}: NOT FOUND")
    
    print(f"  {'TOTAL':20s}: {total_pixels:7,d} pixels")

# Combined ROI analysis
print("\n" + "=" * 60)
print("COMBINED ROI CALCULATION")
print("=" * 60)

for window_type in types:
    print(f"\n{window_type.upper().replace('_', ' ')}:")
    
    # Get full window size
    full_img = Image.open(os.path.join(debug_path, f'debug_{window_type}_full_orig.png'))
    full_w, full_h = full_img.size
    print(f"  Full window: {full_w} x {full_h}")
    
    # Calculate combined ROI based on percentages
    if window_type == 'sell_item':
        x_start = int(full_w * 0.03)
        x_end = int(full_w * 0.45)
        y_start = int(full_h * 0.03)
        y_end = int(full_h * 0.55)
    else:  # buy_item
        x_start = int(full_w * 0.04)
        x_end = int(full_w * 0.45)
        y_start = int(full_h * 0.08)
        y_end = int(full_h * 0.89)
    
    combined_w = x_end - x_start
    combined_h = y_end - y_start
    combined_pixels = combined_w * combined_h
    
    print(f"  Combined ROI: {combined_w} x {combined_h} = {combined_pixels:,} pixels")
    
    # Load individual ROIs to compare
    individual_total = 0
    for roi in rois[:3]:  # Only item_name, balance, warehouse
        filepath = os.path.join(debug_path, f'debug_{roi}_{window_type}_orig.png')
        if os.path.exists(filepath):
            img = Image.open(filepath)
            individual_total += img.size[0] * img.size[1]
    
    print(f"  Individual sum: {individual_total:,} pixels")
    print(f"  Difference: {combined_pixels - individual_total:+,} pixels ({(combined_pixels/individual_total-1)*100:+.1f}%)")
