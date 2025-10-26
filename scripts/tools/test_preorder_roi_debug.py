"""
Test script to generate debug screenshots for preorder input ROI.
Uses existing dev-screenshots to validate ROI detection and debug output.
"""
import cv2
from pathlib import Path
from utils import (
    preprocess,
    detect_detail_preorder_input_roi,
    detect_detail_item_name_roi,
    detect_detail_balance_roi,
    detect_detail_warehouse_roi,
    detect_window_label_roi
)
from PIL import Image

def save_roi_debug_images(img_path: str, window_type: str):
    """Generate debug screenshots for all detail-window ROIs."""
    print(f"\n{'='*60}")
    print(f"Processing: {img_path}")
    print(f"Window Type: {window_type}")
    print(f"{'='*60}\n")
    
    # Load image
    img = cv2.imread(img_path)
    if img is None:
        print(f"❌ Failed to load image: {img_path}")
        return
    
    # Preprocess
    proc = preprocess(img, adaptive=True, denoise=False, fast_mode=False)
    
    # Detect all ROIs
    rois = {
        'label': detect_window_label_roi(img),
        'item_name': detect_detail_item_name_roi(img, window_type),
        'balance': detect_detail_balance_roi(img, window_type),
        'warehouse': detect_detail_warehouse_roi(img, window_type),
        'preorder_input': detect_detail_preorder_input_roi(img, window_type),
    }
    
    # Create debug directory
    debug_dir = Path("debug")
    debug_dir.mkdir(exist_ok=True)
    
    # Save full images
    Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).save(
        debug_dir / f"debug_{window_type}_full_orig.png"
    )
    Image.fromarray(proc).save(
        debug_dir / f"debug_{window_type}_full_proc.png"
    )
    
    # Save ROI images
    for roi_name, roi in rois.items():
        if not roi:
            print(f"⚠️  {roi_name}: ROI detection failed")
            continue
        
        x, y, w, h = roi
        if w <= 0 or h <= 0:
            print(f"⚠️  {roi_name}: Invalid dimensions ({w}x{h})")
            continue
        
        # Extract ROI from original and preprocessed
        roi_orig = img[y:y+h, x:x+w]
        roi_proc = proc[y:y+h, x:x+w]
        
        # Save original (BGR -> RGB)
        Image.fromarray(cv2.cvtColor(roi_orig, cv2.COLOR_BGR2RGB)).save(
            debug_dir / f"debug_{roi_name}_{window_type}_orig.png"
        )
        
        # Save preprocessed (grayscale)
        Image.fromarray(roi_proc).save(
            debug_dir / f"debug_{roi_name}_{window_type}_proc.png"
        )
        
        print(f"✅ {roi_name}: Saved ({w}x{h} at x={x}, y={y})")
    
    print(f"\n{'='*60}")
    print(f"✅ All debug images saved to {debug_dir}/")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    # Test with existing dev-screenshots
    test_images = [
        ("dev-screenshots/buy_item_marked.png", "buy_item"),
        ("dev-screenshots/sell_item_marked.png", "sell_item"),
    ]
    
    for img_path, window_type in test_images:
        if Path(img_path).exists():
            save_roi_debug_images(img_path, window_type)
        else:
            print(f"⚠️  Image not found: {img_path}")
