# Pure Powder Reagent Relist Bug - Detailed Analysis
**Test Date:** 2025-10-21 21:08  
**Status:** ❌ FAILED - No preorder created, no transaction saved, old preorder not collected

---

## Test Scenario

### Initial State
- Warehouse: **5514** Pure Powder Reagent
- Existing Preorder: **4486x @ 58,766,600** (fully filled)

### User Action (21:08)
1. Click "Relist" → Detail-Window opens
2. Set new preorder: **5000x @ 65,000,000**
3. Auto-Collect triggers: **4486x @ 58,766,600**
4. Instant Buy: **364x @ 4,732,000** (current market price)
5. New Preorder created: **4636x @ 60,268,000** (5000 - 364)
6. Detail-Window closed (~3 seconds total)

### Expected DB State
```sql
✅ OLD Preorder (ID=13): 4486x @ 58,766,600, status='collected'
✅ NEW Preorder: 4636x @ 60,268,000, status='active'
✅ Transaction #1: 4486x @ 58,766,600, type='buy', case='buy_collect' (auto-collect)
✅ Transaction #2: 364x @ 4,732,000, type='buy', case='buy_collect' (instant buy)
```

### Actual DB State
```sql
❌ OLD Preorder (ID=13): 4486x @ 58,766,600, status='active' (NOT collected!)
❌ NEW Preorder: NONE
❌ Auto-Collect Transaction: NONE
❌ Instant Buy Transaction: NONE
```

---

## Root Cause Analysis

### Timeline from Logs

**21:08:39.781 - Baseline Captured** ✅
```
Balance: 215,072,270,420
Warehouse: 5514
Input Fields: 5,000x @ 13,000 (total: 65,000,000)
```

**21:08:41.070 - OCR Failure** ❌
```
[DETAIL-EXTRACT] No balance found in metrics, returning None
[DETAIL] ⚠️ Metrics extraction failed → Using last known state
Balance=215,072,270,420, Warehouse=5514 (UNCHANGED!)
```

**Result:**
- `current_metrics == baseline_metrics`
- `balance_delta = 0`, `warehouse_delta = 0`
- **Relist-Detection NOT triggered!**

**21:08:42.191 - Window Exit** ⏰
```
[WINDOW] Transition: buy_item → buy_overview
```

### Why Detection Failed

1. **OCR Timing Issue:**
   - Baseline captured at t=0 (window open)
   - Second scan at t=1.9s **failed to extract balance**
   - User confirmed relist at ~t=1.5s (between scans!)
   - Window closed at t=3s before third scan

2. **Fallback Behavior:**
   - When OCR fails, code uses `last_known_state`
   - `last_known_state` == `baseline` → **Delta = 0**
   - Relist-Detection requires `balance_delta < 0` → **NOT triggered**

3. **Transaction-Log Evidence:**
   ```
   21:08 Transaction of Pure Powder Reagent x4,486 worth 58,766,600 Silver ✓
   21:08 Purchased Pure Powder Reagent x364 for 4,732,000 Silver ✓
   21:08 Placed order of Pure Powder Reagent x4,636 for 60,268,000 Silver ✓
   ```
   **All events logged in Overview - but Detail-Window already closed!**

---

## Fix Plan

### Strategy: Dual-Path Detection

**Path 1: Detail-Window Delta (Primary)** ✅ Already implemented
- Detects balance/warehouse changes in real-time
- **Problem:** Fails if OCR misses the changed state

**Path 2: Window-Exit Fallback (NEW)** ⚠️ Required!
- When Detail-Window exits, parse Overview Transaction-Log
- Match "Transaction of [item]" with active preorders
- Reconstruct missing transactions from log entries

---

## Implementation Plan

### Phase 1: Window-Exit Transaction-Log Parser

**Location:** `_on_detail_window_exit()` (L4460-4620)

**Logic:**
```python
def _on_detail_window_exit(self, now, wtype):
    # Existing logic...
    
    # NEW: Parse Transaction-Log for missing relist events
    if self._detail_window_entry_item and wtype == 'buy_overview':
        item = self._detail_window_entry_item
        
        # Extract from current overview text
        log_entries = self._parse_transaction_log_for_item(item, full_text)
        
        # Look for pattern: "Transaction of [item] x[qty] worth [price] Silver"
        for entry in log_entries:
            if entry['type'] == 'transaction':
                # This is auto-collect from old preorder!
                self._handle_autocollect_from_log(entry, now)
            
            elif entry['type'] == 'placed':
                # New preorder created
                self._handle_new_preorder_from_log(entry, now)
            
            elif entry['type'] == 'purchased':
                # Instant buy
                self._handle_instant_buy_from_log(entry, now)
```

### Phase 2: Increase Burst-Scan Duration

**Current:** 6 fast scans (~0.48s coverage)  
**Problem:** Not enough time to catch state change  
**Solution:** Increase to **15 fast scans (~1.2s coverage)**

**Location:** `_monitor_detail_window()` L3500

```python
# BEFORE:
self._request_immediate_rescan = 3  # 3 rapid scans

# AFTER:
self._request_immediate_rescan = 8  # 8 rapid scans (~640ms)
```

### Phase 3: Improve OCR Reliability

**Option 1:** Extract Balance/Warehouse from **TWO different ROIs**
- Current: One ROI covers both metrics
- Improved: Separate ROIs for balance and warehouse
- Reduces chance of complete OCR failure

**Option 2:** Add OCR Retry Logic
```python
if not balance_found:
    # Retry OCR with different canvas_size
    retry_result = self._extract_metrics_retry(roi_image)
    if retry_result:
        balance = retry_result['balance']
```

---

## Testing Plan

### Test Case 1: Fast Relist (Pure Powder Reagent scenario)
```
1. Open Detail-Window
2. Immediately set new preorder (within 2s)
3. Confirm and close
4. Verify: Auto-collect saved, new preorder created, old preorder collected
```

### Test Case 2: Slow Relist (Original Caphras scenario)
```
1. Open Detail-Window
2. Wait 5s (allow multiple OCR scans)
3. Set new preorder
4. Wait 3s
5. Confirm and close
6. Verify: Same as Test Case 1
```

### Test Case 3: Partial Relist (Trace of Nature scenario)
```
1. Preorder: 5000x (2137x filled)
2. Relist → Auto-collect: 2137x
3. New preorder: 5000x
4. Verify: Partial quantities handled correctly
```

---

## Priority

**CRITICAL:** Phase 1 (Window-Exit Fallback)  
**HIGH:** Phase 2 (Burst Duration)  
**MEDIUM:** Phase 3 (OCR Reliability)

---

## Next Steps

1. Implement `_parse_transaction_log_for_item()` helper
2. Add `_handle_autocollect_from_log()` handler
3. Add `_handle_new_preorder_from_log()` handler
4. Increase burst scan count
5. Test with Pure Powder Reagent scenario
6. Test with Caphras Tree Sap scenario
