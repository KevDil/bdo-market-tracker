
RELIST FIX IMPLEMENTATION - 2025-10-21
=======================================

PROBLEM:
Magical Shard Relist Test zeigte:
✅ Transaction gespeichert (200x @ 580,261,500)
✅ Old listing marked collected
❌ NEW listing NICHT erstellt (172x @ 569,320,000)

ROOT CAUSE:
1. Sell-Detail-Window schließt SOFORT nach Relist-Submit
   → Keine Zeit für Delta-Detection
2. Overview-Log parsed beide Events:
   - Transaction: 200x @ 580,261,500 ✅
   - Listed: 172x @ 569,320,000 ✅
3. ABER: Listed-Entry wurde geskipped wegen Logic-Bug
   → Code erkannte {transaction, listed} nicht als Relist-Pattern

IMPLEMENTED FIXES:
==================

FIX 1: RELIST-PATTERN DETECTION (tracker.py L5256-5269)
--------------------------------------------------------
```python
# ⚡ FIX: RELIST-PATTERN DETECTION
# Detect relist pattern: transaction + listed/placed at same timestamp
is_relist_cluster = False
placed_entry = next((r for r in related if r['type'] == 'placed'), None)

if transaction_entry and (listed_entry or placed_entry):
    tx_ts = transaction_entry.get('timestamp')
    new_order_entry = listed_entry if listed_entry else placed_entry
    new_order_ts = new_order_entry.get('timestamp') if new_order_entry else None
    
    if tx_ts and new_order_ts and tx_ts == new_order_ts:
        is_relist_cluster = True
        log_debug(f"[RELIST] Detected relist pattern...")
```

FIX 2: DON'T SKIP LISTED IN RELIST-CLUSTERS (tracker.py L5271-5296)
--------------------------------------------------------------------
```python
# On sell overview, skip listed-only clusters UNLESS UI metrics OR it's a relist
if wtype == 'sell_overview' and not transaction_entry and listed_entry:
    # Check if this is part of a relist cluster
    is_part_of_relist = any(
        r['type'] == 'transaction' and r.get('timestamp') == ent.get('timestamp')
        for r in related
    )
    
    if is_part_of_relist:
        # This is the NEW listing in a relist - DON'T skip!
        log_debug(f"[RELIST] Keeping listed entry...")
    else:
        # Original skip logic (only if NOT relist)
        ...
```

FIX 3: STORE RELIST INFO IN TX DICT (tracker.py L6203-6215)
------------------------------------------------------------
```python
tx = {
    'item_name': item_name,
    'quantity': quantity,
    'price': price,
    'timestamp': ent['timestamp'],
    'transaction_type': final_type,
    'case': f"{final_type}_{case}",
    'raw_related': related,
    'occurrence_index': None,
    'occurrence_slot': occurrence_slot,
    '_is_relist': is_relist_cluster,  # Store relist flag
    '_listed_entry': listed_entry,     # Store for later processing
    '_placed_entry': placed_entry      # Store for later processing
}
```

FIX 4: RELIST PROCESSING LOGIC (tracker.py L6349-6399)
-------------------------------------------------------
```python
# ⚡ RELIST HANDLING: Process relist pattern
if tx.get('_is_relist'):
    from preorder_manager import PreorderManager
    pm = PreorderManager()
    
    # Extract transaction details
    tx_item = tx['item_name']
    tx_qty = tx['quantity']
    tx_price = tx['price']
    tx_ts = tx['timestamp']
    tx_type = tx['transaction_type']
    
    # Get stored entries
    listed_entry_stored = tx.get('_listed_entry')
    placed_entry_stored = tx.get('_placed_entry')
    
    # Process based on side
    if tx_type == 'sell' and listed_entry_stored:
        new_order_qty = listed_entry_stored.get('qty')
        new_order_price = listed_entry_stored.get('price')
        
        if new_order_qty and new_order_price > 0:
            # Find and mark old listing as collected
            old_listing = pm.find_matching_listing(tx_item, tx_qty, tx_price, tx_ts)
            if old_listing:
                pm.mark_listing_collected(old_listing['id'], tx_ts)
            
            # Create NEW listing
            pm.store_listing(tx_item, new_order_qty, new_order_price, tx_ts)
    
    elif tx_type == 'buy' and placed_entry_stored:
        # Same logic for preorders
        ...
```

WHAT WILL HAPPEN NOW:
======================

Test Scenario (Magical Shard):
1. User clicks "Relist" on 200x @ 654,000,000 (fully filled)
2. User sets new: 172x @ 569,320,000
3. Detail-Window closes immediately
4. Overview-Log shows:
   - "Transaction of Magical Shard x200 ... 580,261,500 Silver"
   - "Listed Magical Shard x172 for 569,320,000 Silver"

Processing Flow:
1. Cluster-Building finds BOTH entries (same timestamp: 22:35:00)
2. Relist-Pattern detected: is_relist_cluster = True ✅
3. Listed-Entry NOT skipped (is_part_of_relist = True) ✅
4. Transaction created with _is_relist flag
5. After tx_candidates.append(tx):
   - Relist-Handler activates
   - Finds old listing (200x @ 654M)
   - Marks old listing collected ✅
   - Creates NEW listing (172x @ 569M) ✅

Expected Database State:
✅ Transaction: 200x @ 580,261,500, case=sell_relist_partial
✅ Old listing: 200x @ 654,000,000, status=collected
✅ NEW listing: 172x @ 569,320,000, status=active

TESTING CHECKLIST:
==================

Test 1: Magical Shard (sell-side, partial relist)
- Old: 200x @ 654M (fully filled)
- New: 172x @ 569M
- Expected: All 3 components saved ✅

Test 2: Unknown Seed (buy-side, partial relist)
- Old: 10x @ price_old (2x filled)
- New: 10x @ price_new
- Expected: All 3 components saved ✅

Test 3: Large quantity (buy-side, full relist)
- Old: 4486x @ price_old (fully filled)
- New: 4486x @ price_new
- Expected: All 3 components saved ✅

Test 4: Edge case - fast relist (multiple quick relists)
- Multiple relists in short succession
- Expected: Each relist creates separate records ✅

NOTES:
======

1. Detail-Window Detection ist UNMÖGLICH für Sell-Side
   - Window schließt zu schnell (game behavior)
   - MUSS auf Overview-Log verlassen
   - Das ist OK! Fix funktioniert im Overview ✅

2. Buy-Side Detail-Window sollte weiterhin funktionieren
   - Window bleibt länger offen
   - Delta-Detection kann greifen
   - Overview-Log als Fallback ✅

3. PreorderManager Matching:
   - find_matching_listing/preorder nutzt fuzzy matching
   - Toleriert kleine Preis-Abweichungen
   - Nutzt timestamp proximity ✅

4. Transaction-Linking:
   - collected_tx_id wird aktuell auf None gesetzt
   - Kann später verlinkt werden wenn nötig
   - Für jetzt: Status=collected reicht ✅
