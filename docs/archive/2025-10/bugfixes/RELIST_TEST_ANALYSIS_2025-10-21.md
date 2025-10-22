# Relist Test Analysis - 2025-10-21 19:32

## Test-Szenario

**Initial State**:
- Warehouse: 14,148 Trace of Nature
- Alte Preorder: 5000x @ 770M (filled: 400x)

**User Action**: Click "Relist"

**Expected Outcome**:
1. Auto-Collect Transaction: 400x @ 61,600,000 Silver
2. Alte Preorder: Status → 'collected'
3. Neue Preorder: 5000x @ 770,000,000 Silver (status='active')

**Actual Outcome**:
- ❌ Keine Auto-Collect Transaction gespeichert
- ❌ Alte Preorder NICHT als collected markiert
- ❌ Neue Preorder: 5000x @ 770M wurde erstellt (ID=5), **ABER ohne Auto-Collect Detection!**

## Timeline - Was ist passiert?

### t=0: Overview Window (19:32:48)
```
OCR-Text zeigt:
- "Placed order of Trace of Nature x5,000 for 770,000,000 Silver"
- "Withdrew order of Trace of Nature xl,700 for 261,800,000 silver"
```

**System-Verhalten**:
```
[PREORDER] No active preorder to cancel: Trace of Nature x1700 @ 261,800,000
skip preorder-only (placed+withdrew without transaction) for item='Trace of Nature' - no actual purchase
```

**Problem #1**: OCR las "x**1,700**" statt "x**4,600**" → Falsche Quantity!
**Problem #2**: System übersprang den Eintrag weil "placed+withdrew ohne transaction" als "nur Preorder-Log" interpretiert wurde

### t=2 seconds: Detail-Window Opens (19:32:50)

**Baseline Capture**:
```
[DETAIL] ⚡ BASELINE CAPTURED (single-sample, warehouse=None moment)
   Window: buy_item
   Item: Trace of Nature
   Warehouse: 14,148  ✅
   Balance: 190,993,406,575  ✅
```

**✅ Baseline korrekt gesetzt!**

**OCR-Text**:
```
Continue? Yes (ENTER) No (ESC) Desired Price use Capacity ,206.2 / 11,000 VT 
MAX 154,000 MIN Desired Amount
Trace of Nature
Balance 190,993,406,575
14,148 Warehouse Quantity
```

**Problem #3**: Keine expliziten Werte für "Desired Price" und "Desired Amount" im OCR!
- OCR zeigt nur "MAX 154,000 MIN" und "Desired Amount" Labels
- Die eigentlichen **INPUT-WERTE FEHLEN** im OCR-Output!

### t=4 seconds: Window Close / Overview Return (19:32:52)

**OCR zeigt NEUEN Overview-Text**:
```
2025.10.21 19.32 Placed order of Trace of Nature x5,000 for 770,000,000 Silver
2025.10.21 19.32 Withdrew order of Trace of Nature x4,600 for 708,400,000 silver
2025.10.21 19.32 Transaction of Trace of Nature X400 61,600,000 Silver has been complet
```

**CRITICAL**: Jetzt sind die korrekten Werte sichtbar!
- Withdrew: **x4,600** (vorher wurde "x1,700" gelesen)
- Transaction: **x400** @ 61,600,000

**System-Status**: Detail-Window war schon geschlossen → System war zurück im Overview
**Metrics Extraction**: `Balance: None`, `Warehouse: None` → Kein Delta erkannt

## Root Causes

### 1. **OCR las Input-Felder NICHT aus**

**Problem**: Die `detect_detail_preorder_input_roi()` Funktion wurde NIE aufgerufen!

**Beweise aus Logs**:
```
[DETAIL-EXTRACT] Extracted metrics for buy_item:
   Balance: 190993406575
   Warehouse: 14148
   Item: Trace of Nature
```

**Was fehlt**: KEIN Log-Eintrag wie:
```
[PREORDER-INPUT] OCR (X.Xms): Desired Price: 154,000 Desired Amount: 5000
[PREORDER-INPUT] ✅ SUCCESS: 5,000x @ 154,000
```

