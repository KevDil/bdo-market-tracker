# OCR V2 - Verbesserungen (2025-10-11) - FIXED for Game UIs

## 🎯 Ziel
Reduzierung der vielen Parsing-Heuristiken durch bessere OCR-Qualität an der Quelle.

## ⚠️ WICHTIG: Aggressive Binarisierung war das Problem!
Die erste Version (V2 initial) war **zu aggressiv** für Game-UIs wie BDO:
- Adaptive Binarisierung zerstörte UI-Text → nur Müll-Output
- Noise-Reduction verwischte Details (unnötig bei klaren Game-UIs)
- Zu aggressive EasyOCR-Parameter → False Positives

**Lösung:** Sanftere Pipeline speziell für Game-UIs optimiert.

---

## 🚀 Was wurde verbessert?

### 1. **Preprocessing-Pipeline (utils.py:preprocess())** - FIXED

#### Alt (V1):
```python
- Einfache Schärfung mit Kernel
- Globale Kontrast-Anpassung
- Gaussian Blur
```

#### V2 Initial (zu aggressiv - verworfen):
```python
✗ Adaptive Binarisierung → zerstörte UI-Text
✗ Noise-Reduction → unnötig für Game-UIs
✗ Morphologische Operationen → zu aggressiv
✗ Größen-Normalisierung auf 720p → verzerrte Bilder
```

#### V2 Final (Game-UI-optimiert):
```python
✓ Sanfte CLAHE-Kontrastverstärkung (clipLimit=1.5)
✓ Leichte Schärfung mit Kernel (nicht Unsharp Mask)
✓ Helligkeit/Kontrast-Anpassung (alpha=1.2, beta=10)
✓ KEINE Binarisierung (Graustufen für EasyOCR besser)
✓ Noise-Reduction deaktiviert (Game-UIs nicht verrauscht)
✓ Größen-Normalisierung nur bei sehr kleinen Bildern (<500px)
```

**Vorteil:** Erhält Original-Text-Qualität, verstärkt nur Kontrast sanft.

---

### 2. **ROI-Detection (utils.py:detect_log_roi())**

```python
✓ Erkennt die Log-Region automatisch
✓ OCR nur auf relevanten Bereich (schneller + genauer)
✓ Ignoriert Header/Navigation (reduziert Noise)
```

**Vorteil:** Weniger irrelevanter Text → weniger Parsing-Fehler.

---

### 3. **EasyOCR-Parameter-Tuning (utils.py:extract_text())** - FIXED

#### V2 Initial (zu aggressiv):
```python
contrast_ths=0.1        # Zu niedrig → viele False Positives
text_threshold=0.6      # Zu niedrig → erkannte Noise als Text
low_text=0.3            # Zu niedrig → zu viel Müll
link_threshold=0.3      # Zu niedrig → falsche Zeichen-Verbindungen
mag_ratio=1.5           # Zu hoch → Verzerrungen
```

#### V2 Final (balanciert für Game-UIs):
```python
contrast_ths=0.3        # ↑ Weniger False Positives
text_threshold=0.7      # Standard (gut für klaren UI-Text)
low_text=0.4            # Standard
link_threshold=0.4      # Standard
canvas_size=2560        # Groß genug für Details
mag_ratio=1.0           # Kein Zoom (Original-Größe)
```

**Vorteil:** Präzise Text-Erkennung ohne Müll-Output.

---

### 4. **Tesseract mit Whitelist (utils.py:extract_text())**

```python
✓ PSM 6 (Uniform block of text) - optimal für Log-Einträge
✓ Whitelist: "0-9a-zA-Z .,':x-()[]/"
✓ OEM 3 (LSTM + Legacy Engine)
```

**Vorteil:** Massive Reduktion von OCR-Fantasie-Zeichen (z.B. keine ♦, §, µ mehr).

---

### 5. **Methoden-Auswahl**

```python
method='easyocr'    # Schnell, für Live-Tracking
method='tesseract'  # Alternative, wenn EasyOCR Probleme macht
method='both'       # Beide versuchen, längeres Ergebnis nehmen (langsam!)
```

---

## 📊 Erwartete Verbesserungen

### Weniger benötigte Heuristiken:

| Problem | Alt (V1) | Neu (V2) |
|---------|----------|----------|
| `O` statt `0` | Normalisierung nötig | ✓ Whitelist verhindert |
| `I` statt `1` | Normalisierung nötig | ✓ Whitelist verhindert |
| `x1OO` statt `x100` | Normalisierung nötig | ✓ Bessere Zeichen-Erkennung |
| Fehlende führende Ziffer | Preis-Korrektur nötig | ✓ Bessere Ziffern-Erkennung |
| Zeichen verschluckt | Stackgrößen-Heuristik | ✓ canvas_size + mag_ratio |
| Noise-Zeichen | Regex-Filter nötig | ✓ Whitelist blockt |

