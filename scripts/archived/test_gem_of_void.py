"""
Test: Gem of Void Item-Name-Korrektur und Parsing
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsing import extract_details_from_entry
from utils import correct_item_name, _load_item_names

def test_gem_of_void_correction():
    """Test dass 'Gem Of Void' korrekt zu 'Gem of Void' korrigiert wird"""
    print("=" * 80)
    print("TEST 1: Item Name Correction - Gem Of Void")
    print("=" * 80)
    
    # Check if Gem of Void is in whitelist
    whitelist = _load_item_names()
    has_gem = any("gem of void" in name.lower() for name in whitelist)
    print(f"\n'Gem of Void' in whitelist: {has_gem}")
    
    test_cases = [
        ("Gem Of Void", "Gem of Void", "OCR with capital Of"),
        ("Gem of Void", "Gem of Void", "Correct spelling"),
        ("gem of void", "Gem of Void", "All lowercase"),
        ("GEM OF VOID", "Gem of Void", "All uppercase"),
        ("Gem of  Void", "Gem of Void", "Double space (OCR error)"),
    ]
    
    passed = 0
    failed = 0
    
    for input_name, expected, description in test_cases:
        corrected = correct_item_name(input_name, min_score=80)
        status = "✅" if corrected == expected else "❌"
        
        if corrected == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} {description}")
        print(f"   Input: '{input_name}'")
        print(f"   Expected: '{expected}'")
        print(f"   Got: '{corrected}'")
        print()
    
    print(f"Result: {passed}/{len(test_cases)} passed\n")
    return failed == 0

def test_gem_of_void_parsing():
    """Test dass Gem Of Void korrekt geparst wird"""
    print("=" * 80)
    print("TEST 2: Parse Gem Of Void Transaction (Real OCR Text)")
    print("=" * 80)
    
    # Real OCR text from log
    ts = "2025.10.12 11.06"
    text = "Placed order of Gem of Void xlO for 383,000,000 Silver"
    
    details = extract_details_from_entry(ts, text)
    
    print(f"\nOCR Text: {text}")
    print(f"Parsed:")
    print(f"  Type: {details.get('type')}")
    print(f"  Item: '{details.get('item')}'")
    print(f"  Qty: {details.get('qty')}")
    print(f"  Price: {details.get('price'):,}" if details.get('price') else f"  Price: None")
    
    expected_item = "Gem of Void"
    expected_qty = 10
    expected_price = 383000000
    expected_type = "placed"
    
    item_ok = details.get('item') == expected_item
    qty_ok = details.get('qty') == expected_qty
    price_ok = details.get('price') == expected_price
    type_ok = details.get('type') == expected_type
    
    all_ok = item_ok and qty_ok and price_ok and type_ok
    
    print(f"\nValidation:")
    print(f"  Item: {'✅' if item_ok else '❌'} (expected '{expected_item}')")
    print(f"  Qty: {'✅' if qty_ok else '❌'} (expected {expected_qty})")
    print(f"  Price: {'✅' if price_ok else '❌'} (expected {expected_price:,})")
    print(f"  Type: {'✅' if type_ok else '❌'} (expected '{expected_type}')")
    
    return all_ok

def main():
    print("\n" + "=" * 80)
    print("GEM OF VOID - ITEM NAME & PARSING TEST")
    print("=" * 80 + "\n")
    
    test1_ok = test_gem_of_void_correction()
    test2_ok = test_gem_of_void_parsing()
    
    print("=" * 80)
    if test1_ok and test2_ok:
        print("✅ ALL TESTS PASSED - Gem of Void can now be tracked!")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 80)
    
    return 0 if (test1_ok and test2_ok) else 1

if __name__ == "__main__":
    sys.exit(main())
