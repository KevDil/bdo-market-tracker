# OCR Spaces in Price Fix - 2025-10-12

## Problem

**Symptom:** Transaction "200x Magical Shard für 585,585,000 Silver" um 04:04 wurde nicht gespeichert.

**Root Cause:** OCR erkannte den Preis mit Leerzeichen nach Kommas:
```
Transaction of Magical Shard x2OO worth 585, 585, OO0 Silver has been complet__.
                                            ^^    ^^    ^^
                                         Spaces after commas!
```

Die Regex-Pattern `[0-9OolI\|,\.]{3,}` matched **keine Leerzeichen**, daher wurde nur `585,` gematcht und dann gestoppt → `price=None`.

Die strikte Preis-Validierung in `tracker.py` (line 1262) verwarf dann die Transaktion:
```python
if price is None or price <= 0:
    log_debug(f"drop candidate: invalid/missing price ({price})")
    continue
```

## Solution

### 1. Regex-Pattern erweitert (parsing.py)

**Lines 400-406:** Added `\s` to numeric patterns to allow spaces within numbers:

```python
# OLD:
m_worth = re.search(fr'worth\s+([0-9OolI\|,\.]{{3,}}){silver_sep}{silver_pat}', entry_text, re.IGNORECASE)
m_for_ctx = re.search(fr'\bfor\s+([0-9OolI\|,\.]{{3,}}){silver_sep}{silver_pat}', segment, re.IGNORECASE)

# NEW:
m_worth = re.search(fr'worth\s+([0-9OolI\|,\.\s]{{3,}}?){silver_sep}{silver_pat}', entry_text, re.IGNORECASE)
m_for_ctx = re.search(fr'\bfor\s+([0-9OolI\|,\.\s]{{3,}}?){silver_sep}{silver_pat}', segment, re.IGNORECASE)
```

**Changes:**
- Added `\s` to character class: `[0-9OolI\|,\.\s]`
- Made quantifier non-greedy: `{3,}?` (stops at 'Silver' keyword)

**Impact:** Pattern now matches `585, 585, OO0` completely instead of just `585,`

### 2. Normalization improved (utils.py)

**Lines 381-395:** Remove spaces **BEFORE** confusable mapping:

```python
def normalize_numeric_str(s):
    """Ersetze häufige OCR-Fehler und parse int."""
    if not s:
        return None
    # CRITICAL FIX: Remove whitespace FIRST
    s = s.replace(' ', '')  # <-- NEW LINE
    # map confusables
    mapped = "".join(LETTER_TO_DIGIT.get(ch, ch) for ch in s)
    cleaned = re.sub(r'[^0-9,\.]', '', mapped)
    if cleaned == "":
        return None
    cleaned = cleaned.replace(',', '').replace('.', '')
    try:
        return int(cleaned)
    except:
        return None
```

**Why:** Previously, `re.sub(r'[^0-9,\.]', '', mapped)` removed spaces, but this happened AFTER pattern matching. If pattern only captured `585,`, normalization couldn't fix it.

**Impact:** Now handles:
- `585, 585, OO0` → `585,585,000` → 585585000 ✅
- `1 225 000 000` → `1,225,000,000` → 1225000000 ✅

## Test Results

**File:** `scripts/test_spaces_in_price.py`

**Test 1 - Normalization (5 cases):**
- `585,585,000` → 585,585,000 ✅
- `585, 585, 000` → 585,585,000 ✅
- `585, 585, OO0` → 585,585,000 ✅ (Spaces + O→0 conversion)
- `1 225 000 000` → 1,225,000,000 ✅ (Spaces as thousands separators)
- `765,000,000` → 765,000,000 ✅ (Normal format)

**Test 2 - Full Parsing (4 cases):**
- OCR error: `Transaction of Magical Shard x2OO worth 585, 585, OO0 Silver` → qty=200, price=585585000 ✅
- Normal format: `Transaction of Magical Shard x200 worth 585,585,000 Silver` → qty=200, price=585585000 ✅
- Listed with spaces: `Listed Magical Shard x2OO for 662, 000, 000 Silver` → qty=200, price=662000000 ✅
- Trace of Nature: `Transaction of Trace of Nature X5,O00 worth 765,000,000 Silver` → qty=5000, price=765000000 ✅

**Result:** 9/9 passed ✅

## Files Modified

1. **parsing.py** (lines 400-406, 530-536)
   - Extended regex patterns with `\s` for numeric strings
   - 3 pattern changes: m_worth, m_worth_missing, m_for_ctx, m_silver

2. **utils.py** (lines 381-395)
   - Added `s = s.replace(' ', '')` as first operation in normalize_numeric_str()

3. **instructions.md**
   - Added to recent_changes with full context

4. **scripts/test_spaces_in_price.py** (NEW)
   - Comprehensive test suite for normalization + parsing

## Why This Happened

OCR sometimes inserts spaces after commas in large numbers, especially when:
- Numbers have many digits (6+ digits)
- Multiple comma separators (e.g., 585,585,000)
- Font/rendering makes commas less distinct

This is a **known OCR edge case** with comma-heavy numbers. The fix makes the parser more robust against this type of OCR error.

## Impact

- ✅ Fixes missing transactions due to space-corrupted prices
- ✅ Backward compatible (normal formats still work)
- ✅ No performance impact (space removal is O(n) operation)
- ⚠️ Future consideration: Monitor if this causes false positives (unlikely due to strict 'Silver' keyword requirement)

## Related Issues

- Previous fix (2025-10-12): Missing leading digits (e.g., "126,184" instead of "585,585,000")
- This fix: Spaces within digits (e.g., "585, 585, OO0")
- Both issues solved by enhanced parsing + plausibility checks

## Verification

To verify the fix works:

1. Run test suite: `python scripts/test_spaces_in_price.py`
2. Check auto-tracking with similar transactions
3. Inspect `ocr_log.txt` for `structured: ... price=<valid number>` (not `price=None`)
4. Verify database contains correct price (not skipped due to price=None)
