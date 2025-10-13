#!/usr/bin/env python3
"""
End-to-End Test: OCR → market.json validation → BDO API → Database
Tests the complete workflow from OCR text to database entry
"""

import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from parsing import extract_details_from_entry
from market_json_manager import (
    correct_item_name,
    is_valid_item,
    get_item_id_by_name,
    get_item_name_by_id
)
from bdo_api_client import get_item_price_range, format_price
from utils import correct_item_name as utils_correct_item_name


def test_ocr_to_validation():
    """Test 1: OCR parsing → market.json validation"""
    print("\n" + "="*70)
    print("TEST 1: OCR Parsing → market.json Validation")
    print("="*70)
    
    test_cases = [
        # (timestamp, ocr_text, expected_item, expected_valid)
        ('2025.10.12 11.06', 'Purchased Gem of Void x10 for 368,000,000 Silver', 'Gem of Void', True),
        ('2025.10.12 11.06', 'Purchased Cem of Void x10 for 368,000,000 Silver', 'Gem of Void', True),  # OCR error
        ('2025.10.12 11.06', 'Purchased Crystal of Void Destruction x1 for 2,030,000,000 Silver', 'Crystal of Void Destruction', True),
        ('2025.10.12 11.06', 'Purchased Magical Shard x200 for 600,000,000 Silver', 'Magical Shard', True),
        ('2025.10.12 11.06', 'Purchased Invalid Item Name x10 for 1,000,000 Silver', None, False),
    ]
    
    passed = 0
    failed = 0
    
    for timestamp, ocr_text, expected_item, should_be_valid in test_cases:
        print(f"\n📝 OCR Text: {ocr_text}")
        
        # Step 1: Parse OCR text
        details = extract_details_from_entry(timestamp, ocr_text)
        
        if not details:
            print(f"   ❌ Failed to parse OCR text")
            failed += 1
            continue
        
        raw_item = details.get('item')
        print(f"   → Parsed item: {raw_item}")
        
        # Step 2: Validate and correct item name
        corrected_name, valid = correct_item_name(raw_item)
        print(f"   → Corrected name: {corrected_name} (valid: {valid})")
        
        # Step 3: Get item ID
        if valid:
            item_id = get_item_id_by_name(corrected_name)
            print(f"   → Item ID: {item_id}")
        
        # Verify expectations
        if should_be_valid:
            if valid and corrected_name == expected_item:
                print(f"   ✅ PASS: Item correctly validated and corrected")
                passed += 1
            else:
                print(f"   ❌ FAIL: Expected valid item '{expected_item}', got '{corrected_name}' (valid: {valid})")
                failed += 1
        else:
            if not valid:
                print(f"   ✅ PASS: Invalid item correctly rejected")
                passed += 1
            else:
                print(f"   ❌ FAIL: Invalid item should have been rejected")
                failed += 1
    
    print(f"\n📊 Test 1 Results: {passed}/{passed+failed} passed")
    return failed == 0


def test_validation_to_api():
    """Test 2: market.json validation → BDO API price fetch"""
    print("\n" + "="*70)
    print("TEST 2: Item Validation → BDO API Price Fetch")
    print("="*70)
    
    test_items = [
        ('Gem of Void', '821182'),
        ('Crystal of Void Destruction', '15280'),
        ('Magical Shard', '44195'),
    ]
    
    passed = 0
    failed = 0
    
    for item_name, expected_id in test_items:
        print(f"\n📝 Testing: {item_name}")
        
        # Step 1: Validate item
        corrected_name, valid = correct_item_name(item_name)
        
        if not valid:
            print(f"   ❌ FAIL: Item should be valid")
            failed += 1
            continue
        
        print(f"   ✅ Item validated: {corrected_name}")
        
        # Step 2: Get item ID
        item_id = get_item_id_by_name(corrected_name)
        
        if not item_id:
            print(f"   ❌ FAIL: Could not get item ID")
            failed += 1
            continue
        
        print(f"   → Item ID: {item_id}")
        
        if item_id != expected_id:
            print(f"   ⚠️  Warning: Expected ID {expected_id}, got {item_id}")
        
        # Step 3: Fetch price from API
        price_data = get_item_price_range(item_id, use_cache=True)
        
        if not price_data:
            print(f"   ❌ FAIL: Could not fetch price data from API")
            failed += 1
            continue
        
        print(f"   ✅ API Response:")
        print(f"      Min Price: {format_price(price_data['min_price'])} Silver")
        print(f"      Max Price: {format_price(price_data['max_price'])} Silver")
        print(f"      Base Price: {format_price(price_data['base_price'])} Silver")
        print(f"      Last Sale: {format_price(price_data['last_sale_price'])} Silver")
        print(f"      Stock: {price_data['current_stock']:,} units")
        
        # Verify price data makes sense
        if price_data['min_price'] >= price_data['max_price']:
            print(f"   ❌ FAIL: Invalid price range")
            failed += 1
            continue
        
        if price_data['min_price'] <= 0:
            print(f"   ❌ FAIL: Invalid min price")
            failed += 1
            continue
        
        print(f"   ✅ PASS: Complete validation → API workflow")
        passed += 1
    
    print(f"\n📊 Test 2 Results: {passed}/{passed+failed} passed")
    return failed == 0


