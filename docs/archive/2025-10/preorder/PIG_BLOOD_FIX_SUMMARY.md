# Pig Blood Test: Korrigierte Analyse & Fix-Strategie

**Datum**: 2025-10-21  
**Status**: Analysis Complete, Implementation Pending  

---

## 🎯 Executive Summary

Der Pig Blood Test hat **3 Hauptprobleme** offenbart:

1. ❌ **Warehouse-Surplus nicht erkannt** → Auto-Collect verpasst, Plausibilitätscheck rejected
2. ❌ **Balance-Delta-Akkumulation** → Multiple Transactions in eine gemerged
3. ❌ **Neue Preorder nicht erkannt** → Detection läuft nur bei `warehouse_delta == 0`

**Root Cause**: Detail-Window verwendet **Fixed Baseline** (nur am Eintritt gesetzt) statt **Rolling Baseline** (nach jeder Transaction updated).

---

## 🔍 Was wirklich passiert ist

### **Timeline (OCR-Log-Analyse)**

```
T=0 (18:01:10.043): Detail-Window öffnen
   ✅ Baseline captured: Balance=193.283M, Warehouse=0

T=1 (18:01:10.733): Kauf #1 + Preorder Auto-Collect
   OCR: Balance=193.267M (-15.75M), Warehouse=10,000 (+10k)
   Implied Price: 15.75M / 10k = 1,575 Silver/item
   Plausibilitätscheck: 1,575 < 2,524 (85% von 2,970) → ❌ REJECTED!
   System: "Likely OCR error - waiting for next scan..."

T=2 (18:01:12.404): Kauf #2
   OCR: Balance=193.251M (-31.5M total), Warehouse=15,000 (+15k total)
   Implied Price: 31.5M / 15k = 2,100 Silver/item
   Plausibilitätscheck: 2,100 < 2,524 → ❌ REJECTED!
   System: Weiterhin wartend...

T=3 (18:01:15.324): Neue Preorder platziert
   OCR: Balance=193.237M (-45.95M total), Warehouse=15,000 (unchanged!)
   Implied Price: 45.95M / 15k = 3,063 Silver/item
   Plausibilitätscheck: 3,063 > 2,524 → ✅ PASS!
   System: "Inferred transaction: 15000x @ 45,950,000"
   → Gespeichert als EINE Transaction!

T=4 (18:01:17.955): Detail-Window schließen
   Transaction-Log sichtbar:
   - "Placed order of Pig Blood x5,000 for 14,450,000 Silver"
   - "Purchased Pig Blood x5,000 for 15,750,000 Silver" (2x)
   - "Transaction of Pig Blood x5,000 worth 13,750,000 Silver has been completed"
   → Parsing überspringt "placed-only" Einträge (KORREKT!)
```

---

## 🐛 Probleme im Detail

### **Problem 1: Warehouse-Surplus → Plausibilitätscheck Fail**

**Was passierte**:
- Kauf #1: 5000x @ 15,75M = 3,150 Silver/item
- **Auto-Collect**: +5000x @ 0 Silver (kostet nichts!)
- **Total**: 10,000x für 15,75M = **1,575 Silver/item**
- Plausibilitätscheck-Minimum: 2,970 * 0.85 = **2,524 Silver/item**
- **1,575 < 2,524** → REJECTED als "OCR-Fehler"

**Warum passierte es**:
```python
# tracker.py (line ~3250)
implied_price_per_item = abs(balance_delta) / warehouse_delta
# = 15,750,000 / 10,000 = 1,575

if implied_price_per_item < (base_price * 0.85):
    log_debug("[DETAIL] Likely OCR error in balance - waiting for next scan...")
    return  # ❌ VERWIRFT gültige Daten!
```

**Fehlende Logik**:
```python
# SOLLTE SEIN:
expected_qty = calculate_expected_qty(balance_delta, item_name)
# = 15,750,000 / 2,970 ≈ 5,303 → rounded to 5,000

warehouse_surplus = warehouse_delta - expected_qty
# = 10,000 - 5,000 = +5,000

if warehouse_surplus > 0:
    # Check for preorder auto-collect!
    preorder = find_matching_preorder(item_name, surplus=5000)
    if preorder:
        # Adjust price calculation
        total_price = balance_delta + preorder['price']
        # = 15,750,000 + 13,750,000 = 29,500,000
        implied_price = total_price / warehouse_delta
        # = 29,500,000 / 10,000 = 2,950 Silver/item ✅ PASS!
```

---

### **Problem 2: Balance-Delta-Akkumulation**

**Was passierte**:
- System verwendet **Fixed Baseline** (nur am Window-Eintritt gesetzt)
- Alle Balance-Änderungen akkumulieren bis Plausibilitätscheck passt:
  ```
  Scan 1: -15.75M → Rejected
  Scan 2: -31.5M (kumuliert) → Rejected
  Scan 3: -45.95M (kumuliert) → Accepted!
  ```
- **Result**: EINE Transaction mit 15,000x @ 45,95M (FALSCH!)

