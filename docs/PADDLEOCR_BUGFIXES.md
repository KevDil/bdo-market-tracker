# PaddleOCR Integration - Bugfixes

## 📅 Datum: 2025-10-13 (23:00 UTC)

## 🐛 Problem

PaddleOCR wurde nicht genutzt, obwohl `OCR_ENGINE = 'paddle'` in config.py gesetzt war. Alle OCR-Aufrufe verwendeten weiterhin EasyOCR.

---

## 🔍 Root Cause Analysis

### Problem 1: Default-Parameter in Funktionen
**Betroffen**: `utils.py`

Die Funktionen hatten noch `method='easyocr'` als Default-Parameter, obwohl die Config `OCR_ENGINE = 'paddle'` war:

```python
# VORHER (Falsch):
def extract_text(img, use_roi=True, method='easyocr', fast_mode=True):
def ocr_image_cached(img, method='easyocr', use_roi=True, ...):
def capture_and_ocr_cached(region, method='easyocr', use_roi=True):
```

**Impact**: Alle Aufrufe ohne expliziten `method`-Parameter nutzten EasyOCR.

### Problem 2: Explizite EasyOCR-Aufrufe
**Betroffen**: `tracker.py`

Der Haupttracker hatte einen expliziten `method='easyocr'` Aufruf:

```python
# VORHER (Falsch):
text, was_cached, cache_stats = ocr_image_cached(
    img,
    method='easyocr',  # <-- Explizit EasyOCR erzwungen
    ...
)
```

**Impact**: Selbst mit Config-Änderung wurde EasyOCR erzwungen.

### Problem 3: PaddleOCR API-Änderung
**Betroffen**: `ocr_engines.py`

PaddleOCR v3.2+ hat den `cls` Parameter entfernt:

```python
# VORHER (Falsch):
result = _paddle_reader.ocr(img, cls=False)  # <-- cls existiert nicht mehr

# ERROR:
# PaddleOCR.predict() got an unexpected keyword argument 'cls'
```

**Impact**: PaddleOCR-Aufrufe führten zu Exceptions.

---

## ✅ Fixes

### Fix 1: Default-Parameter auf 'auto' geändert

**Datei**: `utils.py`

```python
# NACHHER (Korrekt):
def extract_text(img, use_roi=True, method='auto', fast_mode=True):
    """method='auto' uses config.OCR_ENGINE (default: paddle)"""
    ...

def ocr_image_cached(img, method='auto', use_roi=True, ...):
    """Uses PaddleOCR by default (via config.OCR_ENGINE)"""
    ...

def capture_and_ocr_cached(region, method='auto', use_roi=True):
    """Uses PaddleOCR by default."""
    ...
```

**Zeilen geändert**:
- Zeile 247: `extract_text()` - `method='easyocr'` → `method='auto'`
- Zeile 467: `ocr_image_cached()` - `method='easyocr'` → `method='auto'`
- Zeile 537: `capture_and_ocr_cached()` - `method='easyocr'` → `method='auto'`

### Fix 2: Tracker auf Auto-Mode umgestellt

**Datei**: `tracker.py`

```python
# NACHHER (Korrekt):
text, was_cached, cache_stats = ocr_image_cached(
    img,
    method='auto',  # <-- Nutzt config.OCR_ENGINE (paddle)
    use_roi=True,
    preprocessed=proc,
    fast_mode=True,
)
```

**Zeilen geändert**:
- Zeile 217: `method='easyocr'` → `method='auto'`
- Zeile 213-214: Kommentar aktualisiert (Phase 2 erwähnt)

### Fix 3: PaddleOCR API angepasst

**Datei**: `ocr_engines.py`

```python
# NACHHER (Korrekt):
# Note: PaddleOCR v3.2+ removed the cls parameter
if hasattr(img, 'shape'):  # numpy array
    result = _paddle_reader.ocr(img)  # <-- Kein cls Parameter
else:
    result = _paddle_reader.ocr(np.array(img))
```

**Zeilen geändert**:
- Zeile 129: Kommentar hinzugefügt
- Zeile 131: `cls=False` entfernt
- Zeile 133: `cls=False` entfernt

---

## 🧪 Validation

### Test 1: Engine-Auswahl
```bash
python -c "import config; print(f'OCR_ENGINE: {config.OCR_ENGINE}')"
```
**Ergebnis**: ✅ `OCR_ENGINE: paddle`

### Test 2: PaddleOCR funktioniert
```bash
python -c "from utils import extract_text, preprocess; import numpy as np; import cv2; img = np.ones((100, 300, 3), dtype=np.uint8) * 255; cv2.putText(img, 'Test', (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2); proc = preprocess(img); result = extract_text(proc); print(f'Result: {result}')"
```
**Ergebnis**: ✅ `Result: Test` (PaddleOCR erkannte den Text)

### Test 3: Keine Errors mehr
**Vorher**: `PaddleOCR.predict() got an unexpected keyword argument 'cls'`  
**Nachher**: ✅ Keine Errors, OCR funktioniert

---

## 📊 Geänderte Dateien

| Datei | Zeilen | Änderung | Typ |
|-------|--------|----------|-----|
| `utils.py` | 247 | `method='easyocr'` → `method='auto'` | Bugfix |
| `utils.py` | 467 | `method='easyocr'` → `method='auto'` | Bugfix |
| `utils.py` | 537 | `method='easyocr'` → `method='auto'` | Bugfix |
| `tracker.py` | 217 | `method='easyocr'` → `method='auto'` | Bugfix |
| `tracker.py` | 213-214 | Kommentar aktualisiert | Dokumentation |
| `ocr_engines.py` | 129 | Kommentar hinzugefügt | Dokumentation |
| `ocr_engines.py` | 131 | `cls=False` entfernt | API-Fix |
| `ocr_engines.py` | 133 | `cls=False` entfernt | API-Fix |

**Total**: 3 Dateien, 8 Änderungen

---

## ✅ Erwartetes Verhalten (Jetzt)

### Standard-Nutzung (ohne expliziten method-Parameter):
```python
text = extract_text(img)  # <-- Nutzt PaddleOCR (via config.OCR_ENGINE)
```

### Explizite Engine-Auswahl (optional):
```python
text = extract_text(img, method='paddle')    # <-- PaddleOCR
text = extract_text(img, method='easyocr')   # <-- EasyOCR
text = extract_text(img, method='tesseract') # <-- Tesseract
text = extract_text(img, method='auto')      # <-- Config-basiert (paddle)
```

### Config-basierte Steuerung:
```python
# In config.py
OCR_ENGINE = 'paddle'      # Default: PaddleOCR
OCR_ENGINE = 'easyocr'     # Wechsel zu EasyOCR
OCR_FALLBACK_ENABLED = True  # Auto-Fallback bei Fehlern
```

---

## 🎯 Zusammenfassung

**Problem**: PaddleOCR wurde nicht genutzt trotz Config  
**Ursache**: Default-Parameter + explizite EasyOCR-Aufrufe + API-Inkompatibilität  
**Lösung**: 3 Dateien geändert, 8 Zeilen korrigiert  
**Status**: ✅ **BEHOBEN**

PaddleOCR wird jetzt standardmäßig genutzt und funktioniert korrekt!

---

**Erstellt von**: Agent Mode (Warp AI)  
**Datum**: 2025-10-13 23:05 UTC  
**Dokumentation**: docs/PADDLEOCR_BUGFIXES.md
