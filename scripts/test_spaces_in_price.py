"""
Test: OCR-Fehler mit Leerzeichen in Preisen (z.B., "585, 585, OO0")
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsing import extract_details_from_entry
from utils import normalize_numeric_str

def test_normalize_with_spaces():
    """Test normalization function with spaces"""
    print("=" * 80)
    print("TEST 1: Normalize Numeric Strings with Spaces")
    print("=" * 80)
    
    test_cases = [
        ("585,585,000", 585585000, "Normal format"),
        ("585, 585, 000", 585585000, "Spaces after commas"),
        ("585, 585, OO0", 585585000, "Spaces + O→0 conversion"),
        ("1 225 000 000", 1225000000, "Spaces as thousands separators"),
        ("765,000,000", 765000000, "Normal large number"),
    ]
    
    passed = 0
    failed = 0
    
    for input_str, expected, description in test_cases:
        result = normalize_numeric_str(input_str)
        status = "✅" if result == expected else "❌"
        if result == expected:
            passed += 1
        else:
            failed += 1
        print(f"{status} {description}")
        print(f"   Input: '{input_str}'")
        print(f"   Expected: {expected:,}")
        print(f"   Got: {result:,}" if result else f"   Got: None")
        print()
    
    print(f"Result: {passed} passed, {failed} failed\n")
    return failed == 0

def test_parsing_with_spaces():
    """Test full parsing with spaces in prices"""
    print("=" * 80)
    print("TEST 2: Parse Transaction Text with Spaces in Price")
    print("=" * 80)
    
    test_cases = [
        # Case 1: Exact OCR error from log
        (
            "2025.10.12 04.04",
            "Transaction of Magical Shard x2OO worth 585, 585, OO0 Silver has been complet__.",
            {
                'item': 'Magical Shard',
                'qty': 200,
                'price': 585585000,
                'type': 'transaction'
            },
            "OCR error: spaces after commas + O→0"
        ),
        # Case 2: Normal format (should still work)
        (
            "2025.10.12 04.04",
            "Transaction of Magical Shard x200 worth 585,585,000 Silver has been completed.",
            {
                'item': 'Magical Shard',
                'qty': 200,
                'price': 585585000,
                'type': 'transaction'
            },
            "Normal format (control test)"
        ),
        # Case 3: Trace of Nature (from same log)
        (
            "2025.10.12 04.04",
            "Transaction of Trace of Nature X5,O00 worth 765,000,000 Silver has been com__.",
            {
                'item': 'Trace of Nature',
                'qty': 5000,
                'price': 765000000,
                'type': 'transaction'
            },
            "Normal format without spaces"
        ),
        # Case 4: Listed with spaces
        (
            "2025.10.12 04.04",
            "Listed Magical Shard x2OO for 662, 000, 000 Silver.",
            {
                'item': 'Magical Shard',
                'qty': 200,
                'price': 662000000,
                'type': 'listed'
            },
            "Listed event with spaces in price"
        ),
    ]
    
    passed = 0
    failed = 0
    
    for ts, text, expected, description in test_cases:
        details = extract_details_from_entry(ts, text)
        
        # Check each field
        item_ok = details.get('item') == expected['item']
        qty_ok = details.get('qty') == expected['qty']
        price_ok = details.get('price') == expected['price']
        type_ok = details.get('type') == expected['type']
        
        all_ok = item_ok and qty_ok and price_ok and type_ok
        status = "✅" if all_ok else "❌"
        
        if all_ok:
            passed += 1
        else:
            failed += 1
        
        print(f"{status} {description}")
        print(f"   Text: {text[:80]}...")
        print(f"   Expected: {expected['type']} | {expected['item']} x{expected['qty']:,} @ {expected['price']:,}")
        print(f"   Got:      {details.get('type')} | {details.get('item')} x{details.get('qty') or 'None'} @ {details.get('price') or 'None'}")
        
        if not all_ok:
            if not item_ok:
                print(f"   ⚠️  Item mismatch: expected '{expected['item']}', got '{details.get('item')}'")
            if not qty_ok:
                print(f"   ⚠️  Qty mismatch: expected {expected['qty']}, got {details.get('qty')}")
            if not price_ok:
                print(f"   ⚠️  Price mismatch: expected {expected['price']:,}, got {details.get('price') or 'None'}")
            if not type_ok:
                print(f"   ⚠️  Type mismatch: expected '{expected['type']}', got '{details.get('type')}'")
        print()
    
    print(f"Result: {passed} passed, {failed} failed\n")
    return failed == 0

def main():
    print("\n" + "=" * 80)
    print("OCR SPACES IN PRICE FIX - TEST SUITE")
    print("Testing: '585, 585, OO0' → 585,585,000")
    print("=" * 80 + "\n")
    
    test1_ok = test_normalize_with_spaces()
    test2_ok = test_parsing_with_spaces()
    
    print("=" * 80)
    if test1_ok and test2_ok:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print("=" * 80)
    
    return 0 if (test1_ok and test2_ok) else 1

if __name__ == "__main__":
    sys.exit(main())
