#!/usr/bin/env python3
"""Quick check of debug image dimensions."""
import cv2
from pathlib import Path

images = [
    'debug/debug_balance_buy_item_proc.png',
    'debug/debug_warehouse_buy_item_proc.png',
    'debug/debug_item_name_buy_item_proc.png',
    'debug/debug_label_proc.png',
]

print("\n📏 Debug Image Dimensions:")
print("="*60)
for path in images:
    p = Path(path)
    if p.exists():
        img = cv2.imread(str(p))
        if img is not None:
            h, w = img.shape[:2]
            pixels = h * w
            print(f"{p.name:40s}: {w}x{h} = {pixels:,} px")
        else:
            print(f"{p.name:40s}: Failed to load")
    else:
        print(f"{p.name:40s}: Not found")
print("="*60)
