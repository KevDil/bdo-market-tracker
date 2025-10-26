"""
Create visual comparison of all Detail-Window ROIs.
Shows original image with ROI boundaries overlaid.
"""
import cv2
from pathlib import Path
from utils import (
    detect_detail_preorder_input_roi,
    detect_detail_item_name_roi,
    detect_detail_balance_roi,
    detect_detail_warehouse_roi,
    detect_window_label_roi
)

def draw_roi_overlay(img_path: str, window_type: str, output_path: str):
    """Draw all ROI boundaries on the original image."""
    img = cv2.imread(img_path)
    if img is None:
        print(f"❌ Failed to load: {img_path}")
        return
    
    # Create copy for drawing
    overlay = img.copy()
    
    # ROI colors (BGR format)
    colors = {
        'label': (0, 255, 0),           # Green
        'item_name': (255, 0, 0),       # Blue
        'balance': (0, 255, 255),       # Yellow
        'warehouse': (255, 0, 255),     # Magenta
        'preorder_input': (0, 0, 255),  # Red
    }
    
    # Detect and draw all ROIs
    rois = {
        'label': detect_window_label_roi(img),
        'item_name': detect_detail_item_name_roi(img, window_type),
        'balance': detect_detail_balance_roi(img, window_type),
        'warehouse': detect_detail_warehouse_roi(img, window_type),
        'preorder_input': detect_detail_preorder_input_roi(img, window_type),
    }
    
    print(f"\n{window_type.upper()} ROIs:")
    for roi_name, roi in rois.items():
        if not roi:
            print(f"  ⚠️  {roi_name}: Not detected")
            continue
        
        x, y, w, h = roi
        color = colors[roi_name]
        
        # Draw rectangle
        cv2.rectangle(overlay, (x, y), (x+w, y+h), color, 3)
        
        # Add label
        label_text = roi_name.replace('_', ' ').title()
        font_scale = 0.7
        thickness = 2
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Get text size for background
        (text_w, text_h), baseline = cv2.getTextSize(label_text, font, font_scale, thickness)
        
        # Draw background rectangle for text
        cv2.rectangle(overlay, (x, y-text_h-10), (x+text_w+10, y), color, -1)
        
        # Draw text
        cv2.putText(overlay, label_text, (x+5, y-5), font, font_scale, (255, 255, 255), thickness)
        
        print(f"  ✅ {roi_name}: {w}x{h} at ({x}, {y})")
    
    # Save overlay image
    cv2.imwrite(output_path, overlay)
    print(f"\n✅ Saved overlay: {output_path}\n")

if __name__ == "__main__":
    # Create overlays for both window types
    test_images = [
        ("dev-screenshots/buy_item_marked.png", "buy_item", "debug/debug_buy_item_roi_overlay.png"),
        ("dev-screenshots/sell_item_marked.png", "sell_item", "debug/debug_sell_item_roi_overlay.png"),
    ]
    
    for img_path, window_type, output_path in test_images:
        if Path(img_path).exists():
            draw_roi_overlay(img_path, window_type, output_path)
        else:
            print(f"⚠️  Image not found: {img_path}")
