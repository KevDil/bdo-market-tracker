# Lion Blood Test - Bug Analysis & Fix Plan
**Datum**: 2025-10-20 23:15 UTC  
**Branch**: feature/detail-window-capture  
**Status**: 🔴 KRITISCHER BUG GEFUNDEN

---

## Test-Szenario

### Setup
- **Initial Warehouse**: 23,048 Lion Blood (alter Bestand)
- **Aktion**: "Relist" auf 5000x Lion Blood Preorder klicken

### Erwartete Sequenz
1. ✅ **Relist** → Detail-Fenster öffnet OHNE preorder collect
2. ✅ **Kauf #1**: 5000x @ 95,500,000 → Preorder automatisch mit gecollected
3. ✅ **Kauf #2**: 5000x @ 95,500,000
4. ❌ **Kauf #3**: 5000x @ ??? mit neuer Preorder (5000x @ 90,000,000)
5. Detail-Fenster geschlossen

### Tatsächliche Ergebnisse
**Gespeicherte Transaktionen**:
```
2025-10-20 22:39:59 | buy | 10000x Lion Blood @ 95,500,000 | buy_collect_ui_inferred
2025-10-20 22:40:00 | buy | 5000x Lion Blood  @ 95,500,000 | buy_collect_ui_inferred
```

**Fehlende Transaktion**: Kauf #3 nicht gespeichert ❌

---

## Timeline-Analyse (aus ocr_log.txt)

### 22:39:57 - Detail-Fenster öffnet
```
[DETAIL] Entered buy_item window
   Item: Lion Blood
   Balance baseline: 178,872,189,115
   Warehouse baseline: 23,048  ← Alter Bestand, KEINE Preorder enthalten
```

**Wichtig**: Die 5000x Preorder wurden **NICHT** automatisch collected beim Öffnen!

---

### 22:39:59 - Kauf #1 (mit Auto-Collect)
```
[DETAIL] Change detected in buy_item
   Balance: 178,872,189,115 → 178,776,689,115 (Δ -95,500,000)
   Warehouse: 23,048 → 33,048 (Δ +10,000)

[DETAIL] ⚠️ Accumulated purchase detected: 10000x ≈ 2 buys @ 5000x each
[DETAIL] ✅ Inferred transaction: buy 10000x Lion Blood @ 95500000 Silver

DB SAVE: buy 10000x Lion Blood price=95500000 case=buy_collect_ui_inferred
```

**Analyse**:
- Balance-Delta: -95,500,000 (nur 1× Kauf, nicht 2×!)
- Warehouse-Delta: +10,000 (Preorder + Kauf)
- **System korrekt**: Erkannte dass 5000x Preorder + 5000x Kauf = 10,000x total

---

### 22:40:00 - Kauf #2
```
[DETAIL] Change detected in buy_item
   Balance: 178,776,689,115 → 178,681,189,115 (Δ -95,500,000)
   Warehouse: 33,048 → 38,048 (Δ +5,000)

DB SAVE: buy 5000x Lion Blood price=95500000 case=buy_collect_ui_inferred
```

**Analyse**: Normal, einzelner Kauf ohne Preorder ✅

---

### 22:40:03 - Kauf #3 + Neue Preorder (VERLOREN!)
```
[DETAIL] Change detected in buy_item
[DETAIL] Started balance_delta timer at 2025-10-20 22:40:03.308380
[DETAIL] Accumulated balance delta: -90,000,000 (this scan: -90,000,000)
[DETAIL] ⚠️ warehouse_delta=0 but balance negative - no 'Placed order' found, waiting...
[DETAIL] Buy-Transaction incomplete: balance_delta=-90000000, warehouse_delta=0 (waiting 0.00s/3.0s)
```

