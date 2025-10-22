# Detail-Window State Machine - Mit Preorder-Tracking
**Version**: 2.0 (mit Fix #1 + Fix #2)  
**Datum**: 2025-10-20

---

## State-Diagramm

```
┌─────────────────────────────────────────────────────────────────────┐
│                     DETAIL-WINDOW INACTIVE                          │
│  _detail_window_active = False                                      │
│  _detail_pending_collect_qty = 0                                    │
└─────────────────┬───────────────────────────────────────────────────┘
                  │
                  │ Window-Type detected (buy_item/sell_item)
                  │
                  v
┌─────────────────────────────────────────────────────────────────────┐
│                  SET BASELINE (First Metrics Read)                  │
│  _detail_window_active = True                                       │
│  _detail_baseline_balance = current_balance                         │
│  _detail_baseline_warehouse = current_warehouse (DIREKT, keine      │
│                                                   Manipulation!)     │
│  _detail_partial_balance_delta = 0                                  │
│  _detail_partial_warehouse_delta = 0                                │
│  _detail_pending_collect_qty = 0                                    │
└─────────────────┬───────────────────────────────────────────────────┘
                  │
                  │ Monitor Deltas
                  │
                  v
┌─────────────────────────────────────────────────────────────────────┐
│                      DELTA ACCUMULATION                             │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ CASE 1: Warehouse-Only Delta (Preorder-Collect)             │  │
│  │  warehouse_delta > 0, balance_delta = 0                      │  │
│  │  → _detail_pending_collect_qty += warehouse_delta            │  │
│  │  → Reset partial deltas                                      │  │
│  │  → Return None (kein Save)                                   │  │
│  │  🔵 "Preorder-Collect detected, storing as pending"          │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ CASE 2: Placed Order Detection (warehouse_delta = 0)        │  │
│  │  balance_delta < 0, warehouse_delta = 0                      │  │
│  │  → Parse OCR for "Placed order x5,000"                       │  │
│  │  → Set warehouse_delta = placed_qty                          │  │
│  │  → Continue to CASE 3                                        │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ CASE 3: Both Deltas Present                                 │  │
│  │  balance_delta != 0, warehouse_delta != 0                    │  │
│  │  → quantity = warehouse_delta + _detail_pending_collect_qty  │  │
│  │  → gross_price = abs(balance_delta)                          │  │
│  │  → Create Transaction (tx_case=buy_collect_ui_inferred)      │  │
│  │  → Reset partial deltas (but NOT pending_collect_qty)        │  │
│  │  🔵 "Combining purchase with pending_collect"                │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ CASE 4: Balance-Only Timeout (3s)                           │  │
│  │  balance_delta < 0, warehouse_delta = 0, elapsed >= 3s       │  │
│  │  → estimated_qty = balance / desired_price                   │  │
│  │  → quantity = estimated_qty + _detail_pending_collect_qty    │  │
│  │  → Create Transaction (tx_case=buy_collect_balance_only)     │  │
│  │  → Reset partial deltas + pending_collect_qty                │  │
│  │  ⚠️ "Warehouse missing after 3s, using balance-only"         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ CASE 5: Window-Close Force-Save (NEW FIX #2)                │  │
│  │  current_balance = None (window closed)                      │  │
│  │  balance_delta < 0 (pending transaction)                     │  │
│  │  → estimated_qty = balance / desired_price                   │  │
│  │  → quantity = estimated_qty + _detail_pending_collect_qty    │  │
│  │  → Create Transaction (tx_case=buy_collect_balance_only_forced)│
│  │  → Reset ALL state (including pending_collect_qty)           │  │
│  │  🔶 "Window closed with pending, forcing save"               │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────┬───────────────────────────────────────────────────┘
                  │
                  │ Window closed OR Type changed
                  │
                  v
┌─────────────────────────────────────────────────────────────────────┐
│                    RESET STATE                                      │
│  _reset_detail_window_state()                                       │
│  → _detail_window_active = False                                    │
│  → _detail_partial_balance_delta = 0                                │
│  → _detail_partial_warehouse_delta = 0                              │
│  → _detail_pending_collect_qty = 0  (CRITICAL!)                     │
│  → All other state cleared                                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Transition Details

### T1: Window Open
**Trigger**: `detect_window_type()` returns `buy_item` or `sell_item`  
**Actions**:
1. Extract metrics (balance, warehouse, item_name, etc.)
2. Set baselines **directly** from first read (no manipulation)
3. Initialize partial deltas to 0
4. Initialize `pending_collect_qty` to 0
5. Mark window active

**Critical**: Baseline warehouse may already include collected preorder!

---

### T2: Warehouse-Only Delta (Preorder-Collect)
**Trigger**: `warehouse_delta > 0 AND balance_delta = 0`  
**Actions**:
1. Store warehouse_delta in `_detail_pending_collect_qty`
2. Accumulate if multiple preorder-collects
3. Reset partial deltas (clear for next transaction)
4. Return None (no transaction yet)

**Example**:
```
Baseline: warehouse=10,000 (preorder already collected at window open)
Delta: warehouse=0, balance=0
→ pending_collect_qty stays 0 (no new preorder)

Next preorder placed:
Delta: warehouse=+5000, balance=0
→ pending_collect_qty = 5000
```

---

### T3: Complete Transaction (Both Deltas)
**Trigger**: `balance_delta != 0 AND warehouse_delta != 0`  
**Actions**:
1. Calculate quantity: `warehouse_delta + pending_collect_qty`
2. Calculate price: `abs(balance_delta)`
3. Create transaction with `tx_case=buy_collect_ui_inferred`
4. Reset `pending_collect_qty` to 0 (consumed)
5. Reset partial deltas
6. Update baselines

**Example**:
```
pending_collect_qty = 5000 (from previous preorder)
Current delta: warehouse=+5000, balance=-70M
→ quantity = 5000 + 5000 = 10,000
→ price = 70M
→ Save: 10,000x @ 70M
→ pending_collect_qty = 0
```

---

### T4: Balance-Only Timeout
**Trigger**: `balance_delta < 0 AND warehouse_delta = 0 AND elapsed >= 3.0s`  
**Actions**:
1. Estimate quantity: `abs(balance_delta) / desired_price`
2. Add `pending_collect_qty` to estimate
3. Create transaction with `tx_case=buy_collect_balance_only`
4. Reset ALL deltas including `pending_collect_qty`

**Example**:
```
pending_collect_qty = 3000 (from previous preorder)
balance_delta = -42M, warehouse_delta = 0
desired_price = 14,000
Elapsed: 3.2s

→ estimated_qty = 42M / 14k = 3000
→ total_qty = 3000 + 3000 = 6000
→ Save: 6000x @ 42M (balance_only)
→ pending_collect_qty = 0
```

---

### T5: Window-Close Force-Save (FIX #2)
**Trigger**: `current_balance = None AND balance_delta < 0`  
**Actions**:
1. Check if balance_delta_timestamp exists (pending transaction)
2. Estimate quantity from desired_price
3. Add `pending_collect_qty` to estimate
4. Create transaction with `tx_case=buy_collect_balance_only_forced`
5. Full state reset (including `pending_collect_qty`)

**Example**:
```
pending_collect_qty = 5000 (from previous preorder)
balance_delta = -70M, warehouse_delta = 0
desired_price = 14,000
Elapsed: 1.5s (< 3s!)
User closes window → current_balance = None

→ estimated_qty = 70M / 14k = 5000
→ total_qty = 5000 + 5000 = 10,000
→ Save: 10,000x @ 70M (balance_only_forced)
→ Full reset, pending_collect_qty = 0
```

---

### T6: Window Close (Normal)
**Trigger**: `current_balance = None AND no pending transaction`  
**Actions**:
1. Call `_reset_detail_window_state()`
2. Clear ALL state including `pending_collect_qty`
3. Return to INACTIVE state

---

## Pending-Collect-Qty Lifecycle

### Accumulation Phase
```python
# Preorder #1
warehouse_delta = 5000, balance_delta = 0
→ pending_collect_qty = 5000

# Preorder #2 (without purchase)
warehouse_delta = 3000, balance_delta = 0
→ pending_collect_qty = 8000
```

### Consumption Phase (Normal Transaction)
```python
# Purchase
warehouse_delta = 5000, balance_delta = -100M
→ quantity = 5000 + 8000 = 13,000
→ Save: 13,000x @ 100M
→ pending_collect_qty = 0  # CONSUMED
```

### Consumption Phase (Balance-Only Timeout)
```python
# Purchase with warehouse not updating
warehouse_delta = 0, balance_delta = -100M
elapsed = 3.5s
→ estimated_qty = 100M / desired_price = 5000
→ quantity = 5000 + 8000 = 13,000
→ Save: 13,000x @ 100M (balance_only)
→ pending_collect_qty = 0  # CONSUMED
```

### Consumption Phase (Forced Save)
```python
# Window closed before timeout
warehouse_delta = 0, balance_delta = -100M
elapsed = 1.8s, window closed
→ estimated_qty = 100M / desired_price = 5000
→ quantity = 5000 + 8000 = 13,000
→ Save: 13,000x @ 100M (balance_only_forced)
→ pending_collect_qty = 0  # RESET
```

### Abandonment Phase
```python
# Window closed without purchase
pending_collect_qty = 8000
window closed, balance_delta = 0
→ No transaction created
→ pending_collect_qty = 0  # LOST (correct, preorder not collected)
```

---

## Edge-Cases Handling

### E1: Multiple Preorders, No Purchase
```
Preorder #1: warehouse +5000 → pending = 5000
Preorder #2: warehouse +3000 → pending = 8000
Window closes → pending = 0 (no transaction)
```
**Reason**: Preorders alone are not collect-transactions

### E2: Preorder + Immediate Window Close
```
Preorder: warehouse +5000 → pending = 5000
Purchase: balance -70M, warehouse 0 (not updated yet)
Elapsed: 1s, window closes
→ Force-save: 10,000x (5000 estimate + 5000 pending)
```
**Result**: Both preorder and purchase captured ✅

### E3: Baseline Already Includes Preorder
```
Baseline: warehouse = 10,000 (preorder from yesterday)
Delta: warehouse 0, balance 0
→ pending = 0 (no new preorder detected)

Purchase: warehouse +5000, balance -70M
→ quantity = 5000 + 0 = 5000 (correct!)
```
**Result**: Old preorder not double-counted ✅

### E4: New Preorder During Active Purchase
```
Purchase starts: balance -70M, warehouse 0
Timer starts...
New preorder placed: warehouse +5000, balance 0 (net)
→ Placed order detection extracts qty=5000
→ warehouse_delta set to 5000
→ Transaction completes: 5000x @ 70M
```
**Result**: Concurrent preorder handled via Placed-Order-Detection ✅

---

## State Invariants

### I1: pending_collect_qty Monotonic (until consumed)
```python
assert self._detail_pending_collect_qty >= 0
# Can only increase (accumulation) or reset to 0 (consumption/window-close)
```

### I2: Consumed Only When Transaction Created
```python
if transaction and transaction['quantity'] > warehouse_delta:
    assert self._detail_pending_collect_qty was used
    assert self._detail_pending_collect_qty == 0 after transaction
```

### I3: Reset on Window-Close
```python
if current_balance is None:
    assert self._detail_window_active == False after reset
    assert self._detail_pending_collect_qty == 0 after reset
```

### I4: Partial Deltas Reset After Transaction
```python
if transaction:
    assert self._detail_partial_balance_delta == 0 after transaction
    assert self._detail_partial_warehouse_delta == 0 after transaction
    # BUT pending_collect_qty only reset if consumed
```

---

## Debug-Logs per State

### INACTIVE → BASELINE
```
[DETAIL] Entered buy_item window
   Item: Pig Blood
   Balance baseline: 178,904,126,325
   Warehouse baseline: 10,000
```

### BASELINE → ACCUMULATION (Warehouse-Only)
```
🔵 Preorder-Collect detected: warehouse +5000, balance unchanged
🔵 Storing as pending_collect_qty (will combine with next purchase)
```

### ACCUMULATION → TRANSACTION (Normal)
```
[DETAIL] Change detected in buy_item
   Balance: 178,904,126,325 → 178,889,989,115 (Δ -14,137,210)
   Warehouse: 10,000 → 15,000 (Δ +5,000)

🔵 Combining purchase (5000x) with pending_collect (5000x)
🔵 Total quantity: 10000x

[DETAIL] ✅ Transaction saved successfully
```

### ACCUMULATION → TRANSACTION (Balance-Only Timeout)
```
[DETAIL] ⚠️ Warehouse delta missing after 3.12s - using balance-only fallback
[DETAIL] Estimated quantity: 5000x (from balance -70,000,000 / price 14,000)

🔵 Combining balance-only (5000x) with pending_collect (5000x)

[DETAIL] ✅ Transaction saved successfully
```

### ACCUMULATION → TRANSACTION (Forced)
```
🔶 Window closed with pending balance-only transaction!
🔶 Forcing balance-only save now (balance_delta=-70,000,000)

🔶 Combining forced purchase (5000x) with pending_collect (5000x)

🔶 Forced balance-only transaction saved: 10000x @ 70,000,000
```

### TRANSACTION → BASELINE (Next Purchase)
```
[DETAIL] Change detected in buy_item
   Balance: 178,889,989,115 → 178,876,189,115 (Δ -13,800,000)
   Warehouse: 15,000 → 20,000 (Δ +5,000)

[DETAIL] ✅ Transaction saved successfully
```

### ANY → INACTIVE (Window Close)
```
[DETAIL] Window closed - resetting state
```

---

**Ende des State-Machine Dokuments**
