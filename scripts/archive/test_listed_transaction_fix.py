#!/usr/bin/env python3
"""
Comprehensive test for the listed+transaction cluster fix.

Tests multiple scenarios:
1. ✅ Sell with listed+transaction (original issue)
2. ✅ Sell with listed-only (should skip)
3. ✅ Buy with placed+transaction (should work)
4. ✅ Sell with transaction-only (should work)
5. ✅ Multiple events in same cluster
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracker import MarketTracker
import sqlite3

def check_db(item_name, expected_count, description):
    """Helper to check database for specific item"""
    conn = sqlite3.connect('bdo_tracker.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT timestamp, transaction_type, item_name, quantity, price, tx_case
        FROM transactions
        WHERE item_name = ?
        AND timestamp >= datetime('now', '-1 hour')
        ORDER BY timestamp DESC
    """, (item_name,))
    
    results = cursor.fetchall()
    conn.close()
    
    success = len(results) == expected_count
    status = "✅" if success else "❌"
    
    print(f"\n{status} {description}")
    print(f"   Expected: {expected_count} transaction(s), Got: {len(results)}")
    
    if results:
        for r in results:
            ts, tx_type, item, qty, price, case = r
            print(f"   → {ts} | {tx_type} | {qty}x {item} @ {price:,} Silver | {case}")
    
    return success

def test_all_scenarios():
    """Run comprehensive tests"""
    print("=" * 80)
    print("COMPREHENSIVE TEST: Listed+Transaction Cluster Fix")
    print("=" * 80)
    
    mt = MarketTracker(debug=False)  # Disable debug for cleaner output
    all_passed = True
    
    # Test 1: Sell with listed+transaction (original issue - Magical Shard)
    print("\n--- TEST 1: Sell with Listed+Transaction (Magical Shard) ---")
    text1 = (
        "Central Market Warehouse Balance @ 64,868,771,502 Buy "
        "2025.10.12 15.00 2025.10.12 15.00 "
        "Listed Magical Shard x100 for 310,000,000 Silver. The price of enhancement m_. "
        "Transaction of Magical Shard x100 worth 292,867,500 Silver has been complet__ "
        "Items Listed 756 Sales Completed"
    )
    mt.process_ocr_text(text1)
    all_passed &= check_db("Magical Shard", 1, "Sell with listed+transaction should save 1 transaction")
    
    # Test 2: Sell with listed-only (no transaction - should skip)
    print("\n--- TEST 2: Sell with Listed-Only (Pure Powder Reagent) ---")
    text2 = (
        "Central Market Warehouse Balance @ 64,868,771,502 Buy "
        "2025.10.12 15.01 2025.10.12 15.01 "
        "Listed Pure Powder Reagent x5000 for 23,500,000 Silver. "
        "Items Listed 757 Sales Completed"
    )
    mt.process_ocr_text(text2)
    all_passed &= check_db("Pure Powder Reagent", 0, "Sell with listed-only should NOT save (no transaction)")
    
    # Test 3: Buy with placed+transaction (should work as before)
    print("\n--- TEST 3: Buy with Placed+Transaction (Dehkia's Fragment) ---")
    text3 = (
        "Central Market Warehouse Balance @ 64,868,771,502 Sell "
        "2025.10.12 15.02 2025.10.12 15.02 "
        "Placed order of Dehkia's Fragment x5 for 255,000,000 Silver "
        "Transaction of Dehkia's Fragment x5 worth 255,000,000 Silver has been completed. "
        "Orders Completed"
    )
    mt.process_ocr_text(text3)
    all_passed &= check_db("Dehkia's Fragment", 1, "Buy with placed+transaction should save 1 transaction")
    
    # Test 4: Sell with transaction-only (no listed - should work)
    print("\n--- TEST 4: Sell with Transaction-Only (Crystallized Despair) ---")
    text4 = (
        "Central Market Warehouse Balance @ 64,689,571,502 Buy "
        "2025.10.12 15.03 2025.10.12 15.03 "
        "Transaction of Crystallized Despair x10 worth 256,000,000 Silver has been completed. "
        "Items Listed 756 Sales Completed"
    )
    mt.process_ocr_text(text4)
    all_passed &= check_db("Crystallized Despair", 1, "Sell with transaction-only should save 1 transaction")
    
    # Test 5: Sell relist_partial (listed+transaction+withdrew)
    print("\n--- TEST 5: Sell Relist Partial (Black Stone Powder) ---")
    text5 = (
        "Central Market Warehouse Balance @ 64,689,571,502 Buy "
        "2025.10.12 15.04 2025.10.12 15.04 2025.10.12 15.04 "
        "Listed Black Stone Powder x100 for 470,000 Silver. "
        "Transaction of Black Stone Powder x88 worth 414,160 Silver has been completed. "
        "Withdrew Black Stone Powder x12 from market listing "
        "Items Listed 756 Sales Completed"
    )
    mt.process_ocr_text(text5)
    all_passed &= check_db("Black Stone Powder", 1, "Sell relist_partial should save 1 transaction")
    
    # Summary
    print("\n" + "=" * 80)
    if all_passed:
        print("✅ ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED!")
    print("=" * 80)
    
    return all_passed

if __name__ == '__main__':
    success = test_all_scenarios()
    sys.exit(0 if success else 1)