**Korrekte Erwartung**:
```
Transaction #1: 10,000x @ 29,500,000 (Kauf #1 + Auto-Collect)
Transaction #2: 5,000x @ 15,750,000 (Kauf #2)
(Neue Preorder: NICHT als Transaction, sondern in preorders-Tabelle)
```

**Fehlende Logik**:
```python
# SOLLTE SEIN (nach jeder Transaction):
if tx_saved:
    # Rolling Baseline Update
    self._detail_baseline_balance = current_balance
    self._detail_baseline_warehouse = current_warehouse
    
    # Reset accumulators
    self._detail_partial_balance_delta = 0
    self._detail_partial_warehouse_delta = 0
    
    log_debug(f"[DETAIL] 🔄 Rolling baseline updated")
```

---

### **Problem 3: Neue Preorder nicht erkannt**

**Was passierte**:
- Preorder-Detection läuft NUR bei: `balance_delta < 0 AND warehouse_delta == 0`
  ```python
  # tracker.py (line 3280)
  if balance_delta < 0 and warehouse_delta == 0 and window_type == 'buy_item':
      preorder_detected = self._detect_preorder_placement(...)
  ```
- **Aber**: Nach Kauf #2 war `warehouse_delta` bereits **+15,000**!
- **Neue Preorder**: Balance -14,45M, Warehouse +0 (relativ zu letzter Transaction)
- **Detection-Trigger**: `balance_delta=-45.95M, warehouse_delta=+15000` → **KEIN Match!**

**Fehlende Logik**:
```python
# SOLLTE SEIN (nach jeder Transaction):
if tx_saved:
    # ... rolling baseline update ...
    
    # Setup preorder check for next scan
    self._detail_await_preorder_check = True
    self._detail_preorder_check_baseline = {
        'balance': current_balance,
        'warehouse': current_warehouse,
        'timestamp': now
    }

# LATER (in next scan, ~0.5s später):
if self._detail_await_preorder_check:
    balance_delta_new = current_balance - check_baseline['balance']
    warehouse_delta_new = current_warehouse - check_baseline['warehouse']
    
    if balance_delta_new < 0 and warehouse_delta_new == 0:
        # JETZT Match! Preorder detected!
        preorder_detected = self._detect_preorder_placement(...)
```

---

## 🛠️ Fix-Strategie (3 Phasen)

### **Phase 1: Rolling Baseline** (2-3h)

**Änderung**: Nach jeder gespeicherten Transaction → Update Baseline.

**Files**:
- `tracker.py` → `_monitor_detail_window()` (line ~3330)

**Logic**:
```python
tx_result = self._process_detail_window_delta(...)

if tx_result:
    # Transaction saved successfully
    
    # NEW: Rolling baseline update
    self._detail_baseline_balance = current_balance
    self._detail_baseline_warehouse = current_warehouse
    self._detail_last_metrics = current_metrics.copy()
    
    # Reset delta accumulators
    self._detail_partial_balance_delta = 0
    self._detail_partial_warehouse_delta = 0
    self._detail_balance_changed_once = False
    self._detail_warehouse_changed_once = False
    
    if self.debug:
        log_debug(
            f"[DETAIL] 🔄 Rolling baseline updated: "
            f"Balance={current_balance:,}, Warehouse={current_warehouse}"
        )
```

**Test**:
- Nach Kauf #1 (10k warehouse, -15.75M): Baseline = (193.267M, 10k)
- Nach Kauf #2 (15k warehouse, -31.5M total): Baseline = (193.251M, 15k)
- Neue Preorder (15k warehouse, -14.45M relativ): Delta = (-14.45M, 0)

---

### **Phase 2: Preorder-Check nach Transaction** (2h)

**Änderung**: Nach Transaction → Wait 0.5s → Check for new balance decrease.

**Files**:
- `tracker.py` → Add state flags (`_detail_await_preorder_check`)
- `tracker.py` → `_monitor_detail_window()` (after transaction saved)

**Logic**:
```python
# After transaction saved:
if tx_result:
    # ... rolling baseline update (Phase 1) ...
    
    # NEW: Setup preorder check
    self._detail_await_preorder_check = True
    self._detail_preorder_check_baseline = {
        'balance': current_balance,
        'warehouse': current_warehouse,
        'timestamp': datetime.datetime.now()
    }

# LATER (in next scan):
if self._detail_await_preorder_check:
    check_baseline = self._detail_preorder_check_baseline
    time_elapsed = (now - check_baseline['timestamp']).total_seconds()
    
    # Wait at least 0.5s for UI to settle
    if time_elapsed < 0.5:
        return
    
    # Calculate NEW delta (relative to post-transaction baseline)
    balance_delta_new = current_balance - check_baseline['balance']
    warehouse_delta_new = current_warehouse - check_baseline['warehouse']
    
    if balance_delta_new < 0 and warehouse_delta_new == 0:
        # Preorder detected!
        preorder_detected = self._detect_preorder_placement(
            item_name=self._detail_window_item,
            balance_delta=balance_delta_new,
            current_metrics=current_metrics,
            timestamp=now
        )
        
        if preorder_detected:
            # Reset check
            self._detail_await_preorder_check = False
            
            # Update baseline AGAIN
            self._detail_baseline_balance = current_balance
            self._detail_last_metrics = current_metrics.copy()
    
    # Timeout after 3 seconds (no preorder placed)
    if time_elapsed > 3.0:
        self._detail_await_preorder_check = False
```