**Analyse**:
- Balance-Delta: -90,000,000 (Kauf #3 für 5000x)
- Warehouse-Delta: 0 (weil gleichzeitig neue Preorder placed!)
- Balance-Only Timer gestartet → Wartet auf 3s Timeout
- **Problem**: Fenster wurde vor Timeout geschlossen!

---

### 22:40:06 - Fenster geschlossen (3s später)
```
[WINDOW-HYSTERESIS] Unstable detection buy_overview, using stable state buy_item
window='buy_item' -> keine Auswertung

[DETAIL-EXTRACT] Extracted metrics for buy_item:
   Balance: None       ← Fenster geschlossen!
   Warehouse: None     ← Fenster geschlossen!
   Item: Orders 91897 Orders Completed 14896 ...  ← Overview OCR

[DETAIL-EXTRACT] No balance found in metrics, returning None
```

**Analyse**:
- OCR liest jetzt Overview-Screen (nicht mehr Detail-Fenster)
- Balance/Warehouse = None
- **Aber**: Window-Type ist noch `buy_item` (Hysteresis)

---

### 22:40:06 - Force-Save NICHT ausgelöst! 🔴
**Erwartung**: Force-Save sollte pending balance-only transaction speichern  
**Realität**: Nichts passiert, kein Log von Force-Save

**Warum?** → Code-Bug (siehe unten)

---

## Root Cause Analysis

### Bug #1: Force-Save wird NIEMALS erreicht

**Problem-Code** (tracker.py Line 2869):
```python
if wtype in ("buy_item", "sell_item"):
    self._monitor_detail_window(wtype, full_text)  # ← Force-Save Code hier
else:
    # Nicht in Detail-Fenster → Reset State
    if self._detail_window_active:
        self._reset_detail_window_state()  # ← Springt direkt hier!
```

**Bug-Sequenz**:
1. Detail-Fenster aktiv, `wtype = 'buy_item'`
2. Balance-Only Timer läuft (balance_delta = -90M, warehouse_delta = 0)
3. User schließt Fenster
4. OCR liest Overview → `detect_window_type()` returns `'buy_overview'`
5. `wtype = 'buy_overview'` → **ELSE-Branch**
6. `_reset_detail_window_state()` wird aufgerufen
7. **Force-Save Code wird NIEMALS erreicht** (liegt in `_monitor_detail_window`)

**Critical Issue**: Force-Save liegt in falschem Block!

---

### Bug #2: Hysteresis hilft nicht

Die Window-Hysteresis stabilisiert `wtype` über mehrere Scans:
```python
if wtype != self._stable_window:
    # Real transition confirmed
    self._stable_window = wtype
```

**Problem**: Sobald 2 aufeinanderfolgende Scans `'buy_overview'` erkennen, wird Hysteresis bestätigt und wir springen in ELSE-Branch → Reset ohne Force-Save.

---

### Bug #3: Metrics-Extraction gibt None zurück

Wenn Fenster geschlossen ist, returned `extract_detail_window_metrics()`:
```python
if current_balance is None:
    # Unvollständige Metriken → Weiter warten
    return  # ← FRÜHER EXIT!
```

Das bedeutet `current_metrics = None` und Force-Save Check wird nie erreicht.

**ABER WAIT**: Force-Save Code prüft ja:
```python
if current_balance is None or current_warehouse is None:
    # Force-Save Logic hier...
```

Das sollte eigentlich funktionieren! Warum wurde es nicht ausgelöst?

→ **Weil wir nie in `_monitor_detail_window()` kommen** (Bug #1)!

---

## Fix-Plan

### 🔴 FIX #1: Verschiebe Force-Save AUSSERHALB von _monitor_detail_window

**Problem**: Force-Save muss ausgelöst werden **BEVOR** `_reset_detail_window_state()`

**Lösung**: Check in `process_ocr_text()` BEVOR wir in ELSE-Branch springen

**Neuer Code** (tracker.py Line ~2880):
```python
# Fenster-Typ erkennen
if wtype in ("buy_item", "sell_item"):
    self._monitor_detail_window(wtype, full_text)
    # ... burst scan logic ...
else:
    # 🔴 FIX: Prüfe Force-Save BEVOR Reset!
    if self._detail_window_active:
        # Check if pending balance-only transaction
        if (self._detail_partial_balance_delta < 0 and 
            self._detail_balance_delta_timestamp is not None and
            self._detail_window_type == 'buy_item'):
            
            # Force-Save ausführen (analog zu Code in _monitor_detail_window)
            self._force_save_pending_transaction()
        
        # Dann Reset
        if self.debug:
            log_debug("[DETAIL] Left detail window - resetting state")
        self._reset_detail_window_state()
```

---

### 🟠 FIX #2: Extrahiere Force-Save in eigene Funktion

**Problem**: Force-Save Logic ist komplex (50+ Zeilen) und duplikation-anfällig

**Lösung**: Neue Helper-Funktion `_force_save_pending_transaction()`

**Neue Funktion**:
```python
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
    
    # Combine with pending_collect_qty
    if self._detail_pending_collect_qty > 0:
        if self.debug:
            log_debug(f"[DETAIL] 🔶 Combining forced purchase ({estimated_qty}x) with pending_collect ({self._detail_pending_collect_qty}x)")
        estimated_qty += self._detail_pending_collect_qty
        self._detail_pending_collect_qty = 0
    
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

---

### 🟡 FIX #3: Entferne Force-Save aus _monitor_detail_window

**Problem**: Duplikation, wird nie erreicht

**Lösung**: Ersetze mit Funktion-Call

**Alt** (tracker.py Line 2651):
```python
if current_balance is None or current_warehouse is None:
    # ... 50+ Zeilen Force-Save Code ...
    self._reset_detail_window_state()
    return
```

**Neu**:
```python
if current_balance is None or current_warehouse is None:
    # Fenster geschlossen, aber noch im Item-Window-Loop
    # (sollte normalerweise nicht hier landen, aber Safety-Check)
    if self.debug:
        log_debug("[DETAIL] Metrics incomplete (window closed?) - waiting for next scan")
    return
```

**Begründung**: Echter Force-Save passiert jetzt in `process_ocr_text()` ELSE-Branch

---

## Implementation-Plan

### Schritt 1: Neue Helper-Funktion erstellen
```python
# Nach _reset_detail_window_state() einfügen (Line ~2230)
def _force_save_pending_transaction(self) -> bool:
    # ... siehe FIX #2 ...
```

### Schritt 2: Aufrufen in process_ocr_text() ELSE-Branch
```python
# tracker.py Line ~2882
else:
    # Nicht in Detail-Fenster
    if self._detail_window_active:
        # FIX: Force-Save BEVOR Reset
        self._force_save_pending_transaction()
        
        if self.debug:
            log_debug("[DETAIL] Left detail window - resetting state")
        self._reset_detail_window_state()
```

### Schritt 3: Entferne Force-Save aus _monitor_detail_window
```python
# tracker.py Line ~2651
if current_balance is None or current_warehouse is None:
    if self.debug:
        log_debug("[DETAIL] Metrics incomplete - waiting")
    return
```

### Schritt 4: Test mit Lion Blood Wiederholung
**Erwartung**:
- Kauf #1: 10,000x @ 95.5M ✅
- Kauf #2: 5,000x @ 95.5M ✅
- Kauf #3: **5,000x @ 90M** (Force-Save) ✅

---

## Edge-Cases

### E1: Hysteresis verzögert Force-Save
**Szenario**: Fenster geschlossen, aber Hysteresis hält `wtype='buy_item'` für 1-2 Scans

**Erwartung**: 
- Scan #1: `wtype='buy_item'` → `_monitor_detail_window()` aufgerufen, Metrics = None → Early return
- Scan #2: `wtype='buy_overview'` → ELSE-Branch → Force-Save ausgelöst ✅

**Status**: Kein Problem, Force-Save wird spätestens bei Transition ausgelöst

---

### E2: Balance-Only Timer < 3s
**Szenario**: User schließt Fenster nach 1-2 Sekunden

**Erwartung**: Force-Save ignoriert Timeout, speichert sofort

**Code**:
```python
# Kein Timeout-Check in _force_save_pending_transaction!
# Speichert immer wenn balance_delta < 0 vorhanden
```

**Status**: Korrektes Verhalten ✅

---

### E3: Desired_price fehlt
**Szenario**: OCR konnte desired_price nicht extrahieren

**Erwartung**: Force-Save schlägt fehl, Transaktion verloren

**Mitigation**: Log-based Parsing sollte Transaktion retten

**Status**: Acceptable trade-off (sehr seltener Fall)

---

### E4: Placed Order mit Force-Save
**Szenario**: Kauf + neue Preorder, warehouse_delta = 0, Fenster geschlossen

**Erwartung**: 
- "Placed order" Detection schlägt fehl (Fenster schon geschlossen)
- Force-Save schätzt nur Kauf (ohne Preorder)
- **Richtig**: Preorder ist separate Transaktion (placed-only)

**Status**: Korrektes Verhalten ✅

---

## Rückwärtskompatibilität

### Code-Changes
- ✅ Neue Funktion `_force_save_pending_transaction()` (kein Breaking Change)
- ✅ Force-Save in ELSE-Branch verschoben (logischer Flow)
- ✅ `_monitor_detail_window()` vereinfacht (Duplikat entfernt)

### Tests
- ⏳ Lion Blood Test sollte jetzt 3 Transaktionen speichern
- ⏳ Pig Blood Test sollte unverändert funktionieren
- ⏳ Unit-Tests benötigen kein Update (keine API-Änderung)

### Performance
- ✅ Force-Save nur bei Window-Close (selten, < 1× pro Minute)
- ✅ Keine zusätzlichen OCR-Calls
- ✅ Keine DB-Overhead

---

## Test-Plan

### Lion Blood Wiederholung
1. Warehouse: 38,048 Lion Blood (nach erstem Test)
2. Platziere 5000x Preorder
3. Klicke "Relist"
4. Kaufe 5000x @ 95.5M (Preorder collected)
5. Kaufe 5000x @ 95.5M
6. Kaufe 5000x @ 90M + neue Preorder
7. **Sofort schließen** (< 1s)

**Erwartung**:
```
buy | 10000x @ 95,500,000 | buy_collect_ui_inferred
buy | 5000x @ 95,500,000 | buy_collect_ui_inferred
buy | 5000x @ 90,000,000 | buy_collect_balance_only_forced  ← NEU!
```

### Logs zu beachten
```
🔶 Window closed with pending balance-only transaction!
🔶 Forcing balance-only save now (balance_delta=-90000000)
🔶 Forced balance-only transaction saved: 5000x @ 90,000,000
```

---

## Zusammenfassung

### Problem
- ❌ Fix #2 (Window-Close Force-Save) wurde implementiert aber **NIEMALS ausgelöst**
- ❌ Force-Save Code liegt in `_monitor_detail_window()`, wird nur aufgerufen wenn `wtype in ("buy_item", "sell_item")`
- ❌ Bei Window-Close wechselt `wtype` zu `"buy_overview"` → ELSE-Branch → Direkter Reset ohne Force-Save

### Lösung
- ✅ Verschiebe Force-Save in `process_ocr_text()` ELSE-Branch
- ✅ Extrahiere in neue Funktion `_force_save_pending_transaction()`
- ✅ Aufrufen **BEVOR** `_reset_detail_window_state()`

### Erwartung
- ✅ Lion Blood Kauf #3 wird gespeichert (5000x @ 90M)
- ✅ Alle Window-Close Scenarios funktionieren
- ✅ Keine Duplikation von Force-Save Code

---

**Status**: 🔴 BEREIT FÜR IMPLEMENTATION  
**Priority**: CRITICAL - Jede Balance-Only Transaction bei Window-Close geht verloren

---

**Ende der Analyse**