**Warum**: Die `_extract_preorder_input_fields()` Methode wird nur aufgerufen wenn:
1. `_detect_preorder_placement()` aufgerufen wird
2. `img` und `proc_img` übergeben werden

**Aber**: `_detect_preorder_placement()` wird nur bei **Balance-Delta** aufgerufen!

### 2. **Kein Balance-Delta erkannt**

**Erwartung**: Bei Relist sollte `balance_delta = -770,000,000` (neue Preorder) erkannt werden

**Realität**: 
```
t=0: Baseline captured: balance=190,993,406,575, warehouse=14,148
t=2: Next scan: Balance: None, Warehouse: None
```

**Problem**: Der zweite Scan nach Baseline-Capture hatte `Balance=None` und `Warehouse=None`!
- OCR konnte die Werte nicht mehr extrahieren (vermutlich weil Window schon am Schließen war)
- Ohne gültige Werte → Kein Delta → Keine Preorder-Detection

### 3. **Timing-Problem: Window zu schnell geschlossen**

**Timeline**:
```
t=0.0s (19:32:50.829): Baseline captured (Balance=190.99B, Warehouse=14148)
t=0.0s (19:32:50.833): Burst-Mode aktiviert (30s @ 80ms polling)
t=1.4s (19:32:52.280): Nächster Scan → Balance=None, Warehouse=None
```

**Problem**: Zwischen Baseline (t=0) und nächstem Scan (t=1.4s) ist die Transaktion passiert UND das Window wurde geschlossen!

**Erwartete Scans**:
```
t=0.0s: Baseline (14148 warehouse, 190.99B balance)
t=0.08s: Scan #1 (sollte 14548 warehouse, ~190.22B balance zeigen) ← RELIST!
t=0.16s: Scan #2 (Delta erkannt)
```

**Tatsächliche Scans**:
```
t=0.0s: Baseline
t=1.4s: Balance=None (Window schon geschlossen??)
```

**CRITICAL**: Der erste Burst-Scan nach Baseline kam VIEL zu spät (1.4s statt 0.08s)!

### 4. **Transaction-Log wurde nicht verarbeitet**

**Overview-Log nach Window-Close zeigt**:
```
2025.10.21 19.32 Transaction of Trace of Nature X400 61,600,000 Silver
```

**Aber**: Dieser Log wurde NICHT als Transaction gespeichert!

**Warum**: Vermutlich weil:
1. System war schon zurück im Overview
2. Baseline wurde bereits aktualisiert
3. Transaction-Line wurde als "schon verarbeitet" markiert

## Fix-Plan

### Phase 1: Burst-Scan Timing Fix (CRITICAL)

**Problem**: Burst-Scans kommen zu spät (1.4s statt 0.08s)

**Root Cause**: `_request_immediate_rescan` wird auf 3 gesetzt, aber der nächste Scan passiert trotzdem erst nach 1.4s

**Fix**: 
1. Prüfe `_request_immediate_rescan` Logic in `single_scan()`
2. Stelle sicher dass `time.sleep(0.05)` tatsächlich verwendet wird
3. Verifiziere dass keine anderen Delays existieren

**Code-Location**: `tracker.py` → `single_scan()` Methode

```python
while self._request_immediate_rescan > 0 and self.running:
    time.sleep(0.05)  # ← Wird das wirklich ausgeführt?
    img2 = self._capture_frame()
    if img2 is None or not self.running:
        break
    self._process_image(img2, context='quick', allow_debug=False)
    self._request_immediate_rescan -= 1
```

### Phase 2: Proaktive Input-ROI-Extraktion (CRITICAL)

**Problem**: `_extract_preorder_input_fields()` wird nur bei Balance-Delta aufgerufen

**Fix**: Extrahiere Input-Felder **SOFORT bei Baseline-Capture**!

**Rationale**:
- Bei Relist: Input-Felder zeigen die NEUEN Preorder-Werte
- Diese Werte sind BEREITS beim ersten Frame nach Window-Open sichtbar
- Wir müssen sie NICHT erst bei Balance-Delta auslesen

