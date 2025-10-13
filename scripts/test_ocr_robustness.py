"""
Test script to verify OCR robustness fixes:
1. Silver keyword normalization (Silve_ → Silver)
2. Transaction price priority (even when qty is None)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsing import extract_details_from_entry


def test_silver_keyword_variants():
    """Test that OCR variants of 'Silver' are correctly normalized."""
    print("\n=== TEST 1: Silver Keyword Normalization ===\n")
    
    test_cases = [
        # (ts_text, entry_text, expected_price_not_none)
        ("10.13 22:06", "Transaction of Birch Sap x5000 worth 585,585,000 Silve_", True),  # OCR error: Silve_ → Silver
        ("10.13 22:06", "Sold Magical Shard x10 worth 23,000,000 Silve ", True),  # OCR error: 'Silve ' → Silver
        ("10.14 00:03", "Transaction of Concentrated Magical Black Stone xl3O worth 859,301,625 Silv:", True),  # OCR error: Silv: → Silver
    ]
    
    passed = 0
    failed = 0
    
    for ts_text, entry_text, expected_price in test_cases:
        details = extract_details_from_entry(ts_text, entry_text)
        price = details.get('price')
        
        has_price = (price is not None and price > 0)
        test_passed = (has_price == expected_price)
        
        if test_passed:
            status = "✅ PASS"
            passed += 1
        else:
            status = "❌ FAIL"
            failed += 1
        
        print(f"{status}")
        print(f"  Entry: {entry_text[:60]}...")
        print(f"  Expected price: {'NOT None' if expected_price else 'None'}")
        print(f"  Got price: {price}")
        print()
    
    print(f"Results: {passed} passed, {failed} failed\n")
    return failed == 0


def test_transaction_price_priority():
    """
    Test that transaction price is used even when qty is None.
    This simulates the cluster assembly logic in tracker.py.
    """
    print("\n=== TEST 2: Transaction Price Priority ===\n")
    
    # Simulate a cluster with transaction (price only) + listed (qty + price)
    print("Scenario: Transaction line has price but no qty")
    print("          Listed line has both qty and price")
    print()
    
    # Parse the transaction line
    tx_entry = extract_details_from_entry(
        "10.13 22:06",
        "Transaction of Birch Sap worth 585,585,000 Silver"
    )
    
    # Parse the listed line
    listed_entry = extract_details_from_entry(
        "10.13 22:06",
        "Listed Birch Sap x5000 for 650,000,000 Silver"
    )
    
    print(f"Transaction entry: qty={tx_entry.get('qty')}, price={tx_entry.get('price')}")
    print(f"Listed entry: qty={listed_entry.get('qty')}, price={listed_entry.get('price')}")
    print()
    
    # Simulate the tracker.py logic (simplified)
    cluster_entries = [tx_entry, listed_entry]
    
    # Find transaction entry (may have None qty)
    tx_rel = next((r for r in cluster_entries if r['type'] == 'transaction'), None)
    
    # Initialize from anchor (could be either)
    quantity = tx_entry['qty'] or listed_entry['qty']
    price = tx_entry['price'] or listed_entry['price']
    
    # Apply priority logic (NEW FIX)
    if tx_rel is not None:
        if tx_rel.get('qty'):
            quantity = tx_rel['qty']
        # CRITICAL: Always use transaction price if available (even when qty is None)
        if tx_rel.get('price'):
            price = tx_rel['price']
    
    print("Final assembled transaction:")
    print(f"  qty={quantity}, price={price}")
    print()
    
    # Verify correctness
    expected_qty = 5000  # from listed
    expected_price = 585585000  # from transaction (NOT listed!)
    
    if quantity == expected_qty and price == expected_price:
        print("✅ PASS: Transaction price correctly prioritized")
        return True
    else:
        print("❌ FAIL: Wrong values selected")
        print(f"  Expected: qty={expected_qty}, price={expected_price}")
        print(f"  Got: qty={quantity}, price={price}")
        return False


def test_silver_pattern_edge_cases():
    """Test additional edge cases for Silver keyword."""
    print("\n=== TEST 3: Edge Cases ===\n")
    
    test_cases = [
        # Various OCR errors
        ("10.13 22:06", "Transaction of Item x10 worth 1,000,000 SILVER", True),  # All caps
        ("10.13 22:06", "Transaction of Item x10 worth 1,000,000 silver", True),  # Lower case
        ("10.13 22:06", "Transaction of Item x10 worth 1,000,000 SiLvEr", True),  # Mixed case
    ]
    
    passed = 0
    failed = 0
    
    for ts_text, entry_text, expected_price in test_cases:
        details = extract_details_from_entry(ts_text, entry_text)
        price = details.get('price')
        
        has_price = (price is not None and price > 0)
        test_passed = (has_price == expected_price)
        
        if test_passed:
            status = "✅ PASS"
            passed += 1
        else:
            status = "❌ FAIL"
            failed += 1
        
        print(f"{status}")
        print(f"  Entry: {entry_text[:60]}...")
        print(f"  Got price: {price}")
        print()
    
    print(f"Results: {passed} passed, {failed} failed\n")
    return failed == 0


if __name__ == "__main__":
    print("=" * 70)
    print("OCR ROBUSTNESS TEST SUITE")
    print("=" * 70)
    
    all_passed = True
    
    # Run all tests
    all_passed &= test_silver_keyword_variants()
    all_passed &= test_transaction_price_priority()
    all_passed &= test_silver_pattern_edge_cases()
    
    print("=" * 70)
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 70)
    
    sys.exit(0 if all_passed else 1)
