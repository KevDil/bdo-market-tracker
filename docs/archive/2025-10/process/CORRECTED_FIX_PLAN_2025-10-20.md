# Corrected Fix Plan - Window-Close Force-Save Only
**Datum**: 2025-10-20 23:30 UTC  
**Branch**: feature/detail-window-capture  
**Status**: 🔴 KRITISCHER BUG + UNNÖTIGER CODE

---

## Korrektur: Fix #1 ist UNNÖTIG

### Falsche Annahme
❌ Es gibt zwei Wege ins Detail-Fenster:
- "Collect" Button → Preorder automatisch collected
- "Relist" Button → Preorder NICHT collected

### Realität
✅ Es gibt **NUR EINEN** Weg ins Detail-Fenster:
- **"Relist" Button** → Preorder wird **MIT dem ersten Kauf** collected

❌ "Collect" Button öffnet **KEIN** Detail-Fenster (direkte Aktion)

### Konsequenz
**Fix #1 (pending_collect_qty) ist komplett UNNÖTIG!**

**Beweis (Lion Blood Test)**:
```
Baseline: warehouse=23,048 (alter Bestand, KEINE Preorder)
Kauf #1: warehouse 23,048 → 33,048 (Δ +10,000)
        balance -95,500,000
→ System erkannte korrekt: 10,000x = 5000 Preorder + 5000 Kauf ✅
```

Das System funktioniert **bereits perfekt** für den Relist-Flow!

---

## Aktuelle Code-Probleme

### Problem #1: Unnötiger Code (Fix #1)
**Was zu entfernen ist**:
1. State-Variable: `self._detail_pending_collect_qty`
2. Warehouse-Only Delta Logic (Line 2350)
3. Kombination mit pending_collect_qty (Line 2463, 2430, 2660)
4. Reset in `_reset_detail_window_state()` (Line 2230)

**Dateien betroffen**:
- `tracker.py` (7 Änderungen rückgängig machen)

### Problem #2: Force-Save wird NIEMALS ausgelöst (Fix #2 - BUG!)
**Root Cause**: Force-Save Code liegt in falschem Block

```python
# tracker.py Line ~2869
if wtype in ("buy_item", "sell_item"):
    self._monitor_detail_window(wtype, full_text)  # ← Force-Save Code HIER
else:
    # Window closed → wtype = 'buy_overview'
    self._reset_detail_window_state()  # ← Spring direkt hier, OHNE Force-Save!
```

**Beweis (Lion Blood Test)**:
```
22:40:03 - Balance-Delta: -90M, Warehouse-Delta: 0
22:40:03 - Balance-Only Timer gestartet
22:40:06 - Fenster geschlossen (wtype='buy_overview')
22:40:06 - Direkter Reset OHNE Force-Save
→ Transaktion verloren! ❌
```

---

## Korrigierter Fix-Plan

### 🔴 SCHRITT 1: Entferne Fix #1 komplett

#### 1.1 Entferne State-Variable
```python
# tracker.py Line 241 - LÖSCHEN
self._detail_pending_collect_qty = 0  # FIX #1: ...
```

#### 1.2 Entferne Reset
```python
# tracker.py Line 2230 - LÖSCHEN
self._detail_pending_collect_qty = 0  # FIX #1: Reset pending collect
```

#### 1.3 Stelle Warehouse-Only Delta Logic wieder her
```python
# tracker.py Line 2358 - ERSETZEN
# ALT (FIX #1):
if self._detail_partial_warehouse_delta > 0 and self._detail_partial_balance_delta == 0:
    self._detail_pending_collect_qty += self._detail_partial_warehouse_delta
    # ... reset deltas ...
    return None

# NEU (Original):
if self._detail_partial_warehouse_delta > 0 and self._detail_partial_balance_delta == 0:
    if self.debug:
        log_debug(f"[DETAIL] Preorder-Collect detected: warehouse +{self._detail_partial_warehouse_delta}, balance unchanged")
        log_debug(f"[DETAIL] Waiting for actual purchase (balance negative) before saving transaction")
    return None
```

#### 1.4 Entferne Kombination bei normalen Käufen
```python
# tracker.py Line 2471 - LÖSCHEN
if self._detail_pending_collect_qty > 0:
    log_debug(f"[DETAIL] 🔵 Combining purchase ({quantity}x) with pending_collect ({self._detail_pending_collect_qty}x)")
    quantity += self._detail_pending_collect_qty
    self._detail_pending_collect_qty = 0
```