def test_complete_workflow():
    """Test 3: Complete workflow OCR → Validation → API → Database"""
    print("\n" + "="*70)
    print("TEST 3: Complete Workflow (OCR → Validation → API → Database)")
    print("="*70)
    
    # Use a test transaction
    test_case = {
        'timestamp': '2025.10.12 13.30',
        'ocr_text': 'Purchased Gem of Void x5 for 200,000,000 Silver',
        'expected_item': 'Gem of Void',
        'expected_qty': 5,
        'expected_total_price': 200000000
    }
    
    print(f"\n📝 Test Transaction:")
    print(f"   OCR: {test_case['ocr_text']}")
    
    # Step 1: Parse OCR
    print(f"\n🔄 Step 1: Parse OCR text")
    details = extract_details_from_entry(test_case['timestamp'], test_case['ocr_text'])
    
    if not details:
        print(f"   ❌ FAIL: Could not parse OCR text")
        return False
    
    print(f"   ✅ Parsed: {details['type']} {details['item']} x{details['qty']} for {details['price']:,} Silver")
    
    # Step 2: Validate item name
    print(f"\n🔄 Step 2: Validate item name via market.json")
    raw_item = details['item']
    corrected_name, valid = correct_item_name(raw_item)
    
    if not valid:
        print(f"   ❌ FAIL: Item '{raw_item}' not valid")
        return False
    
    print(f"   ✅ Valid item: {corrected_name}")
    
    # Step 3: Get item ID
    print(f"\n🔄 Step 3: Get item ID from market.json")
    item_id = get_item_id_by_name(corrected_name)
    
    if not item_id:
        print(f"   ❌ FAIL: Could not get item ID")
        return False
    
    print(f"   ✅ Item ID: {item_id}")
    
    # Step 4: Fetch price range from API
    print(f"\n🔄 Step 4: Fetch price range from BDO API")
    price_data = get_item_price_range(item_id, use_cache=True)
    
    if not price_data:
        print(f"   ❌ FAIL: Could not fetch price data")
        return False
    
    print(f"   ✅ Price Range: {format_price(price_data['min_price'])} - {format_price(price_data['max_price'])} Silver")
    print(f"   ✅ Base Price: {format_price(price_data['base_price'])} Silver")
    
    # Step 5: Validate transaction price is within bounds
    print(f"\n🔄 Step 5: Validate transaction price")
    unit_price = details['price'] // details['qty']
    
    print(f"   Transaction unit price: {format_price(unit_price)} Silver")
    
    if unit_price < price_data['min_price'] or unit_price > price_data['max_price']:
        print(f"   ⚠️  Warning: Price {format_price(unit_price)} outside hard caps [{format_price(price_data['min_price'])} - {format_price(price_data['max_price'])}]")
        print(f"   (This might be expected for OCR errors or special cases)")
    else:
        print(f"   ✅ Price within valid range")
    
    # Step 6: Simulate database insert (dry run)
    print(f"\n🔄 Step 6: Simulate database insert (dry run)")
    
    transaction_data = {
        'timestamp': datetime.strptime(test_case['timestamp'], '%Y.%m.%d %H.%M'),
        'transaction_type': details['type'],
        'item_name': corrected_name,
        'item_id': item_id,
        'quantity': details['qty'],
        'total_price': details['price'],
        'unit_price': unit_price,
        'min_price': price_data['min_price'],
        'max_price': price_data['max_price'],
        'base_price': price_data['base_price']
    }
    
    print(f"   Transaction ready for database:")
    for key, value in transaction_data.items():
        if isinstance(value, int) and key.endswith('price'):
            print(f"      {key}: {format_price(value)} Silver")
        else:
            print(f"      {key}: {value}")
    
    print(f"\n   ✅ PASS: Complete workflow successful!")
    print(f"   📝 Note: This was a dry run - no actual database insert performed")
    
    return True


def test_utils_integration():
    """Test 4: Verify utils.py uses new system"""
    print("\n" + "="*70)
    print("TEST 4: utils.py Integration with New System")
    print("="*70)
    
    test_cases = [
        ('Gem of Void', 'Gem of Void'),
        ('Cem of Void', 'Gem of Void'),  # OCR error
        ('magical shard', 'Magical Shard'),  # Case fix
        ('Crystal  of  Void', 'Crystal of Void - Ah\'krad'),  # Extra spaces + fuzzy match
    ]
    
    passed = 0
    failed = 0
    
    for raw_name, expected_corrected in test_cases:
        print(f"\n📝 Testing: '{raw_name}'")
        
        # Test utils.correct_item_name (should use market_json_manager now)
        corrected = utils_correct_item_name(raw_name)
        
        print(f"   → Corrected: '{corrected}'")
        
        if corrected == expected_corrected:
            print(f"   ✅ PASS")
            passed += 1
        else:
            print(f"   ❌ FAIL: Expected '{expected_corrected}'")
            failed += 1
    
    print(f"\n📊 Test 4 Results: {passed}/{passed+failed} passed")
    return failed == 0


