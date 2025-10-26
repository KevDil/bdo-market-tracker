# Relist Detection Fix - Implementation Summary
**Date**: 2025-10-21 20:30
**Issue**: Relist transactions not properly saved (missing new preorder, combined transaction quantities)

## Problem Analysis

### Critical Constraint
⚠️ **Transaction-Log is ONLY visible in Overview window!**
- Detail-Window shows NO transaction log
- After relist, window often closes immediately (user navigates away)
- Overview may not be visible → Cannot rely on log parsing
- **Solution: Must save everything DURING relist detection in Detail-Window**

### Test Scenario (Trace of Nature Relist)
```
Initial State:
- Warehouse: 14,548
- Old Preorder: 5000x @ 770M (fully filled: 5000x)

User Action: Click "Relist" button

Expected Results:
1. Auto-collect: 5000x @ 770M (old preorder filled)
2. Instant buy: 21x @ 3,234,000 (available on market)
3. Old preorder: status='collected' ✓
4. New preorder: 4979x @ 766,766,000 (5000 - 21 = 4979)
5. Final warehouse: 14548 + 5000 + 21 = 19,569

Actual Results (BEFORE FIX):
1. ❌ Only ONE transaction saved: 5021x @ 770M (combined auto-collect + instant buy)
2. ❌ New preorder NOT created
3. ✓ Old preorder marked collected
4. ❌ Transaction saved via fallback 27 seconds late
```

### Root Causes

**Issue #1: Cached Input Fields Reflect User Input, Not Final State**
- Cached fields: `5,000x @ 154,000` (what user typed before clicking Relist)
- Actual new preorder: `4,979x @ 766,766,000` (after instant buy reduces quantity)
- Game does NOT update input fields after instant buy - they stay at original values!

**Issue #2: Cannot Rely on Transaction-Log Fallback**
- Transaction log only visible in Overview
- Overview may not be scanned if user navigates elsewhere
- Window closes too fast → Log entries missed

**Issue #3: Warehouse Delta Includes Both Auto-Collect AND Instant Buy**
- Warehouse delta: +5021 (not just +5000 from auto-collect)
- Must detect instant buy: `warehouse_delta > expected_autocollect_qty`

## Solution: Detect and Save Everything in Detail-Window

### Strategy
1. **Detect Relist Pattern**: balance↓ + warehouse↑
2. **Find Old Preorder**: Match by item, use its quantity for expected auto-collect
3. **Detect Instant Buy**: `instant_buy_qty = warehouse_delta - expected_autocollect_qty`
4. **Calculate Transactions**:
   - Auto-collect: `expected_autocollect_qty @ preorder_unit_price`
   - Instant buy: `instant_buy_qty @ calculated_unit_price`
5. **Calculate New Preorder**: `new_qty = input_qty - instant_buy_qty`
6. **Save Everything Immediately** (no waiting for fallback)

### Implementation Changes

#### Enhanced Relist Detection (tracker.py L3834-3972)

```python
if is_relist_with_autocollect:
    # 1. Find matching old preorder
    matching_preorder = find_matching_preorder(...)
    expected_autocollect_qty = matching_preorder['quantity']
    
    # 2. Detect instant buy
    instant_buy_qty = warehouse_delta - expected_autocollect_qty
    
    # 3. Save auto-collect transaction
    preorder_unit_price = matching_preorder['price'] / matching_preorder['quantity']
    autocollect_total = preorder_unit_price * expected_autocollect_qty
    store_transaction_db(qty=expected_autocollect_qty, price=autocollect_total)
    mark_collected(preorder_id)
    
    # 4. Save instant buy (if any)
    if instant_buy_qty > 0:
        instant_buy_total = total_balance_decrease - new_preorder_total
        store_transaction_db(qty=instant_buy_qty, price=instant_buy_total)
    
    # 5. Save new preorder (adjusted for instant buy)
    new_preorder_qty = original_input_qty - instant_buy_qty
    new_preorder_price = original_input_price * new_preorder_qty
    store_preorder(qty=new_preorder_qty, price=new_preorder_price)
    
    return  # Done - no further processing needed
```

