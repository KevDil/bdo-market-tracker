"""
Verification Script: Relist Detection Fix
==========================================

This script verifies that the relist detection correctly:
1. Detects relist pattern in Detail-Window (balance↓ + warehouse↑)
2. Saves auto-collect transaction IMMEDIATELY (using old preorder price)
3. Detects and saves instant buy IMMEDIATELY (if warehouse_delta > expected)
4. Saves new preorder IMMEDIATELY (adjusted for instant buy: input_qty - instant_buy_qty)
5. All operations happen in Detail-Window (NO reliance on Transaction-Log parsing)

CRITICAL: Transaction-Log is ONLY visible in Overview!
- Detail-Window has NO transaction log
- Cannot rely on log parsing (overview may not be scanned)
- Must save everything DURING relist detection

Expected Database State After Relist Test (Trace of Nature x5000 @ 770M):
---------------------------------------------------------------------------
PREORDERS:
- OLD: ID=6, 5000x @ 770M, status='collected', collected_at=19:47:00
- NEW: ID=7, 4979x @ 766,766,000, status='active', placed_at=19:47:00
  (Note: qty reduced by instant buy: 5000 - 21 = 4979)

TRANSACTIONS:
- Auto-Collect: 5000x @ 770M (calculated from old preorder price)
- Instant Buy: 21x @ 3,234,000 (detected from warehouse surplus)

Warehouse Delta Verification:
14,548 (before) + 5,000 (auto-collect) + 21 (instant buy) = 19,569 (after) ✓

Balance Delta Verification:
185,563,029,875 (before) - 766,766,000 (new preorder) - 3,234,000 (instant buy) 
= 184,793,029,875 (after) ✓
"""

import sqlite3
from datetime import datetime, timedelta

def verify_relist_fix():
    print(__doc__)
    print("\n" + "="*80)
    print("VERIFICATION CHECKS")
    print("="*80)
    
    # Connect to database
    conn = sqlite3.connect('bdo_tracker.db')
    cur = conn.cursor()
    
    # Check 1: Old preorder marked as collected
    print("\n[CHECK 1] Old Preorder Status")
    cur.execute('''
        SELECT id, item_name, quantity, price, status, collected_at
        FROM preorders
        WHERE item_name = 'Trace of Nature'
        AND quantity = 5000
        AND price = 770000000
        ORDER BY timestamp DESC LIMIT 1
    ''')
    
    old_preorder = cur.fetchone()
    if old_preorder and old_preorder[4] == 'collected':
        print(f"✅ OLD PREORDER: ID={old_preorder[0]}, status='collected', collected_at={old_preorder[5]}")
    else:
        print(f"❌ OLD PREORDER NOT FOUND OR NOT COLLECTED: {old_preorder}")
        return False
    
    # Check 2: New preorder created with correct quantity/price
    print("\n[CHECK 2] New Preorder Creation")
    cur.execute('''
        SELECT id, item_name, quantity, price, status, timestamp
        FROM preorders
        WHERE item_name = 'Trace of Nature'
        AND quantity = 4979
        AND price = 766766000
        AND status = 'active'
        ORDER BY timestamp DESC LIMIT 1
    ''')
    
    new_preorder = cur.fetchone()
    if new_preorder:
        print(f"✅ NEW PREORDER: ID={new_preorder[0]}, {new_preorder[2]}x @ {new_preorder[3]:,}, status='{new_preorder[4]}'")
    else:
        print(f"❌ NEW PREORDER NOT FOUND (4979x @ 766,766,000)")
        return False
    
    # Check 3: Auto-collect transaction saved
    print("\n[CHECK 3] Auto-Collect Transaction")
    cur.execute('''
        SELECT id, item_name, quantity, price, transaction_type, tx_case, timestamp
        FROM transactions
        WHERE item_name = 'Trace of Nature'
        AND quantity = 5000
        AND price = 770000000
        ORDER BY timestamp DESC LIMIT 1
    ''')
    
    autocollect_tx = cur.fetchone()
    if autocollect_tx:
        print(f"✅ AUTO-COLLECT TX: ID={autocollect_tx[0]}, {autocollect_tx[2]}x @ {autocollect_tx[3]:,}, case='{autocollect_tx[5]}'")
    else:
        print(f"❌ AUTO-COLLECT TRANSACTION NOT FOUND (5000x @ 770M)")
        return False
    
    # Check 4: Instant buy transaction saved
    print("\n[CHECK 4] Instant Buy Transaction")
    cur.execute('''
        SELECT id, item_name, quantity, price, transaction_type, tx_case, timestamp
        FROM transactions
        WHERE item_name = 'Trace of Nature'
        AND quantity = 21
        AND price = 3234000
        ORDER BY timestamp DESC LIMIT 1
    ''')
    
    instant_buy_tx = cur.fetchone()
    if instant_buy_tx:
        print(f"✅ INSTANT BUY TX: ID={instant_buy_tx[0]}, {instant_buy_tx[2]}x @ {instant_buy_tx[3]:,}, case='{instant_buy_tx[5]}'")
    else:
        print(f"❌ INSTANT BUY TRANSACTION NOT FOUND (21x @ 3,234,000)")
        return False
    
    # Check 5: No duplicates
    print("\n[CHECK 5] No Duplicate Transactions")
    cur.execute('''
        SELECT COUNT(*) FROM transactions
        WHERE item_name = 'Trace of Nature'
        AND timestamp >= datetime('now', '-1 hour')
    ''')
    
    tx_count = cur.fetchone()[0]
    if tx_count == 2:
        print(f"✅ EXACTLY 2 TRANSACTIONS (auto-collect + instant buy)")
    else:
        print(f"❌ WRONG TRANSACTION COUNT: {tx_count} (expected 2)")
        return False
    
    # Check 6: No duplicate preorders
    print("\n[CHECK 6] No Duplicate Preorders")
    cur.execute('''
        SELECT COUNT(*) FROM preorders
        WHERE item_name = 'Trace of Nature'
        AND status = 'active'
    ''')
    
    preorder_count = cur.fetchone()[0]
    if preorder_count == 1:
        print(f"✅ EXACTLY 1 ACTIVE PREORDER")
    else:
        print(f"❌ WRONG ACTIVE PREORDER COUNT: {preorder_count} (expected 1)")
        return False
    
    # Check 7: Timestamps are consistent (all within 30 seconds)
    print("\n[CHECK 7] Timestamp Consistency")
    cur.execute('''
        SELECT MIN(timestamp), MAX(timestamp)
        FROM (
            SELECT timestamp FROM transactions WHERE item_name = 'Trace of Nature' AND timestamp >= datetime('now', '-1 hour')
            UNION ALL
            SELECT timestamp FROM preorders WHERE item_name = 'Trace of Nature' AND timestamp >= datetime('now', '-1 hour')
        )
    ''')
    
    min_ts, max_ts = cur.fetchone()
    if min_ts and max_ts:
        min_dt = datetime.fromisoformat(min_ts)
        max_dt = datetime.fromisoformat(max_ts)
        diff = (max_dt - min_dt).total_seconds()
        
        if diff <= 30:
            print(f"✅ ALL TIMESTAMPS WITHIN 30 SECONDS (delta: {diff:.1f}s)")
        else:
            print(f"❌ TIMESTAMPS TOO FAR APART: {diff:.1f}s (expected ≤30s)")
            return False
    
    conn.close()
    
    print("\n" + "="*80)
    print("✅ ALL CHECKS PASSED - Relist Fallback Fix Working Correctly!")
    print("="*80)
    return True

if __name__ == '__main__':
    verify_relist_fix()
