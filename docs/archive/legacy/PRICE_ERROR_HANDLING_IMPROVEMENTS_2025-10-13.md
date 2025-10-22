# Price Error Handling - Improvements (2025-10-13)

## Problem Analysis

Based on test results from 2025-10-13 20:22-20:29, two main issues were identified:

### Issue 1: Missing Recent Transaction
**Problem:** "Magical Shard" sale at 20:29 was not captured.

**Root Cause:** The transaction occurred after Auto-Tracking mode was stopped, so the Market UI hadn't yet displayed it in the visible log window when the last OCR scan happened.

**Solution:** 
- Wait 5-10 seconds after a test transaction before stopping Auto-Track mode
- This gives the game's Market UI time to update and display the transaction
- OCR scanning frequency: Every 3 seconds during auto-tracking

### Issue 2: Incorrect Price (Lost Leading Digit)
**Problem:** "Crystallized Despair" was saved with price 265M instead of 1,265M (lost leading digit "1").

**Root Cause:**
1. OCR failed to recognize the leading digit "1" in "1,265,000,000"
2. Price plausibility check detected the error (265M < 10% of expected 1,265M)
3. UI-based fallback correction was triggered BUT failed to apply correctly
4. Invalid price was still saved despite detection

## Implemented Improvements

### 1. Enhanced Price Truncation Detection (tracker.py)

Added detection for **both** buy AND sell sides:

```python
# BUY-SEITE: Erkennung abgeschnittener Preise
if wtype == 'buy_overview' and final_type == 'buy':
    if item_lc_check in ui_buy:
        expected_unit = remainingPrice / (orders - ordersCompleted)
        parsed_unit = price / quantity
        
        # Wenn parsed_unit 10x kleiner als expected_unit → Abgeschnitten!
        if expected_unit > parsed_unit * 10:
            needs_fallback = True

# SELL-SEITE: Erkennung abgeschnittener Preise (NEU!)
if wtype == 'sell_overview' and final_type == 'sell':
    if item_lc_check in ui_sell:
        expected_unit_after_tax = price * 0.88725
        parsed_unit = price / quantity
        
        # Wenn parsed_unit 10x kleiner als expected_unit → Abgeschnitten!
        if expected_unit_after_tax > parsed_unit * 10:
            needs_fallback = True
```

**Before:** Only detected truncated prices on buy_overview
**After:** Detects truncated prices on both buy_overview AND sell_overview

### 2. Improved UI Fallback Logic (tracker.py)

Enhanced fallback to properly handle all cases and **discard entry if fallback fails**:

```python
if needs_fallback and (not first_snapshot_mode):
    item_lc = (ent.get('item') or '').lower()
    price_success = False
    
    # BUY-Seite: UI-basierte Preisberechnung
    if wtype == 'buy_overview' and final_type == 'buy' and item_lc in ui_buy:
        # ... calculate price from UI metrics ...
        if price_calc > 0:
            price = int(round(price_calc))
            price_success = True
    
    # SELL-Seite: UI-basierte Preisberechnung
    elif wtype == 'sell_overview' and final_type == 'sell' and item_lc in ui_sell:
        # ... calculate price from UI metrics ...
        if price_calc > 0:
            price = int(round(price_calc))
            price_success = True
    
    # KRITISCH: Wenn UI-Fallback fehlschlägt, Eintrag verwerfen!
    if not price_success and needs_fallback:
        log_debug(f"[PRICE-ERROR] UI fallback failed for '{item_name}' - discarding entry")
        continue  # Skip this entry instead of saving bad data
```

**Before:** If UI fallback failed, bad price was still saved
**After:** If UI fallback fails, entry is discarded (preventing bad data)

### 3. Stricter Price Validation (parsing.py)

Improved plausibility checking with clearer thresholds:

```python
if reason == 'too_low' and expected_min and price < expected_min * 0.1:
    # Price < 10% of expected → definitely OCR error (e.g., "265M" vs "1265M")
    price = None  # Trigger UI fallback

elif reason == 'too_low' and expected_min and price < expected_min * 0.5:
    # Price 10-50% of expected → possible OCR error
    pass  # Keep for now, let tracker.py validate with UI
```

**Thresholds:**
- `< 10%` of expected: **Strict** - Definitely invalid, force UI fallback
- `10-50%` of expected: **Moderate** - Possibly invalid, allow tracker.py to validate
- `> 50%` of expected: **Accept** - Within tolerance

### 4. Better Error Logging

All price corrections now include detailed debug messages:

```
[PRICE-IMPLAUSIBLE] 'Crystallized Despair' 50x @ 265,000,000: too_low (expected: 1,000,000,000 - 1,500,000,000) - attempting UI fallback
[PRICE] UI fallback (buy, case=collect): qty=50 * (63250000000/50) = 63250000000.0 → 63250000000
```

## Manual Database Fix

For the test case "Crystallized Despair", the price was manually corrected:

```python
# Created fix_price.py script:
UPDATE transactions 
SET price = 1265000000 
WHERE item_name = "Crystallized Despair" 
AND price = 265000000
```

Result: `Korrigiert: 1 Zeile(n)`

## Testing Recommendations

### Before Testing:
1. Ensure Market UI is fully loaded and visible
2. Clear any old log entries that might confuse parsing

### During Testing:
1. Perform test transaction (buy/sell)
2. **Wait 5-10 seconds** for Market UI to update
3. Verify transaction appears in visible log
4. Then stop Auto-Track mode

### After Testing:
1. Check `latest_ocr.txt` for OCR'd text
2. Verify transaction was parsed correctly
3. Check database for price accuracy
4. Review debug logs for any `[PRICE-ERROR]` or `[PRICE-IMPLAUSIBLE]` messages

## Expected Behavior (After Fix)

### Scenario 1: Valid OCR Price
- Price is parsed correctly
- Passes plausibility check
- Saved to database as-is
- ✅ No UI fallback needed

### Scenario 2: Invalid OCR Price (Lost Leading Digits)
- Price is parsed with missing digits (e.g., "265M" instead of "1265M")
- Fails plausibility check (`< 10%` of expected)
- `needs_fallback = True` is set
- UI metrics are used to reconstruct correct price
- ✅ Corrected price saved to database

### Scenario 3: UI Fallback Fails (No UI Data)
- Price is invalid AND UI metrics unavailable
- `price_success = False`
- Entry is **discarded** (not saved)
- ✅ No bad data in database

### Scenario 4: Truncated Price (Long Item Names)
- Long item name causes price text to be cut off in UI
- OCR captures partial price
- Detection: `parsed_unit << expected_unit` (>10x difference)
- UI fallback reconstructs full price
- ✅ Corrected price saved to database

## Files Modified

1. **tracker.py** (lines 1613-1714)
   - Added sell-side truncation detection
   - Improved UI fallback logic
   - Added entry discard on failed fallback

2. **parsing.py** (lines 644-674)
   - Enhanced plausibility checking
   - Added clearer threshold documentation
   - Better error pattern comments

3. **fix_price.py** (new file)
   - Manual database correction script
   - For fixing test data with wrong prices

## Next Steps

1. ✅ Manual fix applied to test data
2. ⏳ Run new test with multiple items (including "Lion Blood")
3. ⏳ Verify all prices are correct in database
4. ⏳ Monitor for any `[PRICE-ERROR]` messages in logs
5. ⏳ If successful, consider this issue resolved

## Related Documentation

- `docs/OCR_PRICE_ERROR_FIX_2025-10-12.md` - Initial OCR price error handling
- `docs/IMPROVEMENT_PLAN_2025-10-13.md` - Overall improvement plan
- `WARP.md` - Current session conversation history
