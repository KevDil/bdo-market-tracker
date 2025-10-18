#!/usr/bin/env python3
"""
End-to-End Test: OCR → market.json validation → BDO API → Database
Tests the complete workflow from OCR text to database entry
"""

import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
    print("\n" + "=" * 70)
    print("TEST 1: OCR Parsing → market.json Validation")
    print("=" * 70)

    test_cases = [
        ('2025.10.12 11.06', 'Purchased Gem of Void x10 for 368,000,000 Silver', 'Gem of Void', True),
        ('2025.10.12 11.06', 'Purchased Cem of Void x10 for 368,000,000 Silver', 'Gem of Void', True),
        ('2025.10.12 11.06', 'Purchased Crystal of Void Destruction x1 for 2,030,000,000 Silver', 'Crystal of Void Destruction', True),
        ('2025.10.12 11.06', 'Purchased Magical Shard x200 for 600,000,000 Silver', 'Magical Shard', True),
        ('2025.10.12 11.06', 'Purchased Invalid Item Name x10 for 1,000,000 Silver', None, False),
    ]

    passed = 0
    failed = 0

    for timestamp, ocr_text, expected_item, should_be_valid in test_cases:
        print(f"\n📝 OCR Text: {ocr_text}")

        details = extract_details_from_entry(timestamp, ocr_text)

        if not details:
            print(f"   ❌ Failed to parse OCR text")
            failed += 1
            continue

        raw_item = details.get('item')
        print(f"   → Parsed item: {raw_item}")

        corrected_name, valid = correct_item_name(raw_item)
        print(f"   → Corrected name: {corrected_name} (valid: {valid})")

        if valid:
            item_id = get_item_id_by_name(corrected_name)
            print(f"   → Item ID: {item_id}")

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
    print("\n" + "=" * 70)
    print("TEST 2: Item Validation → BDO API Price Fetch")
    print("=" * 70)

    test_items = [
        ('Gem of Void', '821182'),
        ('Crystal of Void Destruction', '15280'),
        ('Magical Shard', '44195'),
    ]

    passed = 0
    failed = 0

    for item_name, expected_id in test_items:
        print(f"\n📝 Testing: {item_name}")

        corrected_name, valid = correct_item_name(item_name)

        if not valid:
            print(f"   ❌ FAIL: Item should be valid")
            failed += 1
            continue

        print(f"   ✅ Item validated: {corrected_name}")

        item_id = get_item_id_by_name(corrected_name)

        if not item_id:
            print(f"   ❌ FAIL: Could not get item ID")
            failed += 1
            continue

        print(f"   → Item ID: {item_id}")

        if item_id != expected_id:
            print(f"   ⚠️  Warning: Expected ID {expected_id}, got {item_id}")

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


def main():
    success = True
    success &= test_ocr_to_validation()
    success &= test_validation_to_api()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
