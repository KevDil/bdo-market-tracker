# OCR Engine Konfigurationsoptionen

## 🎯 Problem

PaddleOCR ist schneller, aber bei BDO-UI weniger genau als EasyOCR:
- PaddleOCR: "Transaction af Cancentrater" ❌
- EasyOCR: "Transaction of Concentrated Magical Black Stone" ✅

## 💡 Lösungen

### Option 1: EasyOCR Only (Aktuell - Empfohlen)

**In `config.py`:**
```python
OCR_ENGINE = 'easyocr'
OCR_FALLBACK_ENABLED = True
```

**Vorteile:**
- ✅ Beste Accuracy für BDO-UI
- ✅ Erprobt und stabil
- ✅ Erkennt Item-Namen korrekt

**Nachteile:**
- ⚠️ Etwas langsamer (~400-700ms vs ~300-500ms)

---

### Option 2: Hybrid Mode (Beide Engines)

**In `tracker.py` ändern (Zeile 217):**
```python
text, was_cached, cache_stats = ocr_image_cached(
    img,
    method='both',  # <-- Nutzt beide Engines, wählt bestes Ergebnis
    use_roi=True,
    preprocessed=proc,
    fast_mode=True,
)
```

**Vorteile:**
- ✅ Nutzt beide Engines
- ✅ Wählt längeren/besseren Text
- ✅ Höhere Chance auf korrekten Text

**Nachteile:**
- ⚠️ Langsamer (beide Engines laufen)
- ⚠️ ~1-1.5s pro Scan

---

### Option 3: PaddleOCR mit EasyOCR Fallback

**In `config.py`:**
```python
OCR_ENGINE = 'paddle'
OCR_FALLBACK_ENABLED = True
```

**Vorteile:**
- ✅ Schnell bei guter Qualität
- ✅ Fallback zu EasyOCR bei Fehlern

**Nachteile:**
- ⚠️ PaddleOCR liefert oft Fehler
- ⚠️ Fallback greift nur bei leeren Ergebnissen
- ⚠️ Schlechte OCR-Qualität wird nicht erkannt

---

### Option 4: EasyOCR mit PaddleOCR Fallback (Empfehlung für Tests)

**In `config.py`:**
```python
OCR_ENGINE = 'easyocr'
OCR_FALLBACK_ENABLED = True
```

**UND in `utils.py` (Zeile 292) ändern:**
```python
# Ändere Priorität: EasyOCR zuerst, dann PaddleOCR
if actual_method == 'easyocr' or (actual_method in ['both', 'auto'] and OCR_FALLBACK_ENABLED):
```

**Vorteile:**
- ✅ Beste Accuracy (EasyOCR)
- ✅ PaddleOCR als Fallback bei Problemen
- ✅ Balanciert

---

## 📊 Vergleich

| Option | Accuracy | Speed | Empfehlung |
|--------|----------|-------|------------|
| **Option 1: EasyOCR Only** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ **EMPFOHLEN** |
| Option 2: Hybrid Mode | ⭐⭐⭐⭐⭐ | ⭐⭐ | Für Tests |
| Option 3: Paddle + Fallback | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ❌ Zu unzuverlässig |
| Option 4: Easy + Fallback | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Alternativ gut |

---

## 🎬 Aktuelle Einstellung

**Status**: Option 1 (EasyOCR Only) ist jetzt aktiv ✅

```python
# config.py
OCR_ENGINE = 'easyocr'
```

Dies sollte Ihre Transaktionen jetzt korrekt erkennen!

---

## 🧪 Test

Machen Sie einen neuen Test-Kauf und prüfen Sie die Logs:
```bash
Get-Content "C:\Users\kdill\Desktop\market_tracker\ocr_log.txt" -Tail 50
```

Achten Sie auf:
- ✅ `engine=easyocr` (nicht paddle)
- ✅ Korrekte Item-Namen
- ✅ Timestamps im Format "2025.10.14 00:59"

---

**Erstellt**: 2025-10-14 01:05 UTC
