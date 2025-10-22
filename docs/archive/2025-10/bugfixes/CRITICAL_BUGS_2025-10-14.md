# 🚨 Critical Bugs - 2025-10-14 10:32

## Test Case
User kaufte 4 Transaktionen im Buy-Tab:
1. ❌ 54x Powder of Time für 216540 um 09:43
2. ❌ 2386x Powder of Time für 9567860 um 09:48  
3. ✅ 111x Special Bluffer Mushroom für 4040400 um 10:12
4. ❌ 770x Powder of Time für 3087700 um 10:32

**Ergebnis**: Nur 1 von 4 Transaktionen gespeichert! (25% Success Rate) ❌

---

## 🔍 Root Causes

### Bug #1: OCR Pattern matcht keine Quantity ohne "x" Präfix ❌
```
OCR-Text: "Transaction of Powder of Time 386 worth 9,567,860"
Erwartet: 2386x (qty=2386)
Problem: Pattern erwartet "xYYY" → findet nichts → qty=None
```

**Pattern (Zeile 21 in parsing.py):**
```python
_TRANSACTION_PATTERN = re.compile(r"Transaction of (.+?) worth", re.IGNORECASE)
```

**Problem**: Matched nur Item-Name, nicht Quantity!

**OCR-Text zeigt**:
```
Transaction of Powder of Time 386 worth 9,567,860
```

Das "2" wurde verschluckt → OCR sieht nur "386".

**Lösung**: Pattern muss robuster sein:
```python
# Aktuell:
r"Transaction of (.+?) worth"

# Besser:
r"Transaction of (.+?)\s+(?:x\s*)?(\d+)\s+worth"
```

---

### Bug #2: Fehlende Price bei älteren Transaktionen ❌
```
[DEBUG] structured: 2025-10-14 09:43:00 transaction item='Powder of Time' qty=54 price=None
[DEBUG] drop candidate: invalid/missing price (None)
```

**Problem**: Text ist zu weit rechts oder abgeschnitten → OCR kann "worth 216,540 Silver" nicht sehen.

**Ursache**: ROI ist zu klein!
```
[ROI] Applied: region=(0,0,1089,524)
```

**Lösung**: ROI vergr\u00f6\u00dfern auf `(0,0,1200,600)` oder dynamisch anpassen.

---

### Bug #3: Aktuelle Transaktion (770x) GAR NICHT erkannt ❌
**Problem**: Die 770x Transaktion erscheint NIRGENDS im Log!

**Mögliche Ursachen**:
1. **Transaktion war außerhalb des Scan-Bereichs** (ROI zu klein)
2. **Transaktion wurde zu schnell gescrollt** (nicht im Frame)
3. **Baseline hatte bereits 10:12 als newest → 10:32 wurde ignoriert** ❌❌❌

**Log zeigt**:
```
[DELTA] prev_max_ts=2025-10-14 10:12:00
```

**Das ist FALSCH!** Die 10:32 Transaktion ist NEUER als 10:12!

**Aber**: Im OCR-Text ist NICHTS über 10:32 oder 770x zu finden!

**Diagnose**: Die Transaktion war zum Zeitpunkt des Scans nicht im sichtbaren Bereich.

---

### Bug #4: `check_price_plausibility` Error ⚠️
```
[DEBUG] [PRICE] API check failed: cannot access local variable 'check_price_plausibility' where it is not associated with a value
```

**Problem**: In `tracker.py` Zeile 568:
```python
result = check_price_plausibility(candidate, 1, int(unit_price))
```

**Aber**: `check_price_plausibility` ist aus `utils` importiert (Zeile 35).

**Ursache**: Wahrscheinlich ein Scope-Problem oder die Funktion existiert nicht in `utils.py`.

**Check**: Ist `check_price_plausibility` in `utils.py` definiert?

---

### Bug #5: Falsche Quantity gespeichert ❌
```
[SAVE] ✅ buy buy_collect 1x Powder of Time price=9567860 ts=2025-10-14 10:12:00
```

**Erwartet**: 2386x für 9567860 → Unit Price = 4010 Silver/Stück  
**Gespeichert**: 1x für 9567860 → Unit Price = 9567860 Silver/Stück ❌

**Problem**: Quantity wurde nicht erkannt → Default=1

**Root Cause**: OCR erkannte "386" statt "2386", dann konnte Pattern die "386" nicht extrahieren.

---

