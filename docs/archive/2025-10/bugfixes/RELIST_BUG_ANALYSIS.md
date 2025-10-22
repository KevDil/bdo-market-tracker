# 🔴 RELIST BUG - Root Cause Analysis
**Date**: 2025-10-21 20:40  
**Status**: CRITICAL BUG IDENTIFIED

---

## 📊 TEST-SZENARIO (Tatsächlicher Ablauf)

### Ausgangssituation
```
Warehouse: 19,569 Trace of Nature
Aktiver Preorder: 4979x @ 766,766,000 (davon 2137x gefüllt)
Balance: 193,718,587,425 Silver
```

### User-Aktion (t=0)
**Click "Relist" auf bestehende Preorder**

### Was im Spiel passierte

**t=0.1s**: Detail-Window öffnet
```
✅ Baseline erfasst:
   - Balance: 193,718,587,425
   - Warehouse: 19,569 (KORREKT!)
   - Input Fields: 5,000x @ 157,000 = 785,000,000 (KORREKT!)
```

**t=0.3s**: Relist-Aktion durchgeführt
```
1. Alte Preorder auto-collected: 2,137x @ 329,098,000
2. Warehouse steigt: 19,569 → 21,706 (+2,137)
3. Neue Preorder gesetzt: 5,000x @ 785,000,000
4. Balance sinkt: 193,718,587,425 → 192,933,587,425 (-785,000,000)
```

**t=1.4s**: Detail-Window geschlossen (zurück zu Overview)

---

## ❌ WAS SCHIEFGING

### Erwartete DB-Einträge
```
PREORDERS:
❌ ALT: 4979x @ 766,766,000 → status='collected' (NICHT PASSIERT!)
❌ NEU: 5000x @ 785,000,000 → status='active' (NICHT ERSTELLT!)

TRANSACTIONS:
✅ Auto-Collect: 2137x @ 329,098,000 (GESPEICHERT via Overview-Fallback)

ZUSAMMENFASSUNG:
- 1/3 Komponenten gespeichert
- Alte Preorder NICHT als collected markiert
- Neue Preorder NICHT erstellt
```

### Tatsächliche DB-Einträge
```
PREORDERS:
ID=7: 4979x @ 766,766,000, status='active' (UNVERÄNDERT!)

TRANSACTIONS:
ID=3: 2137x @ 329,098,000, case='buy_relist_partial', time=20:31:00
```

---

## 🔍 ROOT CAUSE ANALYSIS

### Problem #1: Baseline Warehouse = None

**Log-Beweis**:
```
20:31:41.608731 [DETAIL] ⚡ BASELINE CAPTURED (warehouse=None moment)
```

**Ursache**: 
```python
# tracker.py L3543-3580: Baseline-Capture Code
if window_type == 'buy_item' and img is not None and proc_img is not None:
    # Input fields extraction...
    self._detail_cached_input_fields = input_fields
    
    # BUG: Warehouse wird NICHT im Baseline gesetzt!
    # _detail_baseline_warehouse bleibt None
```

**Warum ist das kritisch?**
- Ohne Baseline-Warehouse kann Delta-Detection nicht funktionieren
- `warehouse_delta = current_warehouse - baseline_warehouse` → `21706 - None = ERROR`
- Relist-Pattern-Erkennung schlägt fehl

### Problem #2: Balance-Extraction Failed

**Log-Beweis**:
```
20:31:43.017747 [DETAIL-EXTRACT] Balance: None
20:31:43.018630 [DETAIL-EXTRACT] No balance found in metrics, returning None
```

**Was passierte**:
1. **t=1.4s**: Zweiter Scan im Detail-Window
2. Balance-ROI OCR **schlägt fehl** (Balance: None)
3. System kann keine Deltas berechnen

**Warum schlägt Balance-OCR fehl?**
- Möglicherweise wurde Window bereits geschlossen (Hysteresis-Instabilität)
- Transaction-Log-Overlay könnte Balance-ROI überdecken
- Timing-Problem: OCR zu langsam für schnelle Window-Transitions

### Problem #3: Relist-Detection Wird Nie Erreicht

**Warum?**
```python
# tracker.py L3700+ (Delta-Detection Logic)
if balance_delta is None or warehouse_delta is None:
    # Cannot calculate deltas → RETURN early
    return
```

**Konsequenz**:
- Ohne Deltas wird `is_relist_with_autocollect` nie evaluiert
- Relist-Detection-Block (L3834-3972) wird **NIE AUSGEFÜHRT**
- Keine Preorder-Saves, keine Transaction-Saves

### Problem #4: Overview-Fallback Rettet Nur Transaction

**Was der Fallback tat**:
```
20:31:44.285904 [ORDER-COLLECTED] No matching preorder found
20:31:44.302314 DB SAVE: buy 2137x Trace of Nature (buy_relist_partial)
```

**Warum nur Transaction?**:
- Fallback parst "Transaction of Trace of Nature x2,137" → Speichert TX ✅
- Fallback sucht matching Preorder → **NICHT GEFUNDEN** ❌
  - Grund: Preorder hat 4979x, aber Auto-Collect war nur 2137x
  - `find_matching_preorder()` matched nicht (qty mismatch)
- "Placed order of" wird **NICHT geparst** (nur "Transaction of")

---

## 🎯 FIX-PLAN

### Phase 1: Fix Baseline-Capture ⚡ CRITICAL

**Problem**: Warehouse wird nie im Baseline gesetzt

