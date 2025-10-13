#!/usr/bin/env python3
"""
Test with clean database for each scenario.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracker import MarketTracker
import sqlite3

def reset_db():
    """Clear transactions table"""
    conn = sqlite3.connect('bdo_tracker.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE timestamp >= datetime('now', '-1 hour')")
    conn.commit()
    conn.close()

def check_latest(item_name, expected_type, expected_qty, expected_case):
    """Check latest transaction for item"""
    conn = sqlite3.connect('bdo_tracker.db')
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT timestamp, transaction_type, item_name, quantity, price, tx_case
        FROM transactions
        WHERE item_name = ?
        AND timestamp >= datetime('now', '-1 hour')
        ORDER BY timestamp DESC
        LIMIT 1
    """, (item_name,))
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        print(f"   ❌ No transaction found for {item_name}")
        return False
    
    ts, tx_type, item, qty, price, case = result
    
    success = (tx_type == expected_type and qty == expected_qty and case == expected_case)
    status = "✅" if success else "❌"
    
    print(f"   {status} {ts} | {tx_type} | {qty}x {item} @ {price:,} Silver | {case}")
    if not success:
        print(f"      Expected: {expected_type} | {expected_qty}x | {expected_case}")
    
    return success

def test_scenario_1():
    """Test 1: Sell with listed+transaction (original issue)"""
    print("\n--- TEST 1: Sell with Listed+Transaction (Magical Shard) ---")
    reset_db()
    
    text = (
        "Central Market Warehouse Balance @ 64,868,771,502 Buy "
        "2025.10.12 15.10 2025.10.12 15.10 "
        "Listed Magical Shard x100 for 310,000,000 Silver. The price of enhancement m_. "
        "Transaction of Magical Shard x100 worth 292,867,500 Silver has been complet__ "
        "Items Listed 756 Sales Completed"
    )
    
    mt = MarketTracker(debug=True)
    mt.process_ocr_text(text)
    
    return check_latest("Magical Shard", "sell", 100, "sell_relist_full")

def test_scenario_2():
    """Test 2: Sell with transaction-only (no listed)"""
    print("\n--- TEST 2: Sell with Transaction-Only (Crystallized Despair) ---")
    reset_db()
    
    text = (
        "Central Market Warehouse Balance @ 64,689,571,502 Buy "
        "2025.10.12 15.11 2025.10.12 15.11 "
        "Transaction of Crystallized Despair x10 worth 256,000,000 Silver has been completed. "
        "Items Listed 756 Sales Completed"
    )
    
    mt = MarketTracker(debug=True)
    mt.process_ocr_text(text)
    
    return check_latest("Crystallized Despair", "sell", 10, "sell_collect")

def test_scenario_3():
    """Test 3: Sell relist_partial with listed+transaction+withdrew"""
    print("\n--- TEST 3: Sell Relist Partial (Black Stone Powder) ---")
    reset_db()
    
    text = (
        "Central Market Warehouse Balance @ 64,689,571,502 Buy "
        "2025.10.12 15.12 2025.10.12 15.12 2025.10.12 15.12 "
        "Listed Black Stone Powder x100 for 470,000 Silver. "
        "Transaction of Black Stone Powder x88 worth 414,160 Silver has been completed. "
        "Withdrew Black Stone Powder x12 from market listing "
        "Items Listed 756 Sales Completed"
    )
    
    mt = MarketTracker(debug=True)
    mt.process_ocr_text(text)
    
    return check_latest("Black Stone Powder", "sell", 88, "sell_relist_partial")

if __name__ == '__main__':
    print("=" * 80)
    print("TARGETED TEST: Listed+Transaction Fix")
    print("=" * 80)
    
    test1 = test_scenario_1()
    test2 = test_scenario_2()
    test3 = test_scenario_3()
    
    print("\n" + "=" * 80)
    if test1 and test2 and test3:
        print("✅ ALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED!")
        sys.exit(1)