**Test**:
- Nach Kauf #2: Check-Baseline = (193.251M, 15k)
- Nach 0.5s: Current = (193.237M, 15k)
- Delta = (-14.45M, 0) → **Match!** Preorder detected ✅

---

### **Phase 3: Auto-Collect Detection** (3-4h)

**Änderung**: Warehouse-Surplus-Check VOR Plausibilitätscheck.

**Files**:
- `preorder_manager.py` (NEW FILE) → PreorderManager class
- `tracker.py` → Import PreorderManager
- `tracker.py` → `_monitor_detail_window()` (before plausibility check)
- `tracker.py` → Add `_calculate_expected_qty()` helper

**Logic** (siehe PIG_BLOOD_TEST_ANALYSIS_AND_FIX_PLAN.md, Phase 3)

**Test**:
- Kauf #1 (warehouse +10k, balance -15.75M):
  * Expected qty: ~5000 (calculated from balance/base_price)
  * Warehouse surplus: 10k - 5k = +5000
  * Preorder found: 5000x @ 13.75M
  * Adjusted price: 15.75M + 13.75M = 29.5M
  * Implied price: 29.5M / 10k = 2,950 Silver/item
  * Plausibility: 2,950 > 2,524 → ✅ PASS!

---

## 📊 Expected Results (After Implementation)

### **Database State** (post-Pig-Blood-test):

```sql
-- preorders table:
SELECT * FROM preorders WHERE item_name = 'Pig Blood';

-- Expected:
-- ID=1: 5000x @ 13,750,000, status='collected', 
--       collected_at='2025-10-21 18:01:10', collected_tx_id=<TX1_ID>
-- ID=2: 5000x @ 14,450,000, status='active',
--       collected_at=NULL, collected_tx_id=NULL

-- transactions table:
SELECT * FROM transactions WHERE item_name = 'Pig Blood' ORDER BY id;

-- Expected:
-- ID=<TX1>: 10000x @ 29,500,000 (buy_collect_ui_inferred)
--           timestamp='2025-10-21 18:01:10'
-- ID=<TX2>: 5000x @ 15,750,000 (buy_collect_ui_inferred)
--           timestamp='2025-10-21 18:01:12'
```

### **Transaction Count**: 2 (not 1!)
### **Preorder Count**: 2 (1 collected, 1 active)

---

## 📝 Important Notes

### **"placed-only" Zeilen SOLLEN übersprungen werden!**

Im Transaction-Log erscheinen "Placed order" Einträge, aber diese werden **korrekt** übersprungen:

```python
# parsing.py
if anchor_types == {'placed'}:
    logger.debug(f"skip placed-only entry for item='{item_name}'")
    continue  # ✅ RICHTIG!
```

**Grund**: Preorder-Erfassung erfolgt **im Detail-Window** via:
1. `_detect_preorder_placement()` (via UI-Metriken: Orders-Field)
2. **NICHT** via Transaction-Log-Parsing!

Das Transaction-Log-Parsing ist nur für **Overview-Fenster** relevant (collect/relist).

---

### **Diskrepanz zwischen alter und neuer Preorder**

Die alte Preorder (13,75M) und neue Preorder (14,45M) haben **unterschiedliche Preise**.
Dies ist **normal** und **kein Bug**:

- Alte Preorder: Platziert am 2025-10-21 13:57 @ 13,750,000 Silver
- Neue Preorder: Platziert am 2025-10-21 18:01 @ 14,450,000 Silver
- **Preisdifferenz**: User hat höheren Preis gewählt (bessere Chance auf Fill)

Die Diskrepanz war **NICHT** die Ursache des Problems. Die Ursache war:
1. Fixed Baseline (statt Rolling)
2. Fehlende Warehouse-Surplus-Detection
3. Fehlende Post-Transaction-Preorder-Check

---

## 🎯 Next Steps

1. **Implement Phase 1** (Rolling Baseline) → TEST
2. **Implement Phase 2** (Preorder-Check) → TEST
3. **Implement Phase 3** (Auto-Collect) → TEST
4. **Full Pig Blood Replay** → Validate alle 4 erwarteten DB-Einträge

**Estimated Time**: 7-9 hours total

---

## 🔗 References

- **Full Analysis**: `docs/PIG_BLOOD_TEST_ANALYSIS_AND_FIX_PLAN.md`
- **OCR Logs**: `ocr_log.txt` (2025-10-21 18:01:07 - 18:01:17)
- **Implementation Plan**: `PREORDER_TRACKING_IMPLEMENTATION_PLAN.md` (v2.0 Final)
