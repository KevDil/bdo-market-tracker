# Partial Delta Accumulation Fix

**Date**: 2025-10-20  
**Status**: ✅ Implemented & Tested  
**Branch**: feature/detail-window-capture

## Problem

Detail-Window-Monitoring erkannte Balance- und Warehouse-Änderungen, aber **speicherte keine Transaktionen**.

### Root Cause

BDO aktualisiert **Balance und Warehouse asynchron**:

```
19:39:12: Baseline: Balance=204,639,381,895, Warehouse=5,000
19:39:13: Change #1: Balance -102,874,500, Warehouse +0 → ❌ REJECTED
19:39:14: Change #2: Balance +0, Warehouse +5,000 → ❌ REJECTED
19:39:16: Change #3: Balance -98,000,000, Warehouse +0 → ❌ REJECTED
```

Die **Validierung war zu streng** und verlangte BEIDE Deltas **gleichzeitig**:

```python
# OLD (BROKEN):
if balance_delta >= 0 or warehouse_delta <= 0:
    return None  # REJECT
```

**Result**: Alle Transaktionen wurden abgelehnt, weil Balance und Warehouse **nie im selben Scan** geändert wurden.

---

## Solution: Partial Delta Accumulation

Implementierung einer **Delta-Akkumulation** über mehrere Scans:

### Architecture

```
Scan 1: Balance -100k, Warehouse +0
  → Akkumuliere: partial_balance_delta = -100k
  → Warte auf Warehouse-Change...

Scan 2: Balance +0, Warehouse +5000
  → Akkumuliere: partial_warehouse_delta = +5000
  → BEIDE Deltas vorhanden → Erstelle Transaktion ✅
  → Reset: partial_balance_delta = 0, partial_warehouse_delta = 0
```

### Implementation Details

#### 1. State Storage (`tracker.py` Line 227-228)

```python
# Partial Delta Accumulation (handles asynchronous Balance/Warehouse updates)
self._detail_partial_balance_delta = 0  # Akkumulierter Balance-Delta
self._detail_partial_warehouse_delta = 0  # Akkumulierter Warehouse-Delta
```

#### 2. Reset Logic (`_reset_detail_window_state()`)

```python
def _reset_detail_window_state(self):
    """Reset Detail-Fenster State."""
    self._detail_window_active = False
    self._detail_window_type = None
    self._detail_window_item = None
    self._detail_baseline_balance = None
    self._detail_baseline_warehouse = None
    self._detail_last_metrics = None
    self._detail_confirmation_pending = False
    self._detail_confirmation_timestamp = None
    self._detail_partial_balance_delta = 0  # NEW
    self._detail_partial_warehouse_delta = 0  # NEW
```

#### 3. Delta Accumulation (`_infer_transaction_from_deltas()` Line 2210-2225)

```python
# ========== DELTA ACCUMULATION ==========
# Akkumuliere Balance-Deltas
if balance_delta != 0:
    self._detail_partial_balance_delta += balance_delta
    if self.debug:
        log_debug(f"[DETAIL] Accumulated balance delta: {self._detail_partial_balance_delta:+,} (this scan: {balance_delta:+,})")

# Akkumuliere Warehouse-Deltas
if warehouse_delta != 0:
    self._detail_partial_warehouse_delta += warehouse_delta
    if self.debug:
        log_debug(f"[DETAIL] Accumulated warehouse delta: {self._detail_partial_warehouse_delta:+,} (this scan: {warehouse_delta:+,})")
```

#### 4. Updated Validation (Buy-Item Example, Line 2250-2260)

```python
# Buy: Balance sinkt, Warehouse steigt
# Prüfe ob BEIDE Deltas jetzt vorhanden sind
if self._detail_partial_balance_delta >= 0 or self._detail_partial_warehouse_delta <= 0:
    # Noch nicht beide Deltas vorhanden → Weiter akkumulieren
    if self.debug and (balance_delta != 0 or warehouse_delta != 0):
        log_debug(f"[DETAIL] Buy-Transaction incomplete: balance_delta={self._detail_partial_balance_delta}, warehouse_delta={self._detail_partial_warehouse_delta} (waiting for both)")
    return None

# BEIDE Deltas vorhanden → Transaction erstellen
gross_price = abs(self._detail_partial_balance_delta)
quantity = self._detail_partial_warehouse_delta
```

#### 5. Reset After Success (Line 2340-2343)

```python
if self.debug:
    log_debug(f"[DETAIL] ✅ Inferred transaction: {transaction_type} {quantity}x {corrected_name} @ {gross_price} Silver (total)")

# Reset partial deltas nach erfolgreicher Transaktion
self._detail_partial_balance_delta = 0
self._detail_partial_warehouse_delta = 0

return transaction
```

---

## Test Coverage

### Unit Tests (`test_partial_delta_accumulation.py`)

**10 Tests, alle bestanden:**