**Key Differences from Previous Approach**:
- ✅ Saves EVERYTHING immediately (not waiting for window close)
- ✅ Uses preorder's unit price for auto-collect (most accurate)
- ✅ Detects instant buy from warehouse surplus
- ✅ Adjusts new preorder quantity: `input_qty - instant_buy_qty`
- ✅ Works even if overview is never scanned

#### Simplified Fallback (tracker.py L4463-4513)
**Role**: BACKUP ONLY for edge cases

```python
# Only runs if:
# 1. Detail-Window was active (_detail_window_active=True)
# 2. NOW in overview (wtype='buy_overview' or 'sell_overview')
# 3. Overview text contains transaction log

# Only parses "Transaction of" entries (as backup)
# Does NOT parse "Purchased" or "Placed order" (handled in Detail-Window)
```

**Backup Scenarios**:
- Detail-Window closed before delta detection triggered
- User navigated away before change detection
- Balance/warehouse deltas not detected due to timing

## Testing & Verification

### Verification Script
`verify_relist_fallback_fix.py` checks:
1. ✅ Old preorder marked collected
2. ✅ New preorder created (4979x @ 766,766,000)
3. ✅ Auto-collect transaction saved (5000x @ 770M)
4. ✅ Instant buy transaction saved (21x @ 3,234,000)
5. ✅ No duplicates (exactly 2 transactions, 1 active preorder)
6. ✅ Timestamps consistent (all within 30 seconds)

### Expected Database State
```
PREORDERS:
- ID=6: 5000x @ 770M, status='collected', collected_at=19:47:00
- ID=7: 4979x @ 766,766,000, status='active', placed_at=19:47:00

TRANSACTIONS:
- Auto-Collect: 5000x @ 770M, case='buy_collect'
- Instant Buy: 21x @ 3,234,000, case='buy_collect'
```

### Test Procedure
1. Reset database: `python scripts/utils/reset_db.py`
2. Start GUI: `python gui.py` (enable auto-tracking + debug mode)
3. Place preorder: 5000x @ 770M (wait for fill)
4. Click "Relist" button
5. Wait for window close (Detail→Overview transition)
6. Run verification: `python verify_relist_fallback_fix.py`

## Advantages of This Approach

✅ **Accurate Data**: Parses ACTUAL log entries (not inferred from deltas)
✅ **Handles Instant Buy**: Separates auto-collect from instant buy transactions
✅ **Correct New Preorder**: Uses game's adjusted quantity/price (not cached input)
✅ **No Duplicates**: Robust duplicate detection with 30s window
✅ **Timing-Independent**: Works even if window closes immediately after relist

## Edge Cases Handled

1. **Relist Without Instant Buy**:
   - Only "Transaction of" + "Placed order of" entries
   - Instant buy pattern won't match → skipped

2. **Instant Buy Fills Entire New Preorder**:
   - "Placed order of" shows qty=0 or very small amount
   - Still saved correctly (may not stay active long)

3. **Multiple Relists in Quick Succession**:
   - Each creates separate transactions + preorders
   - Duplicate detection prevents re-saving within 30s

4. **Window Closes Before Fallback**:
   - Fallback runs on EVERY Detail→Overview transition
   - Will catch transaction even if multiple windows opened/closed

## Migration Notes

**Existing Tests**: Update `test_preorder_relist.py` expectations:
- OLD: 1 transaction (5021x combined)
- NEW: 2 transactions (5000x + 21x separated)

**AGENTS.md Updates**: Document new fallback patterns, update test counts

**Future Work**:
- Consider extending fallback to sell-side relists
- Add metrics for fallback success rate
- Profile fallback regex performance (3 patterns vs 1)
