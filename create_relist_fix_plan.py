"""
MAGICAL SHARD RELIST BUG - FIX PLAN
====================================

PROBLEM ANALYSE:
===============

TEST SCENARIO:
- Warehouse: 172x Magical Shard
- Old listing: 200x @ 654,000,000 (fully filled)
- Action: Click "Relist" → New: 172x @ 569,320,000
- Sell-Detail-Window CLOSES IMMEDIATELY after submit!

WHAT HAPPENED:
✅ Transaction saved: 200x @ 580,261,500 (net) - case: sell_relist_partial
✅ Old listing marked collected
❌ NEW listing (172x @ 569,320,000) NOT created!

LOG EVIDENCE:
-------------
22:35:20.201: BASELINE CAPTURED - Warehouse: 172 ✅
22:35:21.965: Scan #2 - Warehouse: None (window closing, metrics extraction failed)
22:35:23.399: Overview-Log parsed:
  - structured: 2025-10-21 22:35:00 listed item='Magical Shard' qty=172 price=569320000 ✅
  - structured: 2025-10-21 22:35:00 transaction item='Magical Shard' qty=200 price=580261500 ✅
22:35:23.416: [CLUSTER] Skip 'listed'-only for 'Magical Shard' on sell_overview (no transaction) ❌
22:35:23.433: DB SAVE: Transaction only (no listing)

ROOT CAUSES:
===========

1. SELL-DETAIL AUTO-CLOSE:
   - Sell-Detail-Window schließt SOFORT nach Relist-Submit
   - Keine Zeit für Delta-Detection (Warehouse: 172 → 0)
   - Detail-Window Relist-Detection UNMÖGLICH für Sell-Side!
   
2. OVERVIEW-LOG LISTED-SKIP BUG:
   - Code in tracker.py L5257:
     ```python
     if wtype == 'sell_overview' and not transaction_entry and listed_entry:
         # Skip listed-only UNLESS UI metrics show salesCompleted > 0
     ```
   - Cluster enthält BEIDE (listed + transaction)
   - Aber Code skippt das listed-Entry weil es "keine eigene" Transaction hat
   - Logic-Fehler: Prüft `transaction_entry` im Cluster, aber skippt einzelne Entries!

3. RELIST-PATTERN NOT RECOGNIZED:
   - Cluster hat: {'transaction', 'listed'} am SELBEN Timestamp
   - Das ist RELIST-Pattern! (old collected + new listed)
   - Code erkennt das nicht als Relist-Event
   - Speichert nur Transaction, nicht das neue Listing

FIX STRATEGY:
============

FIX 1: RELIST-PATTERN DETECTION in Overview-Log
------------------------------------------------
Problem: Cluster mit {transaction, listed} am selben Timestamp wird nicht als Relist erkannt

Solution:
```python
# In process_ocr_text(), nach cluster-building:

# Detect relist pattern: transaction + listed at same timestamp
if transaction_entry and listed_entry and transaction_entry['ts'] == listed_entry['ts']:
    # RELIST detected!
    # 1. Save transaction (already done)
    # 2. Mark old listing/preorder collected (use transaction to find it)
    # 3. Save NEW listing/preorder from listed_entry
    
    if side == 'sell':
        # Find old listing by transaction
        old_listing = find_matching_listing(item, transaction_qty, transaction_price)
        if old_listing:
            mark_listing_collected(old_listing.id, transaction_ts)
        
        # Save NEW listing
        new_listing_qty = listed_entry['qty']
        new_listing_price = listed_entry['price']
        store_listing(item, new_listing_qty, new_listing_price, timestamp=listed_ts)
    
    elif side == 'buy':
        # Same logic for preorders
        old_preorder = find_matching_preorder(item, transaction_qty, transaction_price)
        if old_preorder:
            mark_preorder_collected(old_preorder.id, transaction_ts)
        
        new_preorder_qty = listed_entry['qty']  # Actually 'placed' entry
        new_preorder_price = listed_entry['price']
        store_preorder(item, new_preorder_qty, new_preorder_price, timestamp=placed_ts)
```

FIX 2: REMOVE LISTED-SKIP for RELIST-CLUSTERS
----------------------------------------------
Problem: listed-Entry wird geskipped wenn es in Relist-Cluster ist

Solution:
```python
# In L5257, ADD exception for relist-clusters:

if wtype == 'sell_overview' and not transaction_entry and listed_entry and ent['type'] == 'listed':
    # Check if this is part of a RELIST cluster (transaction + listed same timestamp)
    is_relist_cluster = any(
        r['type'] == 'transaction' and r['ts'] == ent['ts']
        for r in related
    )
    
    if is_relist_cluster:
        # DON'T skip! This is the NEW listing in a relist event
        pass
    else:
        # Original skip logic
        has_sell_ui_evidence = False
        # ... existing code ...
        if not has_sell_ui_evidence:
            log_debug(f"[CLUSTER] Skip 'listed'-only for '{ent.get('item')}' (no transaction)")
            continue
```

FIX 3: DETAIL-WINDOW RELIST FOR SELL-SIDE (FUTURE)
---------------------------------------------------
Problem: Sell-Detail schließt zu schnell für Delta-Detection

NOT FIXABLE - Window behavior is game-controlled!
Must rely on Overview-Log fallback ✅

IMPLEMENTATION PRIORITY:
=======================

1. HIGH: Fix #1 - Relist-Pattern Detection in Overview-Log
   - Erkennt {transaction, listed} als Relist
   - Speichert beide Komponenten korrekt
   - Works for BOTH sell and buy side

2. MEDIUM: Fix #2 - Remove Listed-Skip for Relist
   - Prevents skipping NEW listing in relist cluster
   - Safety net for edge cases

3. LOW: Fix #3 - Detail-Window (NOT FIXABLE)
   - Sell-Detail closes too fast (game behavior)
   - Must accept Overview-Log as primary source for sell-side relists

TESTING PLAN:
============

After implementing fixes, test:
1. Magical Shard sell relist (172x new, 200x old)
2. Unknown Seed buy relist (10x new, 2x filled)
3. Large quantity relist (4486x new, fully filled)
4. Partial collect relist (132x filled of 200x total)

Expected results:
✅ Transaction saved
✅ Old listing/preorder marked collected
✅ NEW listing/preorder created
✅ All 3 components stored correctly
"""

with open("MAGICAL_SHARD_RELIST_FIX_PLAN.md", "w", encoding="utf-8") as f:
    f.write(__doc__)

print("Fix plan saved to MAGICAL_SHARD_RELIST_FIX_PLAN.md")
print("\nKEY FINDINGS:")
print("=" * 80)
print("1. Sell-Detail-Window AUTO-CLOSES immediately after relist submit")
print("   → NO time for Delta-Detection (Warehouse change)")
print("   → Detail-Window Relist-Detection IMPOSSIBLE for Sell-Side!")
print()
print("2. Overview-Log DOES capture both:")
print("   ✅ Transaction: 200x @ 580,261,500")
print("   ✅ Listed: 172x @ 569,320,000")
print()
print("3. BUT: Listed-Entry was SKIPPED due to logic bug:")
print("   ❌ Code skips 'listed-only' entries on sell_overview")
print("   ❌ Doesn't recognize {transaction + listed} as RELIST pattern")
print()
print("SOLUTION:")
print("=" * 80)
print("✅ FIX 1: Detect {transaction, listed} at same timestamp = RELIST")
print("✅ FIX 2: Don't skip listed-entries in relist-clusters")
print("✅ FIX 3: Accept that Detail-Window won't work for sell-side relists")
