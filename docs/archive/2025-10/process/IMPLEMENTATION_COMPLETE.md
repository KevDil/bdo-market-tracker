# Implementation Complete: Preorder Tracking mit Rolling Baseline

**Datum**: 2025-10-21  
**Status**: ✅ IMPLEMENTIERT - Bereit für Tests  
**Branches**: feature/detail-window-capture

---

## 🎯 Implementierte Features

### **Phase 1: Rolling Baseline** ✅

**Datei**: `tracker.py`  
**Zeilen**: ~3620-3640

**Änderungen**:
```python
# Nach erfolgreicher Transaction-Speicherung:
if transaction:
    success = self.store_transaction_db(transaction)
    
    # Reset Partial-Deltas
    self._detail_partial_balance_delta = 0
    self._detail_partial_warehouse_delta = 0
    self._detail_balance_delta_timestamp = None
    self._detail_balance_changed_once = False
    self._detail_warehouse_changed_once = False
    
    # NEW: Update Rolling Baseline
    self._detail_baseline_balance = current_balance
    self._detail_baseline_warehouse = current_warehouse
    
    log_debug("[DETAIL] 🔄 Rolling baseline updated")
```

**Effekt**:
- Jede Transaction wird von **neuem** Baseline gemessen
- Keine Akkumulation über mehrere Transaktionen hinweg
- **Pig Blood Szenario**: 3 separate Transaktionen statt 1 merged!

---

### **Phase 2: Post-Transaction Preorder Check** ✅

**Datei**: `tracker.py`  
**Zeilen**: ~3210-3270 + ~3640-3660

**State-Variablen** (neu hinzugefügt):
```python
self._detail_await_preorder_check = False
self._detail_preorder_check_baseline = None
self._detail_last_transaction_saved = None
```

**Detection Logic** (in `_monitor_detail_window()`):
```python
# NACH Rolling Baseline Update:
if window_type == 'buy_item':
    self._detail_await_preorder_check = True
    self._detail_preorder_check_baseline = {
        'balance': current_balance,
        'warehouse': current_warehouse,
        'timestamp': datetime.datetime.now()
    }

# AM ANFANG der Methode (vor Change-Detection):
if self._detail_await_preorder_check and window_type == 'buy_item':
    time_elapsed = (now - check_baseline['timestamp']).total_seconds()
    
    if time_elapsed >= 0.5:  # Wait 0.5s for UI settle
        balance_delta_new = current_balance - check_baseline['balance']
        warehouse_delta_new = current_warehouse - check_baseline['warehouse']
        
        if balance_delta_new < 0 and warehouse_delta_new == 0:
            # PREORDER DETECTED!
            preorder_detected = self._detect_preorder_placement(...)
            
            if preorder_detected:
                # Update baseline AGAIN (preorder consumed balance)
                self._detail_baseline_balance = current_balance
                return
```

**Effekt**:
- Nach jedem Kauf: 0,5s Wartezeit, dann Check ob neue Preorder platziert wurde
- **Pattern**: `balance↓, warehouse=0` → Preorder!
- **Pig Blood Szenario**: Neue Preorder (5000x @ 14.45M) wird ERKANNT und gespeichert!

---

### **Phase 3: Auto-Collect Detection + Plausibilitätscheck-Fix** ✅

**Dateien**: 
- `preorder_manager.py` (bereits vorhanden, genutzt)
- `tracker.py` (Integration + Helper-Methods)

**Neue Methode**: `_calculate_expected_qty()` ✅
```python
def _calculate_expected_qty(self, balance_delta: float, item_name: str) -> int:
    """
    Calculate expected purchase quantity from balance delta.
    Used for auto-collect surplus detection.
    
    Algorithm:
    1. Get base_price from BDO API
    2. Estimate unit price = base_price * 0.925 (middle of range)
    3. Calculate qty = balance_delta / unit_price
    4. Round to 1000/100/1 (typical purchase increments)
    """
    base_price = self._get_base_price(item_name)
    estimated_unit_price = base_price * 0.925
    estimated_qty = balance_delta / estimated_unit_price
    
    # Round to nearest 1000, 100, or 1
    if estimated_qty >= 500:
        return round(estimated_qty / 1000) * 1000
    elif estimated_qty >= 50:
        return round(estimated_qty / 100) * 100
    else:
        return int(estimated_qty)
```