**Implementation**:
```python
# In _monitor_detail_window(), nach Baseline-Capture:
if not self._detail_window_active:
    # ... Baseline-Capture Code ...
    
    # ✅ NEW: Extract preorder input fields IMMEDIATELY
    if window_type == 'buy_item' and img is not None and proc_img is not None:
        input_fields = self._extract_preorder_input_fields(
            img=img,
            proc_img=proc_img,
            window_type=window_type
        )
        if input_fields:
            # Store for later use
            self._detail_pending_preorder_input = input_fields
            if self.debug:
                log_debug(
                    f"[DETAIL] Input fields cached: "
                    f"{input_fields['quantity']:,}x @ {input_fields['price']:,}"
                )
```

### Phase 3: Relist-Pattern Detection (HIGH)

**Problem**: System kann nicht unterscheiden zwischen:
- Neuer Preorder (balance↓, warehouse=0)
- Relist mit Auto-Collect (balance↓, warehouse↑)

**Fix**: Verwende gecachte Input-Fields + Delta-Pattern

**Detection Logic**:
```python
# Wenn Balance-Delta erkannt wird:
if balance_delta < 0:  # Preorder platziert
    # Check warehouse
    if warehouse_delta > 0:
        # RELIST with Auto-Collect!
        # 1. Save auto-collect transaction
        # 2. Mark old preorder as collected
        # 3. Create new preorder from input fields
    else:
        # Simple new preorder
        # Create preorder from input fields
```

### Phase 4: Transaction-Log Fallback (MEDIUM)

**Problem**: Wenn Detail-Window zu schnell schließt, wird Auto-Collect nicht erkannt

**Fix**: Nutze Transaction-Log als Fallback

**Logic**:
```python
# Nach Detail-Window Exit:
if self._detail_window_active:
    # Check if we have a pending preorder detection
    if self._detail_pending_preorder_input:
        # Scan overview log for "Transaction of [item]"
        # If found: Save as auto-collect, mark old preorder collected
```

### Phase 5: OCR-Quality für Input-ROI verbessern (LOW)

**Problem**: Input-Felder werden möglicherweise nicht sauber ausgelesen

**Fix**:
1. Teste mit echtem Screenshot aus `debug/debug_preorder_input_buy_item_orig.png`
2. Optimiere Preprocessing für Input-ROI
3. Erweitere Pattern-Matching für verschiedene OCR-Varianten

## Testing Plan

### Test 1: Burst-Scan Timing
```python
# Add debug logging:
log_debug(f"[BURST-DEBUG] _request_immediate_rescan={self._request_immediate_rescan}")
log_debug(f"[BURST-DEBUG] Sleeping 0.05s before rapid scan")
```

**Expected**: Rapid scans sollten alle ~50-80ms kommen

### Test 2: Input-Field Extraction
```python
# Test mit existierendem Screenshot:
python -c "
from utils import detect_detail_preorder_input_roi, preprocess
import cv2
img = cv2.imread('debug/debug_buy_item_full_orig.png')
proc = preprocess(img)
roi = detect_detail_preorder_input_roi(proc, 'buy_item')
print(f'ROI: {roi}')
# OCR des ROI durchführen
"
```

### Test 3: Live Relist
1. Auto-Track starten
2. Preorder mit teilweiser Füllung erstellen
3. "Relist" klicken
4. Logs prüfen:
   - `[DETAIL] Input fields cached: ...`
   - `[PREORDER-PLACED] ... method: input_fields_roi`
   - `[AUTO-COLLECT] Detected: ...`

## Priority

1. **CRITICAL**: Burst-Scan Timing Fix (Phase 1)
2. **CRITICAL**: Proaktive Input-ROI-Extraktion (Phase 2)
3. **HIGH**: Relist-Pattern Detection (Phase 3)
4. **MEDIUM**: Transaction-Log Fallback (Phase 4)
5. **LOW**: OCR-Quality Improvements (Phase 5)

## Next Steps

1. ✅ Analysiere `single_scan()` Code
2. ✅ Finde Ursache für 1.4s Delay
3. ✅ Implementiere proaktive Input-Field-Extraktion
4. Test mit Live-Relist