**Lösung**:
```python
# tracker.py L3543-3580: Nach Input-Field-Extraction
if window_type == 'buy_item':
    # ... input fields extraction ...
    
    # FIX: Set baseline IMMEDIATELY with extracted metrics
    self._detail_baseline_balance = current_metrics.get('balance')
    self._detail_baseline_warehouse = current_metrics.get('warehouse_qty')
    self._detail_last_metrics = current_metrics.copy()
    
    if self.debug:
        log_debug(
            f"[DETAIL] 🎯 BASELINE SET: "
            f"Balance={self._detail_baseline_balance:,}, "
            f"Warehouse={self._detail_baseline_warehouse:,}"
        )
```

**Erwartete Logs nach Fix**:
```
[DETAIL] 🎯 BASELINE SET: Balance=193,718,587,425, Warehouse=19,569
```

### Phase 2: Robustere Delta-Detection

**Problem**: Wenn Balance/Warehouse OCR fehlschlägt → keine Deltas

**Lösung**: Retry-Mechanismus
```python
# Wenn current_metrics incomplete sind → trigger immediate rescan
if current_balance is None or current_warehouse is None:
    if self._detail_baseline_balance and self._detail_baseline_warehouse:
        # We have baseline but current metrics failed
        # → Trigger immediate rescan (OCR retry)
        self._request_immediate_rescan = max(self._request_immediate_rescan, 2)
        
        if self.debug:
            log_debug(
                f"[DETAIL] ⚠️ Metrics incomplete (balance={current_balance}, warehouse={current_warehouse}) "
                f"→ Retry OCR ({self._request_immediate_rescan}x)"
            )
        return
```

### Phase 3: Find-Matching-Preorder Fix

**Problem**: `find_matching_preorder()` matched nicht bei Partial-Collects

**Aktuell**:
```python
def find_matching_preorder(item_name, warehouse_delta, ...):
    # Sucht Preorder mit quantity == warehouse_delta
    # 4979 != 2137 → NO MATCH ❌
```

**Lösung**: Erweiterte Matching-Logik
```python
def find_matching_preorder(item_name, warehouse_delta, ...):
    # 1. Exact match (quantity == warehouse_delta)
    # 2. Partial match (warehouse_delta <= quantity_filled)
    # 3. Fallback: Match by item + recent timestamp
    
    # Try partial collect match
    cur.execute('''
        SELECT * FROM preorders
        WHERE item_name = ?
        AND status = 'active'
        AND quantity_filled >= ?
        AND timestamp >= datetime('now', '-5 minutes')
        ORDER BY timestamp DESC LIMIT 1
    ''', (item_name, warehouse_delta))
```

### Phase 4: Overview-Fallback Enhanced

**Problem**: Fallback parst nur "Transaction of", nicht "Placed order of"

**Lösung**: Parse ALLE Relist-Komponenten
```python
# Beim Overview-Return:
# 1. Parse "Transaction of" → Auto-Collect TX ✅
# 2. Parse "Withdrew order of" → Find old preorder, mark collected ✅ NEW!
# 3. Parse "Placed order of" → Create new preorder ✅ NEW!
```

---

## 🧪 TEST-PLAN

### Test 1: Baseline-Capture Fix Verification

```powershell
# 1. Code fixen (Phase 1)
# 2. GUI starten (Debug Mode)
python gui.py

# 3. Detail-Window öffnen (beliebiges Item)
# 4. Logs checken:
```

**Erwartete Logs**:
```
[DETAIL] 🎯 BASELINE SET: Balance=XXX, Warehouse=YYY
[DETAIL] ✅ Input fields cached: QQQx @ PPP
```

### Test 2: Relist Full-Flow

```powershell
# 1. Preorder platzieren: 5000x @ 770M
# 2. Warten bis teilweise gefüllt (z.B. 2000x)
# 3. "Relist" klicken
# 4. DB checken
```

**Erwartete DB-Einträge**:
```
PREORDERS:
✅ ALT: status='collected', quantity_filled=2000
✅ NEU: status='active', quantity=5000

TRANSACTIONS:
✅ Auto-Collect: 2000x @ calculated_price
```

### Test 3: Overview-Fallback Enhanced

```powershell
# Simuliere: Window schließt VOR Delta-Detection
# → Fallback muss alle Komponenten finden

# Erwartete Logs:
[DETAIL-FALLBACK] ✅ Found "Transaction of" → Auto-Collect
[DETAIL-FALLBACK] ✅ Found "Withdrew order" → Mark old preorder collected
[DETAIL-FALLBACK] ✅ Found "Placed order" → Create new preorder
```

---

## 🚨 PRIORITÄT

1. **CRITICAL**: Phase 1 (Baseline-Capture Fix) - OHNE DIES FUNKTIONIERT NICHTS
2. **HIGH**: Phase 3 (Find-Matching Fix) - Für Partial-Collects essentiell
3. **MEDIUM**: Phase 2 (Retry-Mechanismus) - Erhöht Robustheit
4. **MEDIUM**: Phase 4 (Enhanced Fallback) - Safety-Net

**Empfehlung**: Fix Phase 1+3 zusammen, dann testen!

---

## 📋 NÄCHSTE SCHRITTE

1. ✅ Analyse complete (diese Datei)
2. ⏳ **JETZT**: Phase 1 implementieren (Baseline-Fix)
3. ⏳ Phase 3 implementieren (Find-Matching-Fix)
4. ⏳ Test mit echtem Relist
5. ⏳ Logs analysieren
6. ⏳ Bei Bedarf: Phase 2+4 implementieren