1. ✅ `test_buy_transaction_partial_deltas_balance_first` - Balance zuerst, dann Warehouse
2. ✅ `test_buy_transaction_partial_deltas_warehouse_first` - Warehouse zuerst, dann Balance
3. ✅ `test_sell_transaction_partial_deltas` - Sell-Transaction Akkumulation
4. ✅ `test_lion_blood_exact_scenario` - Exakte Replay der Real-World-Logs
5. ✅ `test_multiple_accumulations_before_complete` - Mehrere Balance-Changes vor Warehouse
6. ✅ `test_reset_detail_window_state_clears_partial_deltas` - Reset-Logik
7. ✅ `test_invalid_item_name_with_whitelist_check` - Item-Name Validierung
8. ✅ `test_sequential_transactions_reset_accumulator` - Reset zwischen Transaktionen
9. ✅ `test_zero_deltas_dont_change_accumulator` - Zero-Deltas ändern nichts
10. ✅ `test_sell_transaction_with_set_price_validation` - Sell mit set_price

### Integration Tests

**45/45 Tests bestanden:**
- 10 neue Partial-Delta Tests
- 19 bestehende Detail-Window-Transaction Tests
- 16 bestehende Metrics-Extraction Tests

---

## Expected Behavior After Fix

### Before (Broken)

```
19:39:12: [DETAIL] Entered buy_item window
19:39:13: [DETAIL] Change detected in buy_item
   Balance: 204639381895 → 204536507395 (Δ -102,874,500)
   Warehouse: 5000 → 5000 (Δ +0)
❌ [DETAIL] Buy-Transaction rejected: balance_delta=-102874500, warehouse_delta=0

19:39:14: [DETAIL] Change detected in buy_item
   Balance: 204536507395 → 204536507395 (Δ +0)
   Warehouse: 5000 → 10000 (Δ +5000)
❌ [DETAIL] Buy-Transaction rejected: balance_delta=0, warehouse_delta=5000
```

**NO TRANSACTIONS SAVED** ❌

### After (Fixed)

```
19:39:12: [DETAIL] Entered buy_item window
19:39:13: [DETAIL] Change detected in buy_item
   Balance: 204639381895 → 204536507395 (Δ -102,874,500)
   Warehouse: 5000 → 5000 (Δ +0)
[DETAIL] Accumulated balance delta: -102,874,500 (this scan: -102,874,500)
[DETAIL] Buy-Transaction incomplete: balance_delta=-102874500, warehouse_delta=0 (waiting for both)

19:39:14: [DETAIL] Change detected in buy_item
   Balance: 204536507395 → 204536507395 (Δ +0)
   Warehouse: 5000 → 10000 (Δ +5000)
[DETAIL] Accumulated warehouse delta: +5,000 (this scan: +5,000)
✅ [DETAIL] ✅ Inferred transaction: buy 5000x Lion Blood @ 102874500 Silver (total)
✅ [DETAIL] ✅ Transaction saved successfully
```

**TRANSACTION SAVED IMMEDIATELY** ✅

---

## Performance Impact

- ✅ **Minimal**: Only 2 additional integer fields per MarketTracker instance
- ✅ **No extra OCR calls**: Uses existing scan data
- ✅ **No timing dependencies**: Works regardless of scan intervals
- ✅ **Graceful degradation**: Falls back to log-based detection if delta-monitoring fails

---

## Edge Cases Handled

1. **Multiple balance changes before warehouse update**: Accumulates all balance deltas
2. **Zero deltas**: No-op, accumulator unchanged
3. **Invalid item names**: Transaction rejected but deltas preserved (could be fixed with better item name)
4. **Sequential transactions**: Accumulator resets after each successful transaction
5. **Window type changes**: Full state reset including accumulators
6. **Manual state reset**: Clears all accumulators

---

## Migration Notes

### Breaking Changes
- **NONE**: Fully backward-compatible

### Required Updates
- **tracker.py**: Updated (Lines 227-228, 2171, 2210-2343)
- **tests/unit/test_partial_delta_accumulation.py**: New test file

### Database Changes
- **NONE**: No schema changes required

---

## Verification Checklist

Before deploying to production:

- [x] All 45 unit tests pass
- [x] No syntax errors in tracker.py
- [x] Lion Blood exact scenario replays correctly
- [ ] Real-world testing with 2x Lion Blood purchases in-game
- [ ] Log validation: Check for "Accumulated balance delta" and "Inferred transaction" messages
- [ ] DB validation: Confirm 2 separate transactions saved during detail window, not on overview return

---

## Next Steps

1. **Real-World Testing**: Test with actual game (2x Lion Blood purchases)
2. **Log Validation**: Verify accumulated delta messages appear
3. **DB Check**: Confirm transactions saved during detail window
4. **Performance Monitoring**: Watch for any unexpected scan delays
5. **Documentation Update**: Update AGENTS.md with new behavior

---

## References

- **Issue**: Lion Blood 2x purchases saved via log-based fallback, not delta-monitoring
- **Root Cause Analysis**: Balance/Warehouse updates are asynchronous in BDO
- **Solution Pattern**: Partial-Delta Accumulation with stateful tracking
- **Test Suite**: `test_partial_delta_accumulation.py` (10 tests)
- **Implementation Commit**: feature/detail-window-capture branch