---

## 🧪 Testen

### 1. Vergleich Alt vs. Neu:

```bash
python scripts/test_ocr_improvements.py
```

**Output:**
- `debug_proc_old.png` - Altes Preprocessing
- `debug_proc_new.png` - Neues Preprocessing (sollte schärfer/kontrastreicher sein)
- `debug_ocr_*.txt` - OCR-Ergebnisse zum Vergleichen

### 2. Live-Test im Tracker:

```python
# In tracker.py single_scan()
text = extract_text(proc, use_roi=True, method='both')
```

→ Mit `method='both'` kann man beide Engines vergleichen.

---

## ⚙️ Tuning

Falls die OCR noch Probleme macht:

### Preprocessing anpassen (utils.py:preprocess()):

```python
# Bei schlechten Screenshots: Noise-Reduction aktivieren
preprocess(img, adaptive=True, denoise=True)  # statt denoise=False

# Mehr Kontrast (falls UI zu dunkel):
clahe = cv2.createCLAHE(clipLimit=2.0, ...)  # statt 1.5

# Stärkere Schärfung (falls Text unscharf):
# Erhöhe Werte im Schärfungskernel von 3 auf 4

# Alte aggressive Binarisierung NICHT verwenden!
# Dies zerstört Game-UI-Text
```

### EasyOCR-Parameter anpassen (utils.py:extract_text()):

```python
# Mehr Text erkennen (bei fehlendem Text):
text_threshold=0.6,  # statt 0.7
low_text=0.3,        # statt 0.4

# Weniger False Positives (bei zu viel Müll):
text_threshold=0.8,  # höher
contrast_ths=0.4,    # höher

# NICHT zu niedrig setzen! (sonst Müll wie bei V2 Initial)
```

### ROI anpassen (utils.py:detect_log_roi()):

```python
# Log-Region weiter oben:
roi_y_start = int(h * 0.2)  # statt 0.3

# Ganze Höhe (kein ROI):
return (0, 0, w, h)
```

---

## 🎯 Nächste Schritte

1. **Testen im Live-Betrieb** (mehrere Sessions)
2. **Parsing-Heuristiken vereinfachen:**
   - Welche Normalisierungen sind noch nötig?
   - Können wir `LETTER_TO_DIGIT` reduzieren?
   - Können wir Preis-Korrekturen vereinfachen?
3. **Performance messen:**
   - Ist die neue Pipeline langsamer?
   - Falls ja: Denoising optional machen
4. **Dokumentieren welche Heuristiken obsolet sind**

---

## 📝 Konfiguration

Alle Tuning-Parameter sind dokumentiert in:
- `config.py` (EasyOCR-Init + Kommentare)
- `utils.py` (Preprocessing + OCR-Funktionen)

---

## 🐛 Bekannte Einschränkungen & Lessons Learned

1. **Aggressive Binarisierung funktioniert NICHT für Game-UIs**
   - Zerstört klaren UI-Text komplett
   - EasyOCR arbeitet besser mit Graustufen-Bildern
   - Lösung: Nur sanfte Kontrastverstärkung
   
2. **Noise-Reduction ist unnötig bei Game-UIs**
   - Game-Screenshots sind nicht verrauscht
   - Kostet nur Zeit (~100-200ms) und verwischt Details
   - Standardmäßig deaktiviert: `denoise=False`
   
3. **Zu aggressive EasyOCR-Parameter → Müll-Output**
   - text_threshold < 0.7 erkennt Noise als Text
   - contrast_ths < 0.3 erzeugt False Positives
   - Lösung: Standard-Parameter oft besser für klare UIs
   
4. **ROI-Detection ist simpel**
   - Nutzt nur Heuristik (untere 70%)
   - Funktioniert aber gut für BDO Market-Window
   
5. **Tesseract Whitelist ist strikt**
   - Blockiert auch seltene aber legitime Zeichen
   - Bei Bedarf erweitern

---

## ✅ Erfolg messen

Gute Indikatoren:
- ✓ Weniger "Unknown Items" in der DB
- ✓ Weniger fehlerhafte Mengen (x0, x1)
- ✓ Weniger Preis-Korrekturen im Log
- ✓ Mehr erfolgreiche Fuzzy-Matches
- ✓ Weniger Duplikate

---

**Version:** OCR V2 (2025-10-11)  
**Status:** ✅ Implementiert, Testing ausstehend