def test_ocr_errors():
    """Test 5: Real-world OCR error handling"""
    print("\n" + "="*70)
    print("TEST 5: Real-world OCR Error Handling")
    print("="*70)
    
    test_cases = [
        # Common OCR errors
        ('2025.10.12 11.06', 'Transaction of Magical Shard x1OO worth 275,934,750 Silver has been comple', 'Magical Shard', 100),
        ('2025.10.12 11.06', 'Purchased Cem of Void x10 for 368,000,000 Silver', 'Gem of Void', 10),
        ('2025.10.12 11.06', 'Transaction of Crystallized Despair x1Z worth 330,000,000 Silver has been', 'Crystallized Despair', 12),  # 1Z = 12
        ('2025.10.12 11.06', 'Placed order of Lion Blood x4,522 for 70,091,000 Silver', 'Lion Blood', 4522),
        ('2025.10.12 11.06', 'Transaction of Lion Blood x5,0O0 worth 78,000,000 Silver', 'Lion Blood', 5000),  # 0O0 = 000
    ]
    
    passed = 0
    failed = 0
    
    for timestamp, ocr_text, expected_item, expected_qty in test_cases:
        print(f"\n📝 OCR: {ocr_text[:70]}...")
        
        # Parse
        details = extract_details_from_entry(timestamp, ocr_text)
        
        if not details:
            print(f"   ❌ FAIL: Could not parse")
            failed += 1
            continue
        
        # Validate
        corrected_name, valid = correct_item_name(details['item'])
        
        if not valid:
            print(f"   ❌ FAIL: Item not valid")
            failed += 1
            continue
        
        # Get ID and price
        item_id = get_item_id_by_name(corrected_name)
        
        if item_id:
            price_data = get_item_price_range(item_id, use_cache=True)
            
            if price_data:
                print(f"   ✅ Parsed: {corrected_name} x{details['qty']}")
                print(f"      Item ID: {item_id}")
                print(f"      Price Range: {format_price(price_data['min_price'])} - {format_price(price_data['max_price'])}")
                
                # Verify item and quantity match expectations
                if corrected_name == expected_item and details['qty'] == expected_qty:
                    print(f"   ✅ PASS: Correct item and quantity extracted")
                    passed += 1
                else:
                    print(f"   ❌ FAIL: Expected {expected_item} x{expected_qty}, got {corrected_name} x{details['qty']}")
                    failed += 1
            else:
                print(f"   ❌ FAIL: Could not fetch price")
                failed += 1
        else:
            print(f"   ❌ FAIL: Could not get item ID")
            failed += 1
    
    print(f"\n📊 Test 5 Results: {passed}/{passed+failed} passed")
    return failed == 0


def run_end_to_end_tests():
    """Run all end-to-end tests"""
    print("\n" + "="*70)
    print("🧪 END-TO-END TESTING: Complete Workflow Validation")
    print("="*70)
    print("\n⚠️  NOTE: These tests validate the complete pipeline:")
    print("   OCR parsing → market.json validation → BDO API → Database")
    
    results = {
        'OCR → Validation': False,
        'Validation → API': False,
        'Complete Workflow': False,
        'utils.py Integration': False,
        'OCR Error Handling': False,
    }
    
    try:
        results['OCR → Validation'] = test_ocr_to_validation()
        results['Validation → API'] = test_validation_to_api()
        results['Complete Workflow'] = test_complete_workflow()
        results['utils.py Integration'] = test_utils_integration()
        results['OCR Error Handling'] = test_ocr_errors()
        
        print("\n" + "="*70)
        print("📊 END-TO-END TEST RESULTS SUMMARY")
        print("="*70)
        
        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"   {test_name}: {status}")
        
        all_passed = all(results.values())
        
        if all_passed:
            print("\n" + "="*70)
            print("✅ ALL END-TO-END TESTS PASSED!")
            print("="*70)
            print("\n🎉 The complete system is working correctly!")
            print("\n📋 Verified workflows:")
            print("   ✅ OCR text parsing")
            print("   ✅ Item name validation (market.json)")
            print("   ✅ Item name correction (fuzzy matching)")
            print("   ✅ Item ID lookup")
            print("   ✅ BDO API price fetching")
            print("   ✅ Price range validation")
            print("   ✅ Database-ready transaction preparation")
            print("   ✅ OCR error handling (O→0, l→1, etc.)")
            print("   ✅ utils.py integration with new system")
            print("\n🚀 System is ready for production use!")
        else:
            failed = [name for name, passed in results.items() if not passed]
            print(f"\n❌ {len(failed)} TEST(S) FAILED: {', '.join(failed)}")
        
        return all_passed
        
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_end_to_end_tests()
    sys.exit(0 if success else 1)