#### 1.5 Entferne Kombination bei Balance-Only Timeout
```python
# tracker.py Line 2438 - LÖSCHEN
if self._detail_pending_collect_qty > 0:
    if self.debug:
        log_debug(f"[DETAIL] 🔵 Combining balance-only ({estimated_qty}x) with pending_collect ({self._detail_pending_collect_qty}x)")
    estimated_qty += self._detail_pending_collect_qty
    self._detail_pending_collect_qty = 0
```

#### 1.6 Entferne Kombination bei Window-Close Force
```python
# tracker.py Line 2668 - LÖSCHEN
if self._detail_pending_collect_qty > 0:
    if self.debug:
        log_debug(f"[DETAIL] 🔶 Combining forced purchase ({estimated_qty}x) with pending_collect ({self._detail_pending_collect_qty}x)")
    estimated_qty += self._detail_pending_collect_qty
    self._detail_pending_collect_qty = 0
```

---

### 🟠 SCHRITT 2: Fixe Window-Close Force-Save (Fix #2)

#### 2.1 Neue Helper-Funktion erstellen
```python
# tracker.py Line ~2231 (nach _reset_detail_window_state)
def _force_save_pending_transaction(self) -> bool:
    """
    Force-Save einer pending Balance-Only Transaction.
    Wird aufgerufen wenn Detail-Fenster geschlossen wird BEVOR 3s Timeout.
    
    Returns:
        True wenn Transaction gespeichert wurde, False sonst
    """
    if self._detail_partial_balance_delta >= 0:
        return False  # Keine negative Balance-Delta
    
    if self._detail_balance_delta_timestamp is None:
        return False  # Timer nicht gestartet
    
    if self._detail_window_type != 'buy_item':
        return False  # Nur für Buy-Transaktionen
    
    if self.debug:
        log_debug(f"[DETAIL] 🔶 Window closed with pending balance-only transaction!")
        log_debug(f"[DETAIL] 🔶 Forcing balance-only save now (balance_delta={self._detail_partial_balance_delta})")
    
    # Get desired_price from last metrics
    desired_price = None
    if self._detail_last_metrics:
        desired_price = self._detail_last_metrics.get('desired_price')
    
    if not desired_price or desired_price <= 0:
        if self.debug:
            log_debug(f"[DETAIL] 🔶 No desired_price available - cannot force save")
        return False
    
    # Estimate quantity
    estimated_qty = abs(self._detail_partial_balance_delta) // desired_price
    
    # Validate quantity
    if not (1 <= estimated_qty <= 500000):
        if self.debug:
            log_debug(f"[DETAIL] 🔶 Estimated quantity {estimated_qty}x out of range - cannot force save")
        return False
    
    # Get item name
    item_name = self._detail_window_item
    if not item_name and self._detail_last_metrics:
        item_name = self._detail_last_metrics.get('item_name')
    
    if not item_name:
        if self.debug:
            log_debug(f"[DETAIL] 🔶 No item name available - cannot force save")
        return False
    
    # Validate item name
    from market_json_manager import correct_item_name
    corrected_result = correct_item_name(item_name)
    
    if not corrected_result or not corrected_result[0]:
        if self.debug:
            log_debug(f"[DETAIL] 🔶 Item name '{item_name}' not in whitelist - cannot force save")
        return False
    
    corrected_name = corrected_result[0]
    
    # Create transaction
    transaction = {
        'item_name': corrected_name,
        'quantity': estimated_qty,
        'price': abs(self._detail_partial_balance_delta),
        'transaction_type': 'buy',
        'timestamp': datetime.datetime.now(),
        'tx_case': 'buy_collect_balance_only_forced'
    }
    
    # Save transaction
    success = self.store_transaction_db(transaction)
    
    if success and self.debug:
        log_debug(f"[DETAIL] 🔶 Forced balance-only transaction saved: {estimated_qty}x @ {transaction['price']:,}")
    elif not success and self.debug:
        log_debug(f"[DETAIL] 🔶 Forced transaction not saved (duplicate or error)")
    
    return success
```

#### 2.2 Aufrufen in process_ocr_text() ELSE-Branch
```python
# tracker.py Line ~2882
else:
    # Nicht in Detail-Fenster
    if self._detail_window_active:
        # 🔴 FIX #2: Force-Save BEVOR Reset!
        self._force_save_pending_transaction()
        
        if self.debug:
            log_debug("[DETAIL] Left detail window - resetting state")
        self._reset_detail_window_state()
```

