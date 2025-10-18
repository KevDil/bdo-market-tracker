#!/usr/bin/env python3
"""
Manual smoke tests for the market.json + BDO API integration.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_json_manager import (
    load_market_json,
    get_item_by_id,
    get_item_id_by_name,
    get_item_name_by_id,
    correct_item_name,
    is_valid_item,
    search_items,
    get_item_count,
)


def test_basic_loading():
    print("\n" + "=" * 60)
    print("TEST 1: Basic Loading")
    print("=" * 60)
    load_market_json()
    count = get_item_count()
    print(f"✅ Loaded {count} items from market.json")
    assert count > 4000, f"Expected >4000 items, got {count}"


def test_item_lookup():
    print("\n" + "=" * 60)
    print("TEST 2: Item ID <-> Name Translation")
    print("=" * 60)
    item_id = "821182"
    item_name = get_item_name_by_id(item_id)
    print(f"✅ ID {item_id} → Name: {item_name}")
    assert item_name == "Gem of Void"

    found_id = get_item_id_by_name("Gem of Void")
    print(f"✅ Name 'Gem of Void' → ID: {found_id}")
    assert found_id == item_id

    item_data = get_item_by_id(item_id)
    print(f"✅ Full data for ID {item_id}: {item_data}")


def test_name_correction():
    print("\n" + "=" * 60)
    print("TEST 3: OCR Name Correction")
    print("=" * 60)
    test_cases = [
        ("Gem Of Void", "Gem of Void"),
        ("gem of void", "Gem of Void"),
        ("GEM OF VOID", "Gem of Void"),
        ("Gem  of  Void", "Gem of Void"),
        ("Cem of Void", "Gem of Void"),
        ("Magical Shard", "Magical Shard"),
        ("magical shard", "Magical Shard"),
        ("Crystal of Void Destruction", "Crystal of Void Destruction"),
        ("Crystal of Void - Ah'krad", "Crystal of Void - Ah'krad"),
    ]
    for ocr_text, expected in test_cases:
        corrected, is_valid = correct_item_name(ocr_text)
        print(f"✅ '{ocr_text}' → '{corrected}' (valid={is_valid})")
        assert corrected == expected and is_valid


def test_whitelist_validation():
    print("\n" + "=" * 60)
    print("TEST 4: Whitelist Validation")
    print("=" * 60)
    valid_items = [
        "Gem of Void",
        "Magical Shard",
        "Crystal of Void Destruction",
        "Lion Blood",
        "Black Stone Powder",
    ]
    invalid_items = [
        "Fake Item That Does Not Exist",
        "Lorem Ipsum",
        "Test Item 12345",
    ]
    for item in valid_items:
        assert is_valid_item(item)
    for item in invalid_items:
        assert not is_valid_item(item)


def test_search():
    print("\n" + "=" * 60)
    print("TEST 5: Item Search")
    print("=" * 60)
    results = search_items("void", limit=5, min_score=60)
    print(f"🔍 Results: {results}")
    assert len(results) >= 3
    assert any(name == "Gem of Void" for _, name, _ in results)


def run_all_tests():
    print("\n" + "=" * 60)
    print("🧪 TESTING: market.json + BDO-API System")
    print("=" * 60)
    try:
        test_basic_loading()
        test_item_lookup()
        test_name_correction()
        test_whitelist_validation()
        test_search()
        print("\n✅ ALL TESTS PASSED!")
        return True
    except AssertionError as exc:
        print(f"\n❌ TEST FAILED: {exc}")
        return False
    except Exception as exc:
        print(f"\n❌ UNEXPECTED ERROR: {exc}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