**Plausibilitätscheck-Anpassung** ✅ (Lines ~3540-3590):
```python
if window_type == 'buy_item':
    # NEW: Check for warehouse surplus BEFORE price check
    expected_qty = self._calculate_expected_qty(abs(balance_delta), item_name)
    warehouse_surplus = warehouse_delta - expected_qty
    
    # Default: Use full warehouse_delta for price check
    effective_qty_for_price_check = warehouse_delta
    
    if warehouse_surplus > 0 and expected_qty > 0:
        # Check if preorder exists for this surplus
        preorder = self._preorder_manager.find_matching_preorder(
            item_name=item_name,
            warehouse_delta=warehouse_surplus,
            balance_delta=abs(balance_delta),
            timestamp=datetime.datetime.now()
        )
        
        if preorder:
            # Surplus explained by preorder auto-collect!
            # Adjust effective_qty to ONLY the purchase part
            effective_qty_for_price_check = expected_qty
            
            log_debug(
                f"[PREORDER-AUTOCOLLECT] Warehouse surplus detected: "
                f"{warehouse_surplus}x (matched preorder ID={preorder['id']})"
            )
    
    # Now run plausibility check with ADJUSTED quantity
    implied_price_per_item = abs(balance_delta) / abs(effective_qty_for_price_check)
    
    if implied_price_per_item < min_price_per_item:
        log_debug("[DETAIL] ⚠️ PLAUSIBILITY FAIL")
        return
```

**PreorderManager Integration** ✅:
```python
# In __init__():
self._preorder_manager = PreorderManager(debug=self.debug)

# Nach Transaction-Save:
if success and preorder_correction:
    self._preorder_manager.mark_collected(
        preorder_id=preorder_correction['id'],
        collected_at=datetime.datetime.now(),
        transaction_id=None
    )
```

**Effekt**:
- **Warehouse-Surplus** wird VOR Plausibilitätscheck erkannt
- **Expected Qty**: 15.75M / 2,970 = 5,303 → 5,000x
- **Surplus**: 10,000 - 5,000 = **+5,000x**
- **Preorder Match**: 5000x @ 13.75M → ✅ Found!
- **Adjusted Price**: 15.75M / **5,000x** (nicht 10,000x!) = 3,150 Silver/item ✅ PASS!
- **Alte Preorder**: Status='collected', collected_tx_id=<TX_ID>

---

## 🔧 State-Management-Änderungen

**Neue State-Variablen** (Lines ~253-257):
```python
# Rolling Baseline + Preorder Detection (Phase 1 & 2)
self._detail_await_preorder_check = False
self._detail_preorder_check_baseline = None
self._detail_last_transaction_saved = None
```

**State-Reset** (`_reset_detail_window_state()`):
```python
# NEW (Phase 2): Reset preorder check state
self._detail_await_preorder_check = False
self._detail_preorder_check_baseline = None
self._detail_last_transaction_saved = None
```

---

## 📊 Expected Results (Pig Blood Replay)

### **Database State VORHER** (broken):
```sql
-- preorders:
ID=1: Pig Blood 5000x @ 13.75M, status='active' ❌

-- transactions:
ID=1: Pig Blood 5000x @ 15.45M
ID=3: Pig Blood 15000x @ 45.95M ❌ (merged!)
```

### **Database State NACHHER** (fixed):
```sql
-- preorders:
ID=1: Pig Blood 5000x @ 13.75M, 
      status='collected' ✅
      collected_tx_id=<TX1_ID> ✅
      
ID=2: Pig Blood 5000x @ 14.45M,
      status='active' ✅

-- transactions:
ID=<TX1>: Pig Blood 10000x @ 29,500,000 ✅
          (5k purchase + 5k preorder auto-collect)
          timestamp='2025-10-21 18:01:10'
          
ID=<TX2>: Pig Blood 5000x @ 15,750,000 ✅
          timestamp='2025-10-21 18:01:12'
```

**Transaction Count**: 2 (nicht 1!)  
**Preorder Count**: 2 (1 collected, 1 active)

---

## 🧪 Testing-Szenarien

