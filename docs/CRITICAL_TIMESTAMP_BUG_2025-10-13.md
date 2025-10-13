# CRITICAL BUG: False Timestamp Assignment

## Problem Description

**Symptom:** Transactions are stored with WRONG timestamps that don't exist in the OCR log.

**Example:**
- OCR reads: "2025.10.13 23:25 Transaction of Magical Shard x55..."
- Parser extracts: `23:25:00` ✓ CORRECT
- BUT Database stores: `23:26:00` ❌ WRONG!

**Why This Is Critical:**
- The same transaction can be bought/sold multiple times within seconds with identical values
- Example: Buying 5000x Material in multiple batches within 1 minute
- Time-based deduplication (e.g., "skip if within 5 minutes") **BLOCKS LEGITIMATE TRANSACTIONS**!

## Root Cause

The tracker has multiple "timestamp adjustment" logics that modify parsed timestamps:

1. **First Snapshot Timestamp Drift** (Lines 944-1040)
   - Adjusts timestamps when multiple entries of same type have different times
   - Purpose: Handle OCR header/layout ordering issues

2. **Fresh Transaction Detection** (Lines 1042-1153)
   - Adjusts OLD log timestamps to CURRENT time for "fast collect" scenarios
   - Purpose: When transaction shows "21:55" but collect happened at "22:06"

3. **Dialog Return Adjustment** (Lines 888-923, 2456-2480)
   - Adjusts timestamps after returning from item detail dialog
   - Purpose: Align timestamps to latest snapshot time

**The Problem:** These adjustments are TOO AGGRESSIVE and modify timestamps even for transactions that should NOT be adjusted!

## The Magical Shard Case

**Scan 1 (23:26:03):**
- Maple Sap appears with timestamp 23:26 (NEW transaction, collect button)
- Magical Shard visible with timestamp 23:25 (OLD transaction, already processed)
- `overall_max_ts = 23:26` (from Maple Sap)

**What Should Happen:**
- Magical Shard: Keep 23:25, skip as already in DB
- Maple Sap: Save with 23:26

**What Actually Happens:**
- Some adjustment logic changes Magical Shard timestamp to 23:26
- Magical Shard saved AGAIN with wrong timestamp
- Result: Duplicate with different timestamp!

## The ONLY Correct Solution

**NEVER** use time-based deduplication windows (e.g., "skip if within 5 minutes")!

Instead:
1. **Fix timestamp assignment** - Only adjust timestamps when absolutely necessary and correct
2. **Use Content-Hash** - Position-aware hash that includes OCR raw text
3. **Trust the Parser** - If parser says 23:25, keep 23:25 unless there's PROOF it should be different

## Key Business Rule

⚠️ **CRITICAL RULE:**  
**Users regularly buy/sell the same item with same quantity at same price within seconds/minutes!**

Examples:
- Buying 5x batches of 5000x Material within 1 minute
- Selling collected items in multiple 1000x stacks within seconds
- Rapid market flipping with identical values

**ANY time-based dedup window will break these legitimate use cases!**

## Action Items

1. ✅ Remove value-based 5-minute dedup (already done)
2. ⚠️ Review and FIX all timestamp adjustment logics
3. ⚠️ Add safeguards: Never adjust if transaction already in DB
4. ⚠️ Add logging: Log every timestamp adjustment with reason
5. ✅ Use Content-Hash as primary dedup method
6. ⚠️ Add rules to project instructions about this critical requirement

##  Related Files

- `tracker.py` - Lines 888-1153, 2456-2480 (timestamp adjustments)
- `parsing.py` - Timestamp extraction (CORRECT, don't change!)
- `database.py` - Dedup checks
