"""
ROI-Kalibrierung für Detail-Fenster.

Dieses Script hilft bei der Kalibrierung der ROI-Positionen für:
- Item Name (oben links)
- Balance (Kontostand, mittig links)
- Warehouse Quantity (Lagerbestand, oben/unten links je nach Fenstertyp)

Usage:
    python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/sell_item_marked.png --type sell_item
    python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/buy_item_marked.png --type buy_item
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import cv2
import numpy as np
from utils import preprocess


def _shape_hw(img):
    """Helper to get (height, width) from image."""
    if img.ndim == 3:
        return img.shape[0], img.shape[1]
    return img.shape


def detect_detail_item_name_roi(img, window_type: str):
    """
    ROI für Item-Name im Detail-Fenster.
    
    Position: Oben links im Detail-Fenster
    Text: Item-Name (z.B. "Powder of Darkness", "Brutal Death Elixir")
    
    Returns:
        tuple (x, y, width, height) oder None
    """
    try:
        h, w = _shape_hw(img)
        # Item-Name ist immer oben links im Detail-Fenster
        # Geschätzte Position: 5-40% Breite, 5-20% Höhe
        if window_type == 'sell_item':
            x_start = int(w * 0.08)
            x_end = int(w * 0.45)
            y_start = int(h * 0.03)
            y_end = int(h * 0.09)
        elif window_type == 'buy_item':
            x_start = int(w * 0.09)
            x_end = int(w * 0.45)
            y_start = int(h * 0.08)
            y_end = int(h * 0.14)
        else:
            print(f"Invalid window type: {window_type}")
            return None

        width = x_end - x_start
        height = y_end - y_start
        return (x_start, y_start, width, height)
    except Exception as e:
        print(f"Error detecting item name ROI: {e}")
        return None


def detect_detail_balance_roi(img, window_type: str):
    """
    ROI für Kontostand (Balance) im Detail-Fenster.
    
    Position: Mittig links
    Text: "Balance: <amount> Silver"
    
    Returns:
        tuple (x, y, width, height) oder None
    """
    try:
        h, w = _shape_hw(img)
        # Kontostand ist immer mittig-links im Detail-Fenster
        # Geschätzte Position: 10-35% Breite, 35-50% Höhe
        if window_type == 'sell_item':
            x_start = int(w * 0.04)
            x_end = int(w * 0.23)
            y_start = int(h * 0.46)
            y_end = int(h * 0.55)
        elif window_type == 'buy_item':
            # Buy-Item: Warehouse unten links
            # Geschätzte Position: 5-30% Breite, 65-85% Höhe
            x_start = int(w * 0.04)
            x_end = int(w * 0.23)
            y_start = int(h * 0.50)
            y_end = int(h * 0.59)
        else:
            print(f"Invalid window type: {window_type}")
            return None
        
        width = x_end - x_start
        height = y_end - y_start
        return (x_start, y_start, width, height)
    except Exception as e:
        print(f"Error detecting balance ROI: {e}")
        return None


def detect_detail_warehouse_roi(img, window_type: str):
    """
    ROI für Lagerbestand (Warehouse Quantity) im Detail-Fenster.
    
    Position abhängig von Fenstertyp:
    - Sell-Item: Relativ weit oben links
    - Buy-Item: Relativ weit unten links
    
    Args:
        img: Preprocessed image
        window_type: 'sell_item' oder 'buy_item'
    
    Returns:
        tuple (x, y, width, height) oder None
    """
    try:
        h, w = _shape_hw(img)
        
        if window_type == 'sell_item':
            # Sell-Item: Warehouse oben links
            # Geschätzte Position: 5-30% Breite, 15-35% Höhe
            x_start = int(w * 0.03)
            x_end = int(w * 0.10)
            y_start = int(h * 0.11)
            y_end = int(h * 0.20)
        elif window_type == 'buy_item':
            # Buy-Item: Warehouse unten links
            # Geschätzte Position: 5-30% Breite, 65-85% Höhe
            x_start = int(w * 0.04)
            x_end = int(w * 0.43)
            y_start = int(h * 0.84)
            y_end = int(h * 0.89)
        else:
            print(f"Invalid window type: {window_type}")
            return None
        
        width = x_end - x_start
        height = y_end - y_start
        return (x_start, y_start, width, height)
    except Exception as e:
        print(f"Error detecting warehouse ROI: {e}")
        return None


def detect_detail_preorder_input_roi(img, window_type: str):
    """
    ROI für Preorder-Eingabefelder im Detail-Fenster.
    
    Position: Rechte Seite des Detail-Fensters
    
    Buy-Item enthält:
    - "Desired Price" Input-Feld (Preis pro Einheit)
    - "Desired Amount" Input-Feld (Anzahl)
    
    Sell-Item enthält:
    - "Set Price" Input-Feld (Preis pro Einheit)
    - "Register Quantity" Input-Feld (Anzahl)
    
    Args:
        img: Preprocessed image
        window_type: 'sell_item' oder 'buy_item'
    
    Returns:
        tuple (x, y, width, height) oder None
    """
    try:
        h, w = _shape_hw(img)
        
        if window_type == 'sell_item':
            # Sell-Item: Rechte Hälfte, mittlerer Bereich
            # Enthält: "Set Price" und "Register Quantity"
            # Geschätzte Position: 50-95% Breite, 30-70% Höhe
            x_start = int(w * 0.43)
            x_end = int(w * 0.67)
            y_start = int(h * 0.49)
            y_end = int(h * 0.73)
        elif window_type == 'buy_item':
            # Buy-Item: Rechte Hälfte, mittlerer Bereich
            # Enthält: "Desired Price" und "Desired Amount"
            # Geschätzte Position: 50-95% Breite, 35-75% Höhe
            x_start = int(w * 0.43)
            x_end = int(w * 0.67)
            y_start = int(h * 0.49)
            y_end = int(h * 0.73)
        else:
            print(f"Invalid window type: {window_type}")
            return None
        
        width = x_end - x_start
        height = y_end - y_start
        return (x_start, y_start, width, height)
    except Exception as e:
        print(f"Error detecting preorder input ROI: {e}")
        return None


def visualize_roi(image_path: str, window_type: str):
    """
    Visualisiert ROI-Positionen auf Screenshot.
    
    Args:
        image_path: Path to screenshot
        window_type: 'sell_item' oder 'buy_item'
    """
    print(f"\n{'='*60}")
    print(f"ROI Calibration for {window_type.upper()}")
    print(f"{'='*60}\n")
    
    # Load image
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"❌ Error: Could not load image {image_path}")
        return
    
    print(f"✅ Image loaded: {image_path}")
    print(f"   Dimensions: {img.shape[1]}x{img.shape[0]} px")
    
    # Preprocess
    print(f"\n🔄 Preprocessing image...")
    proc = preprocess(img, adaptive=True, denoise=False, fast_mode=False)
    print(f"✅ Preprocessing complete")
    
    # Get ROIs
    print(f"\n🔍 Detecting ROIs...")
    item_name_roi = detect_detail_item_name_roi(proc, window_type)
    balance_roi = detect_detail_balance_roi(proc, window_type)
    warehouse_roi = detect_detail_warehouse_roi(proc, window_type)
    preorder_input_roi = detect_detail_preorder_input_roi(proc, window_type)
    
    # Draw ROIs on original image
    output = img.copy()
    
    roi_count = 0
    total_rois = 4
    
    if item_name_roi:
        x, y, w, h = item_name_roi
        cv2.rectangle(output, (x, y), (x + w, y + h), (0, 255, 0), 3)  # Grün
        cv2.putText(output, "Item Name ROI", (x, y - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        print(f"   ✅ Item Name ROI: x={x}, y={y}, w={w}, h={h}")
        roi_count += 1
    else:
        print(f"   ❌ Item Name ROI: Not detected")
    
    if balance_roi:
        x, y, w, h = balance_roi
        cv2.rectangle(output, (x, y), (x + w, y + h), (255, 0, 255), 3)  # Violett
        cv2.putText(output, "Balance ROI", (x, y - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
        print(f"   ✅ Balance ROI: x={x}, y={y}, w={w}, h={h}")
        roi_count += 1
    else:
        print(f"   ❌ Balance ROI: Not detected")
    
    if warehouse_roi:
        x, y, w, h = warehouse_roi
        cv2.rectangle(output, (x, y), (x + w, y + h), (0, 255, 255), 3)  # Gelb
        cv2.putText(output, "Warehouse ROI", (x, y - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        print(f"   ✅ Warehouse ROI: x={x}, y={y}, w={w}, h={h}")
        roi_count += 1
    else:
        print(f"   ❌ Warehouse ROI: Not detected")
    
    if preorder_input_roi:
        x, y, w, h = preorder_input_roi
        cv2.rectangle(output, (x, y), (x + w, y + h), (255, 128, 0), 3)  # Orange
        # Unterschiedlicher Text je nach Window-Type
        if window_type == 'buy_item':
            label_text = "Preorder Input ROI (Desired Price/Amount)"
        else:
            label_text = "Preorder Input ROI (Set Price/Register Qty)"
        cv2.putText(output, label_text, (x, y - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 128, 0), 2)
        print(f"   ✅ Preorder Input ROI: x={x}, y={y}, w={w}, h={h}")
        if window_type == 'buy_item':
            print(f"      Expected fields: 'Desired Price' and 'Desired Amount'")
        else:
            print(f"      Expected fields: 'Set Price' and 'Register Quantity'")
        roi_count += 1
    else:
        print(f"   ❌ Preorder Input ROI: Not detected")
    
    # Save output
    output_dir = Path("debug")
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"calibrate_{window_type}_roi.png"
    
    cv2.imwrite(str(output_path), output)
    
    print(f"\n{'='*60}")
    print(f"✅ ROI visualization saved to: {output_path}")
    print(f"   ROIs detected: {roi_count}/{total_rois}")
    print(f"{'='*60}\n")
    
    if roi_count < total_rois:
        print("⚠️  WARNING: Not all ROIs were detected!")
        print("   Please adjust ROI coordinates in this script and utils.py")
        print("   See docs/DETAIL_WINDOW_ROI_REFERENCE.md for details")
    else:
        print("✅ All ROIs detected successfully!")
        print("   Please verify the ROI positions visually")
        print(f"   Open: {output_path}")
    
    print("\n📋 Expected UI Elements per Window Type:")
    if window_type == 'buy_item':
        print("   BUY-ITEM Window:")
        print("   - Preorder Input ROI should contain:")
        print("     • 'Desired Price' field (unit price)")
        print("     • 'Desired Amount' field (quantity)")
        print("     • Input values (e.g., '154,000' and '5000')")
    else:
        print("   SELL-ITEM Window:")
        print("   - Preorder Input ROI should contain:")
        print("     • 'Set Price' field (unit price)")
        print("     • 'Register Quantity' field (quantity)")
        print("     • Input values")
    
    print("\nNext steps:")
    print("1. Open the generated image to verify ROI positions")
    print("2. If Preorder Input ROI is INCORRECT, adjust coordinates:")
    print("   - In this script: detect_detail_preorder_input_roi()")
    print("   - In utils.py: Copy the function once calibrated")
    print("3. Run this script again to verify changes")
    print("4. The ROI must capture BOTH field labels AND input values!")
    print("5. Once calibrated, implement Phase 1: Preorder Input Extraction")


def main():
    parser = argparse.ArgumentParser(
        description="Calibrate Detail Window ROIs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/sell_item_marked.png --type sell_item
  python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/buy_item_marked.png --type buy_item

ROI Colors:
  Green   = Item Name ROI (oben links)
  Violet  = Balance ROI (mittig links)
  Yellow  = Warehouse ROI (oben/unten links je nach Fenstertyp)
  Orange  = Preorder Input ROI (rechts mittig - Desired Price/Amount oder Set Price/Register Quantity)
        """
    )
    
    parser.add_argument(
        "--image",
        required=True,
        help="Path to screenshot (e.g., dev-screenshots/sell_item_marked.png)"
    )
    parser.add_argument(
        "--type",
        choices=['sell_item', 'buy_item'],
        required=True,
        help="Window type: sell_item or buy_item"
    )
    
    args = parser.parse_args()
    
    # Validate image path
    image_path = Path(args.image)
    if not image_path.exists():
        print(f"❌ Error: Image not found: {image_path}")
        print(f"   Please provide a valid image path")
        sys.exit(1)
    
    # Run visualization
    try:
        visualize_roi(str(image_path), args.type)
    except Exception as e:
        print(f"\n❌ Error during ROI calibration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