### **Test 1: Simple Auto-Collect**
```
Setup:
  - Active preorder: 5000x @ 13.75M
  - Warehouse: 0

Action:
  - Buy 5000x @ 15.75M

Expected:
  ✅ Preorder auto-collected
  ✅ Transaction: 10000x @ 29.5M
  ✅ Old preorder status='collected'
  ✅ Warehouse: +10,000
```

### **Test 2: Buy + Buy + Preorder (Pig Blood)**
```
Setup:
  - Active preorder: 5000x @ 13.75M
  - Warehouse: 0

Actions:
  1. Buy 5000x @ 15.75M (auto-collects preorder)
  2. Buy 5000x @ 15.75M
  3. Place preorder 5000x @ 14.45M

Expected:
  ✅ Transaction #1: 10000x @ 29.5M
  ✅ Transaction #2: 5000x @ 15.75M
  ✅ Old preorder: status='collected'
  ✅ New preorder: 5000x @ 14.45M (active)
  ✅ Total warehouse: +15,000
```

### **Test 3: Preorder Only (no auto-collect)**
```
Setup:
  - No active preorder
  - Warehouse: 0

Action:
  - Place preorder 5000x @ 14.45M

Expected:
  ✅ Preorder stored: 5000x @ 14.45M (active)
  ✅ NO transaction created
  ✅ Balance: -14.45M
  ✅ Warehouse: +0
```

---

## 🚀 Next Steps

### **Immediate**:
1. ✅ **Code Review** - Syntax-Check passed!
2. 🔄 **Test mit GUI** - Starte tracker und führe Pig Blood Replay durch
3. 🔍 **Database Validation** - Überprüfe erwartete Einträge

### **Validation**:
```bash
# Nach Test:
python inspect_db.py

# Erwartete Ausgabe:
# - preorders: 2 entries (1 collected, 1 active)
# - transactions: 2 entries (nicht 1!)
# - Preise korrekt (29.5M + 15.75M, nicht 45.95M merged)
```

### **Regression Testing**:
- Test alle 9 Szenarien aus PREORDER_TRACKING_IMPLEMENTATION_PLAN.md
- Validiere Edge Cases (partial fills, auto-preorder creation)
- Performance-Check (keine Latenz durch zusätzliche DB-Lookups)

---

## 📝 Code-Änderungen Summary

**Dateien geändert**:
- ✅ `tracker.py` (~150 neue Zeilen)

**Dateien unverändert** (bereits vorhanden):
- ✅ `preorder_manager.py` (bereits komplett implementiert!)
- ✅ `database.py` (preorders-Tabelle bereits vorhanden)

**Neue Methoden**:
- ✅ `_calculate_expected_qty()` (Phase 3)

**Modifizierte Methoden**:
- ✅ `_monitor_detail_window()` (Phase 1+2+3 Integration)
- ✅ `_reset_detail_window_state()` (Phase 2 State-Reset)

**Zeilen-Änderungen**:
- ✅ +~200 Zeilen (neue Logik)
- ✅ ~50 Zeilen (angepasste Plausibilitätscheck)

---

## 🎯 Kritische Verbesserungen

### **Vor der Implementierung**:
- ❌ Fixed Baseline → Multi-Transaction-Batching
- ❌ Keine Preorder-Detection nach Transactions
- ❌ Plausibilitätscheck rejected Auto-Collect (zu billiger Preis)
- ❌ Keine Warehouse-Surplus-Analyse

### **Nach der Implementierung**:
- ✅ Rolling Baseline → Jede Transaction isoliert
- ✅ Post-Transaction Preorder-Check (0.5s delay)
- ✅ Plausibilitätscheck berücksichtigt Auto-Collect
- ✅ Warehouse-Surplus → Preorder-Match → Adjusted Price

---

## 🔗 Dokumentation

- **Plan**: `docs/PIG_BLOOD_TEST_ANALYSIS_AND_FIX_PLAN.md`
- **Summary**: `docs/PIG_BLOOD_FIX_SUMMARY.md`
- **This File**: `docs/IMPLEMENTATION_COMPLETE.md`

---

**Status**: 🟢 **READY FOR TESTING**

**Next Action**: Führe Pig Blood Replay-Test durch und validiere Database-Einträge!
