"""
Region Calibration Tool

Zeigt die aktuelle Screenshot-Region und hilft beim Finden der richtigen Koordinaten.
"""
import sys
import os
# Add project root (two levels up from scripts/utils/) to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import cv2
import numpy as np
from utils import capture_region, preprocess, extract_text
from config import DEFAULT_REGION
import mss
from PIL import Image, ImageDraw, ImageFont

def capture_full_screen():
    """Capture kompletten Bildschirm"""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Primary monitor
        screenshot = sct.grab(monitor)
        img = np.array(screenshot)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
    return img, monitor

def draw_region_on_screen(img, region, label="Current Region"):
    """Zeichne Region-Box auf Bildschirm"""
    x1, y1, x2, y2 = region
    overlay = img.copy()
    
    # Zeichne Box
    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 255, 0), 3)
    
    # Zeichne Label
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(overlay, label, (x1, y1-10), font, 1, (0, 255, 0), 2)
    
    # Zeichne Koordinaten an Ecken
    cv2.putText(overlay, f"({x1},{y1})", (x1, y1+20), font, 0.5, (255, 255, 0), 1)
    cv2.putText(overlay, f"({x2},{y2})", (x2-100, y2-10), font, 0.5, (255, 255, 0), 1)
    
    return overlay

def main():
    print("="*80)
    print("🎯 REGION CALIBRATION TOOL")
    print("="*80)
    
    # 1. Zeige aktuelle Konfiguration
    print(f"\n📍 Aktuelle Region aus config.py:")
    print(f"   DEFAULT_REGION = {DEFAULT_REGION}")
    x1, y1, x2, y2 = DEFAULT_REGION
    w, h = x2 - x1, y2 - y1
    print(f"   Größe: {w}x{h} Pixel")
    
    # 2. Capture Full Screen
    print(f"\n📸 Capture Full Screen...")
    full_screen, monitor = capture_full_screen()
    print(f"   Monitor: {monitor['width']}x{monitor['height']}")
    
    # 3. Zeige Region auf Full Screen
    screen_with_box = draw_region_on_screen(full_screen, DEFAULT_REGION, "DEFAULT_REGION")
    cv2.imwrite("debug_fullscreen_with_region.png", screen_with_box)
    print(f"   ✅ Gespeichert: debug_fullscreen_with_region.png")
    
    # 4. Capture aktuelle Region
    print(f"\n📸 Capture DEFAULT_REGION...")
    region_img = capture_region(DEFAULT_REGION)
    cv2.imwrite("debug_region_original.png", region_img)
    print(f"   ✅ Gespeichert: debug_region_original.png")
    
    # 5. Preprocess Region
    print(f"\n🔧 Preprocessing...")
    processed = preprocess(region_img, adaptive=True, denoise=False)
    cv2.imwrite("debug_region_processed.png", processed)
    print(f"   ✅ Gespeichert: debug_region_processed.png")
    
    # 6. OCR Test
    print(f"\n🔍 OCR Test...")
    text = extract_text(processed, use_roi=False, method='easyocr')
    print(f"\n📝 OCR Result ({len(text)} chars):")
    print("-"*80)
    print(text[:500] if text else "(LEER)")
    print("-"*80)
    
    # 7. Empfehlungen
    print(f"\n💡 NÄCHSTE SCHRITTE:")
    print(f"   1. Öffne 'debug_fullscreen_with_region.png' und prüfe:")
    print(f"      - Ist die grüne Box über dem Marktfenster?")
    print(f"      - Wenn NEIN: Region muss angepasst werden!")
    print(f"   2. Öffne 'debug_region_original.png' und prüfe:")
    print(f"      - Ist das komplette Marktfenster sichtbar?")
    print(f"      - Ist der Transaktionslog im unteren Bereich sichtbar?")
    print(f"   3. Wenn Region falsch ist:")
    print(f"      - Öffne BDO und positioniere Marktfenster")
    print(f"      - Nutze Windows Snipping Tool um Koordinaten zu ermitteln")
    print(f"      - Aktualisiere DEFAULT_REGION in config.py")
    print(f"\n📐 REGION ERMITTELN:")
    print(f"   1. Öffne BDO Marktfenster")
    print(f"   2. Nutze Windows Snipping Tool (Win+Shift+S)")
    print(f"   3. Markiere Marktfenster komplett")
    print(f"   4. Snipping Tool zeigt Position und Größe!")
    print(f"   5. Berechne: x2=x1+width, y2=y1+height")
    print(f"\n" + "="*80)

if __name__ == "__main__":
    main()
