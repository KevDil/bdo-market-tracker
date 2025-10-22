"""
Test-Script um die OCR-Qualität zu vergleichen
Testet PaddleOCR vs EasyOCR vs Tesseract auf debug_proc.png (im Root-Verzeichnis)
"""
import sys
import os
# Add project root (two levels up from scripts/utils/) to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import cv2
import time
from PIL import Image
from pathlib import Path

# Work from project root
ROOT_DIR = Path(__file__).resolve().parents[2]
os.chdir(ROOT_DIR)

def test_paddleocr():
    """Test PaddleOCR"""
    try:
        from paddleocr import PaddleOCR
        ocr = PaddleOCR(use_angle_cls=True, lang='en')
        
        img = cv2.imread('debug_proc.png')
        if img is None:
            print("❌ debug_proc.png nicht gefunden")
            return None
        
        start = time.time()
        result = ocr.ocr(img, cls=True)
        elapsed = time.time() - start
        
        if result and result[0]:
            text_items = []
            for line in result[0]:
                if line and len(line) >= 2:
                    bbox, (text, conf) = line[0], line[1]
                    y_center = sum(pt[1] for pt in bbox) / 4
                    text_items.append((y_center, text))
            text_items.sort(key=lambda x: x[0])
            text = " ".join(item[1] for item in text_items)
        else:
            text = ""
        
        return {
            'name': 'PaddleOCR',
            'text': text,
            'time': elapsed,
            'length': len(text)
        }
    except Exception as e:
        print(f"❌ PaddleOCR Fehler: {e}")
        return None

def test_easyocr():
    """Test EasyOCR"""
    try:
        import easyocr
        reader = easyocr.Reader(['en'], gpu=False)
        
        img = cv2.imread('debug_proc.png')
        if img is None:
            return None
        
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        
        start = time.time()
        res = reader.readtext(rgb, detail=0, paragraph=True)
        elapsed = time.time() - start
        
        text = " ".join(res)
        
        return {
            'name': 'EasyOCR',
            'text': text,
            'time': elapsed,
            'length': len(text)
        }
    except Exception as e:
        print(f"❌ EasyOCR Fehler: {e}")
        return None

def test_tesseract():
    """Test Tesseract"""
    try:
        import pytesseract
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        
        img = cv2.imread('debug_proc.png', cv2.IMREAD_GRAYSCALE)
        if img is None:
            return None
        
        pil = Image.fromarray(img)
        
        start = time.time()
        text = pytesseract.image_to_string(pil, config='--psm 6 --oem 3')
        elapsed = time.time() - start
        
        return {
            'name': 'Tesseract',
            'text': text,
            'time': elapsed,
            'length': len(text)
        }
    except Exception as e:
        print(f"❌ Tesseract Fehler: {e}")
        return None

def analyze_ocr_quality(result):
    """Analysiert OCR-Qualität anhand typischer Fehler"""
    if not result or not result['text']:
        return {}
    
    text = result['text']
    
    # Zähle typische OCR-Fehler
    o_count = text.count('O') + text.count('o')
    zero_count = text.count('0')
    i_count = text.count('I') + text.count('l')
    one_count = text.count('1')
    
    # Suche nach Zahlenblöcken
    import re
    numbers = re.findall(r'\d[\d,\.]+', text)
    
    # Suche nach bekannten Keywords
    keywords = ['Transaction', 'Silver', 'Listed', 'Purchased', 'Orders', 'Sales']
    found_keywords = [kw for kw in keywords if kw.lower() in text.lower()]
    
    return {
        'char_count': len(text),
        'numbers_found': len(numbers),
        'keywords_found': len(found_keywords),
        'keywords': found_keywords,
        'o_vs_0': f"O/o: {o_count}, 0: {zero_count}",
        'i_vs_1': f"I/l: {i_count}, 1: {one_count}"
    }

if __name__ == "__main__":
    print("=" * 80)
    print("OCR-Qualitätsvergleich für BDO Market Tracker")
    print("=" * 80)
    print()
    
    # Teste alle Engines
    results = []
    
    print("🔍 Teste PaddleOCR...")
    paddle_result = test_paddleocr()
    if paddle_result:
        results.append(paddle_result)
    print()
    
    print("🔍 Teste EasyOCR...")
    easy_result = test_easyocr()
    if easy_result:
        results.append(easy_result)
    print()
    
    print("🔍 Teste Tesseract...")
    tess_result = test_tesseract()
    if tess_result:
        results.append(tess_result)
    print()
    
    # Vergleich
    print("=" * 80)
    print("ERGEBNISSE")
    print("=" * 80)
    print()
    
    for result in results:
        print(f"📊 {result['name']}")
        print(f"   Zeit: {result['time']:.2f}s")
        print(f"   Zeichen: {result['length']}")
        
        analysis = analyze_ocr_quality(result)
        if analysis:
            print(f"   Zahlen erkannt: {analysis['numbers_found']}")
            print(f"   Keywords gefunden: {analysis['keywords_found']} - {', '.join(analysis['keywords'][:3])}")
            print(f"   {analysis['o_vs_0']}")
            print(f"   {analysis['i_vs_1']}")
        
        print()
        print(f"   Erste 200 Zeichen:")
        print(f"   {result['text'][:200]}")
        print()
        print("-" * 80)
    
    # Empfehlung
    if paddle_result and easy_result:
        print()
        print("💡 EMPFEHLUNG:")
        if paddle_result['length'] > easy_result['length'] * 0.9:
            print("   ✅ PaddleOCR liefert vergleichbare oder bessere Ergebnisse")
            print("   ✅ Empfohlen für beste Qualität")
        else:
            print("   ⚠️  EasyOCR hat mehr Text erkannt")
            print("   💭 Prüfe die Qualität der Erkennung manuell")
