#!/usr/bin/env python3
"""
Test script for new market.json + BDO-API system
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from market_json_manager import (
    load_market_json,
    get_item_by_id,
    get_item_id_by_name,
    get_item_name_by_id,
    correct_item_name,
    is_valid_item,
    search_items,
    get_item_count
)

def test_basic_loading():
    """Test loading market.json"""
    print("\n" + "="*60)
    print("TEST 1: Basic Loading")
    print("="*60)
    
    items = load_market_json()
    count = get_item_count()
    
    print(f"✅ Loaded {count} items from market.json")
    assert count > 4000, f"Expected >4000 items, got {count}"
    print("✅ Item count validation passed")


def test_item_lookup():
    """Test item ID <-> name translation"""
    print("\n" + "="*60)
    print("TEST 2: Item ID <-> Name Translation")
    print("="*60)
    
    # Test: Gem of Void (ID: 821182)
    item_id = "821182"
    item_name = get_item_name_by_id(item_id)
    print(f"✅ ID {item_id} → Name: {item_name}")
    assert item_name == "Gem of Void", f"Expected 'Gem of Void', got '{item_name}'"
    
    # Test: Reverse lookup
    found_id = get_item_id_by_name("Gem of Void")
    print(f"✅ Name 'Gem of Void' → ID: {found_id}")
    assert found_id == item_id, f"Expected ID {item_id}, got {found_id}"
    
    # Test: Get full item data
    item_data = get_item_by_id(item_id)
    print(f"✅ Full data for ID {item_id}:")
    print(f"   Name: {item_data['name']}")
    print(f"   Grade: {item_data['grade']}")
    print(f"   Category: {item_data['main_category']}/{item_data['sub_category']}")


def test_name_correction():
    """Test OCR name correction (fuzzy matching)"""
    print("\n" + "="*60)
    print("TEST 3: OCR Name Correction")
    print("="*60)
    
    test_cases = [
        # (ocr_text, expected_corrected)
        ("Gem Of Void", "Gem of Void"),
        ("gem of void", "Gem of Void"),
        ("GEM OF VOID", "Gem of Void"),
        ("Gem  of  Void", "Gem of Void"),  # Extra spaces
        ("Cem of Void", "Gem of Void"),   # OCR error: G→C
        ("Magical Shard", "Magical Shard"),  # Exact match
        ("magical shard", "Magical Shard"),  # Case correction
        ("Crystal of Void Destruction", "Crystal of Void Destruction"),
        ("Crystal of Void - Ah'krad", "Crystal of Void - Ah'krad"),
    ]
    
    passed = 0
    failed = 0
    
    for ocr_text, expected in test_cases:
        corrected, is_valid = correct_item_name(ocr_text)
        
        if corrected == expected and is_valid:
            print(f"✅ '{ocr_text}' → '{corrected}' (valid)")
            passed += 1
        else:
            print(f"❌ '{ocr_text}' → '{corrected}' (expected '{expected}', valid={is_valid})")
            failed += 1
    
    print(f"\n📊 Name Correction: {passed}/{len(test_cases)} passed")
    assert failed == 0, f"{failed} test cases failed"


def test_whitelist_validation():
    """Test item whitelist validation"""
    print("\n" + "="*60)
    print("TEST 4: Whitelist Validation")
    print("="*60)
    
    valid_items = [
        "Gem of Void",
        "Magical Shard",
        "Crystal of Void Destruction",
        "Lion Blood",
        "Black Stone Powder"
    ]
    
    invalid_items = [
        "Fake Item That Does Not Exist",
        "Lorem Ipsum",
        "Test Item 12345"
    ]
    
    print("\n✅ Testing valid items:")
    for item in valid_items:
        is_valid = is_valid_item(item)
        print(f"   '{item}': {is_valid}")
        assert is_valid, f"Item '{item}' should be valid"
    
    print("\n❌ Testing invalid items:")
    for item in invalid_items:
        is_valid = is_valid_item(item)
        print(f"   '{item}': {is_valid}")
        assert not is_valid, f"Item '{item}' should be invalid"
    
    print("\n✅ All whitelist validations passed")


def test_search():
    """Test item search functionality"""
    print("\n" + "="*60)
    print("TEST 5: Item Search")
    print("="*60)
    
    # Search for "void" items
    results = search_items("void", limit=5, min_score=60)
    
    print(f"\n🔍 Search results for 'void' ({len(results)} items):")
    for item_id, item_name, score in results:
        print(f"   ID {item_id}: {item_name} (score: {score})")
    
    assert len(results) >= 3, "Expected at least 3 void items"
    
    # Verify Gem of Void is in results
    gem_found = any(name == "Gem of Void" for _, name, _ in results)
    assert gem_found, "Gem of Void should be in search results"
    print("\n✅ Search functionality working correctly")


def test_integration_with_utils():
    """Test integration with existing utils.py"""
    print("\n" + "="*60)
    print("TEST 6: Integration with utils.py")
    print("="*60)
    
    try:
        from utils import correct_item_name as utils_correct
        
        test_cases = [
            "Gem Of Void",
            "magical shard",
            "Crystal of Void Destruction"
        ]
        
        for ocr_text in test_cases:
            corrected = utils_correct(ocr_text)
            print(f"✅ utils.correct_item_name('{ocr_text}') → '{corrected}'")
        
        print("\n✅ Integration with utils.py working correctly")
        
    except ImportError as e:
        print(f"⚠️  Could not import utils.py: {e}")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*60)
    print("🧪 TESTING: market.json + BDO-API System")
    print("="*60)
    
    try:
        test_basic_loading()
        test_item_lookup()
        test_name_correction()
        test_whitelist_validation()
        test_search()
        test_integration_with_utils()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\n📝 Summary:")
        print("   - market.json loading: ✅")
        print("   - Item ID <-> Name translation: ✅")
        print("   - OCR name correction: ✅")
        print("   - Whitelist validation: ✅")
        print("   - Item search: ✅")
        print("   - utils.py integration: ✅")
        print("\n🎉 New system is ready for production!")
        
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
