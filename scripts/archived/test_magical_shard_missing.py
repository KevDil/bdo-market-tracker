#!/usr/bin/env python3
"""
Test case for missing Magical Shard transaction (200x for 585,585,000 Silver @ 2025-10-12 14:12).

Problem: Transaction was recognized in OCR but not saved to database.
Root Cause: When cluster has both 'listed' and 'transaction', and 'listed' is processed first,
           the code skips the cluster (line 726-728 in tracker.py).
           
This prevents the transaction from being saved even though it was recognized.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracker import MarketTracker

def test_magical_shard_missing():
    """
    Reproduces the exact scenario from ocr_log.txt line 139:
    - sell_overview window
    - Listed Magical Shard x200 for 654,000,000 Silver
    - Transaction of Magical Shard x200 worth 585,585,000 Silver has been completed
    """
    print("=" * 80)
    print("TEST: Magical Shard Transaction Missing (200x @ 585,585,000 Silver)")
    print("=" * 80)
    
    # Exact text from ocr_log.txt line 139
    text = (
        "Central Market Warehouse Balance @ 64,868,771,502 Buy "
        "2025.10.12 14.12 2025.10.12 14.12 2025.10.12 13.50 2025.10.12 13.50 "
        "Listed Magical Shard x2OO for 654,000,000 Silver. The price of enhancement m_. "
        "Transaction of Magical Shard x2OO worth 585,585,000 Silver has been complet__ "
        "Placed order of Pure Powder Reagent x5,000 for 67,500,000 Silver "
        "Transaction of Pure Powder Reagent xl,000 worth 13,600,000 Silver has been "
        "Warehouse Capacity 6 8,714.5 / 11,000 VT Pearl Item Selling Limit 31.590 Sell Sell "
        "Enter a search term Enter a search term: Items Listed 756 Sales Completed"
    )
    
    mt = MarketTracker(debug=True)
    
    # Process the text
    print("\n--- Processing OCR Text ---")
    mt.process_ocr_text(text)
    
    # Check if transaction was saved
    print("\n--- Checking Database ---")
    import sqlite3
    conn = sqlite3.connect('bdo_tracker.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT timestamp, transaction_type, item_name, quantity, price, tx_case
        FROM transactions
        WHERE item_name = 'Magical Shard'
        AND timestamp >= '2025-10-12 14:00:00'
        AND timestamp <= '2025-10-12 14:15:00'
        ORDER BY timestamp DESC
    """)
    
    results = cursor.fetchall()
    conn.close()
    
    if results:
        print(f"\n✅ Found {len(results)} Magical Shard transaction(s) around 14:12:")
        for r in results:
            ts, tx_type, item, qty, price, case = r
            print(f"   {ts} | {tx_type} | {qty}x {item} @ {price:,} Silver | {case}")
    else:
        print("\n❌ No Magical Shard transactions found around 14:12")
        print("   Expected: 2025-10-12 14:12:00 | sell | 200x Magical Shard @ 585,585,000 Silver | sell_relist_full")
    
    print("\n--- Expected Behavior ---")
    print("✅ Should save: 200x Magical Shard for 585,585,000 Silver (sell_relist_full)")
    print("   - Listed 200x for 654,000,000 (new listing)")
    print("   - Transaction 200x for 585,585,000 (previous listing sold)")
    print("   - Case: sell_relist_full (no withdrew event)")
    
    print("\n" + "=" * 80)
    
    return len(results) > 0

if __name__ == '__main__':
    success = test_magical_shard_missing()
    sys.exit(0 if success else 1)