## 🔧 Erforderliche Fixes (Priorität)

### Priority 1: ROI vergrößern 🔥
```python
# config.py
DEFAULT_REGION = (0, 0, 1200, 600)  # Aktuell: (0, 0, 1089, 524)
```

**Warum**: Mehr sichtbare Transaktionen erfassen.

---

### Priority 2: Transaction Pattern robuster machen 🔥
```python
# parsing.py Zeile 21
# ALT:
_TRANSACTION_PATTERN = re.compile(r"Transaction of (.+?) worth", re.IGNORECASE)

# NEU - mit optional Quantity:
_TRANSACTION_PATTERN = re.compile(
    r"Transaction of (.+?)(?:\s+x?\s*(\d+))?\s+worth\s+([0-9,\.]+)",
    re.IGNORECASE
)
```

**Oder noch robuster**:
```python
# Match auch wenn "xYYY" fehlt und direkt Zahl kommt
_TRANSACTION_PATTERN = re.compile(
    r"Transaction of (.+?)\s+(\d+)\s+worth\s+([0-9,\.]+)",
    re.IGNORECASE
)
```

---

### Priority 3: Baseline Reset-Funktion 🔥
**Problem**: User kann Baseline nicht manuell zurücksetzen.

**Lösung**: Button in GUI hinzufügen: "Reset Baseline"

```python
def reset_baseline():
    """Reset baseline to allow re-scanning old transactions."""
    save_state('last_overview_text', "")
    log_debug("[BASELINE] Manual reset - baseline cleared")
```

---

### Priority 4: Fix `check_price_plausibility` Error ⚠️
**Check**: Existiert die Funktion in `utils.py`?

**Wenn nicht**: Entferne den Check oder erstelle die Funktion.

---

### Priority 5: Quantity Extraction verbessern 🔥
**Problem**: "Transaction of Powder of Time 386 worth" matcht nicht.

**Ursache**: Pattern erwartet "x" vor Quantity.

**Lösung**: Pattern muss flexibler sein:
```python
# Akzeptiere:
# - "Transaction of Item x123 worth"
# - "Transaction of Item 123 worth"
# - "Transaction of Item xI23 worth" (OCR Fehler)
```

---

## 📊 Success Rate Analyse

| Transaktion | Zeit | Quantity | Price | Status | Grund |
|-------------|------|----------|-------|--------|-------|
| Powder of Time | 09:43 | 54 | 216540 | ❌ Failed | Price=None (OCR konnte nicht extrahieren) |
| Powder of Time | 09:48 | 2386 | 9567860 | ❌ Wrong | Gespeichert als 1x statt 2386x |
| Special Bluffer Mushroom | 10:12 | 111 | 4040400 | ✅ Success | Korrekt gespeichert |
| Powder of Time | 10:32 | 770 | 3087700 | ❌ Missing | Gar nicht erkannt (außerhalb ROI?) |

**Success Rate**: 25% (1/4) ❌

**Critical Issues**:
- 50% Missing (nicht erkannt oder dropped)
- 25% Wrong Data (falsche Quantity)
- 25% Success

---

## 🎯 Action Items

### Sofort (Heute):
- [ ] ROI von (0,0,1089,524) auf (0,0,1200,600) vergrößern
- [ ] Transaction Pattern robuster machen (ohne "x" Support)
- [ ] Baseline Reset-Button in GUI hinzufügen

### Wichtig (Diese Woche):
- [ ] `check_price_plausibility` Error fixen
- [ ] Quantity Extraction verbessern (auch ohne "x")
- [ ] OCR Region dynamisch anpassen (adaptive ROI)

### Nice-to-Have:
- [ ] Multi-Frame-Scanning (mehrere Frames pro Sekunde)
- [ ] Confidence Threshold für OCR-Ergebnisse
- [ ] Logging verbessern (mehr Debug-Info bei Fehlern)

---

## 💡 Lessons Learned

1. **ROI ist kritisch**: Zu klein → Transaktionen werden nicht erfasst
2. **OCR ist nicht perfekt**: Patterns müssen flexibel sein ("2386" wird zu "386")
3. **Baseline kann Probleme machen**: User braucht Reset-Funktion
4. **Testing ist wichtig**: 25% Success Rate ist inakzeptabel!

---

**Erstellt**: 2025-10-14 10:37  
**Status**: Critical - Requires Immediate Fix 🚨  
**Impact**: High - 75% Transaction Loss Rate
