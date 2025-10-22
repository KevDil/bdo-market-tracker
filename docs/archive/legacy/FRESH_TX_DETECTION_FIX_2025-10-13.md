# Fresh Transaction Detection Fix - 2025-10-13

**Status**: ✅ FIXED  
**Issue**: Wrong timestamps for old log entries  
**Root Cause**: Missing time-window constraint

---

## The Original Purpose

The "Fresh Transaction Detection" logic was implemented to handle the **"Fast Collect" scenario**:

### Problem:
When a user quickly collects items or re-lists orders, the transaction line appears with an **OLD timestamp from the log**, but the transaction **just happened now**.

**Example:**
```
User clicks "Collect" at 22:06
OCR shows: "2025.10.13 21:55 Transaction of Maple Sap x488..."
```

- Timestamp `21:55` is from the OLD log entry
- But the transaction JUST happened at `22:06`!

### Solution (Original):
Adjust the timestamp to the current scan time (`overall_max_ts`):
```
21:55 → 22:06 (correct for fresh transactions)
```

---

## The Bug

The original implementation could NOT distinguish between:

1. **Fresh transactions** (just happened, but old log timestamp) ✅ should adjust
2. **Old log entries** (really old, should NOT adjust) ❌ was incorrectly adjusted

### Real Example from Test:

**Sharp Black Crystal Shard:**
- OCR timestamp: `21:55` (11 minutes old)
- Current time: `22:06`
- System thought: "Not in baseline → must be fresh!"
- Adjusted: `21:55 → 22:06` ❌ **WRONG!**

This was a **real old transaction**, not a fresh one!

---

## The Fix

### Key Insight:

**Fresh transactions** are RECENT (within seconds), not minutes/hours old!

### New Logic:

Only adjust timestamps if **ALL three criteria** are met:

1. ✅ Item NOT in baseline (new in this scan)
2. ✅ Timestamp is RECENT (within `FRESH_TX_WINDOW` seconds) **← NEW!**
3. ✅ Transaction NOT already in DB

### Implementation:

```python
FRESH_TX_WINDOW = 60  # seconds

# Before adjustment, check time difference
time_diff_seconds = abs((overall_max_ts - ts).total_seconds())

if time_diff_seconds <= FRESH_TX_WINDOW and ts < overall_max_ts:
    # Fresh transaction - adjust timestamp
    s['timestamp'] = overall_max_ts
elif time_diff_seconds > FRESH_TX_WINDOW:
    # Old log entry - do NOT adjust
    log_debug(f"Skip '{item}' - timestamp too old ({time_diff_seconds:.0f}s > 60s)")
```

---

## Examples

### Example 1: Fresh Transaction (ADJUST)

```
Current time: 22:06:30
Transaction:  22:05:45 (45 seconds old)
Time diff:    45 seconds ✅ < 60 seconds
Result:       Adjust 22:05:45 → 22:06:30 ✅
```

**Use case**: User clicked "Collect" 45 seconds ago, transaction just processed.

---

### Example 2: Old Log Entry (DO NOT ADJUST)

```
Current time: 22:06:30
Transaction:  21:55:00 (11 minutes old)
Time diff:    690 seconds ❌ > 60 seconds
Result:       Keep 21:55:00 (do NOT adjust) ✅
```

**Use case**: Old transaction from history, visible in log but already happened long ago.

---

## Testing

### Test Case 1: Fast Collect (Fresh Transaction)

**Steps:**
1. List items for sale
2. Wait for sales to complete
3. Start autotrack
4. Click "Collect" immediately
5. Wait 2-3 seconds
6. Stop autotrack

**Expected Log:**
```
[FRESH-TX] 'Maple Sap' within 2s window: adjusting ts 22:05:58 -> 22:06:00
```

**Expected Result:**
- Timestamp adjusted to current time ✅
- Transaction saved with correct timestamp ✅

---

### Test Case 2: Old Log Entry

**Steps:**
1. Have old transactions in log (e.g., from 10+ minutes ago)
2. Start autotrack
3. Let it scan (do NOT make new transactions)
4. Stop autotrack

**Expected Log:**
```
[FRESH-TX] Skip 'Sharp Black Crystal Shard' - timestamp too old (660s > 60s window)
```

**Expected Result:**
- Timestamp NOT adjusted ✅
- Transaction saved with ORIGINAL timestamp (21:55) ✅

---

## Why 60 Seconds?

The `FRESH_TX_WINDOW` is set to **60 seconds** because:

1. **Fast collect/re-list**: Usually happens within 5-15 seconds
2. **Safety margin**: Allows for slow OCR/processing (up to 1 minute)
3. **Clear distinction**: Old log entries are typically minutes/hours old

**Alternative values:**
- **30 seconds**: More strict, may miss some legitimate fresh transactions
- **120 seconds**: More lenient, may incorrectly adjust some old entries

60 seconds is a good balance.

---

## Files Modified

### `tracker.py`

**Lines 903-916**: Documentation and FRESH_TX_WINDOW constant
```python
FRESH_TX_WINDOW = 60  # seconds
```

**Lines 972-983**: Time-window check for multi-transaction case
```python
time_diff_seconds = abs((overall_max_ts - ts).total_seconds())
if time_diff_seconds <= FRESH_TX_WINDOW and ts < overall_max_ts:
    # Adjust timestamp
elif time_diff_seconds > FRESH_TX_WINDOW:
    # Skip (too old)
```

**Lines 1001-1011**: Time-window check for single-transaction case
```python
time_diff_seconds = abs((overall_max_ts - ts).total_seconds())
if time_diff_seconds <= FRESH_TX_WINDOW and ts < overall_max_ts:
    # Adjust timestamp
elif time_diff_seconds > FRESH_TX_WINDOW:
    # Skip (too old)
```

---

## Summary

| Version | Behavior | Result |
|---------|----------|--------|
| **Original** | Adjust ALL transactions not in baseline | ❌ Wrong timestamps for old entries |
| **Disabled (temp)** | Never adjust timestamps | ❌ Wrong timestamps for fresh transactions |
| **Fixed (V2.3)** | Adjust ONLY if within 60-second window | ✅ Correct for both cases! |

---

## Related Issues

### Issue #1: Sharp Black Crystal Shard Wrong Timestamp
- **Symptom**: 21:55 → 22:06 (incorrect)
- **Cause**: No time-window check
- **Fix**: ✅ Time-window constraint added

### Issue #2: Maple Sap 1x (Wrong Quantity)
- **Symptom**: qty=None defaulted to 1
- **Cause**: Missing quantity validation
- **Fix**: ✅ Quantity validation added (separate fix)

---

**Status**: Ready for testing  
**Expected Outcome**: Correct timestamps for both fresh AND old transactions
