"""
Test-Script für OCR-Verbesserungen (V2)

Vergleicht die neue OCR-Pipeline mit verschiedenen Methoden:
- EasyOCR mit optimierten Parametern
- Tesseract mit Whitelist
- Beide Methoden kombiniert

Usage:
    python scripts/test_ocr_improvements.py
"""

import sys

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
from PIL import Image
from utils import capture_region, preprocess, extract_text, log_debug
from config import DEFAULT_REGION

def test_ocr_methods():
    """Testet verschiedene OCR-Methoden auf dem aktuellen Screenshot."""
    
    print("=" * 80)
    print("OCR V2 - Verbesserungstest")
    print("=" * 80)
    print()
    
    # Screenshot
    print("📸 Capturing screenshot...")
    try:
        img = capture_region(DEFAULT_REGION)
        print(f"✓ Screenshot captured: {img.shape}")
    except Exception as e:
        print(f"✗ Error capturing screenshot: {e}")
        return
    
    # Preprocessing Vergleich
    print("\n" + "─" * 80)
    print("🔧 Testing Preprocessing Methods:")
    print("─" * 80)
    
    print("\n1️⃣ Old Method (Simple Sharpening):")
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        import numpy as np
        kernel = np.array([[0, -1, 0],[-1, 5, -1],[0, -1, 0]])
        sharp = cv2.filter2D(gray, -1, kernel)
        sharp = cv2.convertScaleAbs(sharp, alpha=1.6, beta=12)
        proc_old = cv2.GaussianBlur(sharp, (1,1), 0)
        Image.fromarray(proc_old).save("debug_proc_old.png")
        print("✓ Saved as debug_proc_old.png")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    print("\n2️⃣ New Method (Adaptive CLAHE, no denoise):")
    try:
        proc_new = preprocess(img, adaptive=True, denoise=False)
        Image.fromarray(proc_new).save("debug_proc_new.png")
        print("✓ Saved as debug_proc_new.png")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # OCR Vergleich
    print("\n" + "─" * 80)
    print("🔍 Testing OCR Methods:")
    print("─" * 80)
    
    methods = [
        ('easyocr', 'EasyOCR (optimized)', True),
        ('tesseract', 'Tesseract (whitelist)', True),
        ('both', 'Both (best result)', True),
    ]
    
    results = {}
    
    for method_key, method_name, use_roi in methods:
        print(f"\n{method_name} (ROI: {use_roi}):")
        try:
            text = extract_text(proc_new, use_roi=use_roi, method=method_key)
            results[method_key] = text
            
            # Stats
            char_count = len(text)
            line_count = len(text.split('\n'))
            word_count = len(text.split())
            
            print(f"  Characters: {char_count}")
            print(f"  Words: {word_count}")
            print(f"  Lines: {line_count}")
            print(f"  Preview (first 200 chars):")
            print(f"  {text[:200].replace(chr(10), ' ')}")
            
            # Save to file
            filename = f"debug_ocr_{method_key}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(text)
            print(f"  ✓ Full text saved to {filename}")
            
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results[method_key] = None
    
    # Vergleich
    print("\n" + "─" * 80)
    print("📊 Comparison:")
    print("─" * 80)
    
    if results.get('easyocr') and results.get('tesseract'):
        easy_len = len(results['easyocr'])
        tess_len = len(results['tesseract'])
        
        print(f"\nEasyOCR length: {easy_len}")
        print(f"Tesseract length: {tess_len}")
        print(f"Difference: {abs(easy_len - tess_len)} chars")
        
        if easy_len > tess_len * 1.2:
            print("→ EasyOCR erkannte deutlich mehr Text (besser für BDO)")
        elif tess_len > easy_len * 1.2:
            print("→ Tesseract erkannte deutlich mehr Text")
        else:
            print("→ Beide Methoden sind ähnlich")
    
    print("\n" + "=" * 80)
    print("✓ Test complete!")
    print("=" * 80)
    print("\nGenerated files:")
    print("  - debug_proc_old.png (Old preprocessing)")
    print("  - debug_proc_new.png (New preprocessing)")
    print("  - debug_ocr_easyocr.txt (EasyOCR result)")
    print("  - debug_ocr_tesseract.txt (Tesseract result)")
    print("  - debug_ocr_both.txt (Combined result)")
    print("\n💡 Tipp: Vergleiche die *_proc*.png Bilder visuell!")
    print("   Das neue Preprocessing sollte schärfer und kontrastreicher sein.")

if __name__ == "__main__":
    test_ocr_methods()