#### 2.3 Vereinfache _monitor_detail_window (entferne Force-Save Code)
```python
# tracker.py Line ~2651 - ERSETZEN
# ALT (FIX #2 - falsch platziert):
if current_balance is None or current_warehouse is None:
    # ... 50+ Zeilen Force-Save Code ...
    self._reset_detail_window_state()
    return

# NEU (vereinfacht):
if current_balance is None or current_warehouse is None:
    # Fenster geschlossen, aber noch im Item-Window-Loop
    # (sollte normalerweise nicht hier landen, aber Safety-Check)
    if self.debug:
        log_debug("[DETAIL] Metrics incomplete (window closed?) - waiting for next scan")
    return
```

---

### 🟡 SCHRITT 3: Behalte Fix #3 (Price-Similarity Dedupe)

**Keine Änderung nötig** - Fix #3 ist korrekt und funktioniert:
- ±10% Price-Toleranz in Log-based Dedupe
- Bevorzugt Detail-Window Preise
- Logging bei Price-Unterschieden

**Code bleibt** (tracker.py Line 2105-2135)

---

## Implementation-Reihenfolge

### Phase 1: Cleanup (Fix #1 entfernen)
1. ✅ Entferne `_detail_pending_collect_qty` State-Variable
2. ✅ Entferne alle pending_collect_qty Referenzen (6 Stellen)
3. ✅ Stelle Warehouse-Only Delta Logic wieder her
4. ✅ Test kompilieren

### Phase 2: Fix (Fix #2 korrekt platzieren)
1. ✅ Neue Funktion `_force_save_pending_transaction()` erstellen
2. ✅ Aufrufen in `process_ocr_text()` ELSE-Branch
3. ✅ Entferne Force-Save aus `_monitor_detail_window()`
4. ✅ Test kompilieren

### Phase 3: Test
1. ✅ Lion Blood Wiederholung
2. ✅ Verifiziere alle 3 Transaktionen gespeichert
3. ✅ Prüfe Logs für `🔶` Marker

---

## Erwartete Test-Ergebnisse

### Lion Blood Test (nach Fix)
**Setup**:
1. Warehouse: 38,048 Lion Blood
2. Relist auf 5000x Preorder
3. Kauf #1: 5000x @ 95.5M (Preorder collected)
4. Kauf #2: 5000x @ 95.5M
5. Kauf #3: 5000x @ 90M + neue Preorder
6. Sofort schließen (< 1s)

**Erwartung**:
```
buy | 10000x @ 95,500,000 | buy_collect_ui_inferred     ← Preorder + Kauf #1
buy | 5000x @ 95,500,000 | buy_collect_ui_inferred      ← Kauf #2
buy | 5000x @ 90,000,000 | buy_collect_balance_only_forced  ← Kauf #3 (Force-Save!)
```

**Logs**:
```
🔶 Window closed with pending balance-only transaction!
🔶 Forcing balance-only save now (balance_delta=-90000000)
🔶 Forced balance-only transaction saved: 5000x @ 90,000,000
```

---

## Zusammenfassung der Änderungen

### Zu entfernen (Fix #1)
- ❌ `self._detail_pending_collect_qty` (Line 241)
- ❌ Reset in `_reset_detail_window_state()` (Line 2230)
- ❌ Warehouse-Only speichern statt verwerfen (Line 2358)
- ❌ Kombination bei normalen Käufen (Line 2471)
- ❌ Kombination bei Balance-Only Timeout (Line 2438)
- ❌ Kombination bei Window-Close Force (Line 2668)

### Zu verschieben (Fix #2)
- ✅ Force-Save aus `_monitor_detail_window()` (Line 2651)
- ✅ In neue Funktion `_force_save_pending_transaction()` (Line 2231)
- ✅ Aufrufen in `process_ocr_text()` ELSE-Branch (Line 2882)

### Zu behalten (Fix #3)
- ✅ Price-Similarity Dedupe (Line 2105-2135)

---

## Datei-Änderungen

### tracker.py
- **Gelöscht**: 6 Stellen mit pending_collect_qty
- **Hinzugefügt**: 1 neue Funktion `_force_save_pending_transaction()`
- **Geändert**: 2 Stellen (ELSE-Branch, _monitor_detail_window)
- **Behalten**: Price-Similarity Dedupe

### Dokumentation
- **Zu löschen**: `PIG_BLOOD_FIXES_2025-10-20.md` (Fix #1 basiert auf falscher Annahme)
- **Zu behalten**: `LION_BLOOD_BUG_ANALYSIS_2025-10-20.md` (korrekte Analyse)
- **Neu**: Dieses Dokument (CORRECTED_FIX_PLAN)

---

**Status**: 🔴 BEREIT FÜR CLEANUP + FIX  
**Priority**: CRITICAL - Jede Balance-Only Transaction bei Window-Close geht verloren

---

**Ende des Plans**
