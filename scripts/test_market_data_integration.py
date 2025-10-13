"""
Test: Market Data Integration & Price Plausibility Check
Tests the new market_data.csv integration with min/max price validation
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import _load_market_data, check_price_plausibility
from parsing import extract_details_from_entry

print("=" * 80)
print("TEST 1: Market Data Loader")
print("=" * 80)

market_data = _load_market_data()
print(f"Loaded {len(market_data)} items from market_data.csv")

# Test specific items
test_items = ["Magical Shard", "Black Stone Powder", "Trace of Nature", "Lion Blood"]
for item in test_items:
    if item in market_data:
        data = market_data[item]
        print(f"  {item}: Min={data['min_price']:,}, Max={data['max_price']:,}")
    else:
        print(f"  {item}: NOT FOUND")

print("\n" + "=" * 80)
print("TEST 2: Price Plausibility Check")
print("=" * 80)

# Test cases
test_cases = [
    {
        "name": "Magical Shard - Korrekt (585M für 200x)",
        "item": "Magical Shard",
        "qty": 200,
        "price": 585585000,
        "expected_plausible": True
    },
    {
        "name": "Magical Shard - OCR-Fehler (126K für 200x)",
        "item": "Magical Shard",
        "qty": 200,
        "price": 126184,
        "expected_plausible": False
    },
    {
        "name": "Black Stone Powder - Niedrig aber OK (23.5K für 5x)",
        "item": "Black Stone Powder",
        "qty": 5,
        "price": 23500,
        "expected_plausible": True
    },
    {
        "name": "Trace of Nature - Hoch (765M für 5000x)",
        "item": "Trace of Nature",
        "qty": 5000,
        "price": 765000000,
        "expected_plausible": True
    },
    {
        "name": "Lion Blood - Realistisch (7.4M für 478x)",
        "item": "Lion Blood",
        "qty": 478,
        "price": 7409000,
        "expected_plausible": True
    },
]

passed = 0
failed = 0

for test in test_cases:
    print(f"\nTest: {test['name']}")
    result = check_price_plausibility(test['item'], test['qty'], test['price'])
    
    plausible = result['plausible']
    unit_price = result.get('unit_price', 0)
    reason = result.get('reason', 'unknown')
    expected_min = result.get('expected_min')
    expected_max = result.get('expected_max')
    
    print(f"  Input: {test['qty']}x {test['item']} = {test['price']:,} Silver")
    print(f"  Unit Price: {unit_price:,.0f} Silver")
    if expected_min and expected_max:
        print(f"  Expected Range: {expected_min:,} - {expected_max:,} Silver")
    print(f"  Result: {'✅ Plausible' if plausible else '❌ Implausible'} ({reason})")
    
    if plausible == test['expected_plausible']:
        print(f"  ✅ PASS")
        passed += 1
    else:
        print(f"  ❌ FAIL: Expected {'plausible' if test['expected_plausible'] else 'implausible'}")
        failed += 1

print("\n" + "=" * 80)
print("TEST 3: Parsing Integration")
print("=" * 80)

# Test parsing mit market data validation
parsing_tests = [
    {
        "name": "Magical Shard - Korrekt",
        "ts": "2025-10-12 04:04",
        "text": "Transaction of Magical Shard x200 worth 585,585,000 Silver has been completed",
        "expected_price": 585585000
    },
    {
        "name": "Magical Shard - OCR-Fehler (sollte None werden)",
        "ts": "2025-10-12 04:04",
        "text": "Transaction of Magical Shard x200 worth 126,184 Silver has been completed",
        "expected_price": None
    },
    {
        "name": "Black Stone Powder - Niedrig aber OK",
        "ts": "2025-10-12 04:04",
        "text": "Transaction of Black Stone Powder x5 worth 23,500 Silver has been completed",
        "expected_price": 23500
    },
]

for test in parsing_tests:
    print(f"\nTest: {test['name']}")
    print(f"  Input: {test['text'][:80]}...")
    
    result = extract_details_from_entry(test['ts'], test['text'])
    actual_price = result.get('price')
    
    if actual_price == test['expected_price']:
        print(f"  ✅ PASS: price={actual_price}")
        passed += 1
    else:
        print(f"  ❌ FAIL: Expected price={test['expected_price']}, got price={actual_price}")
        print(f"     Full result: {result}")
        failed += 1

print("\n" + "=" * 80)
print(f"FINAL RESULTS: {passed} passed, {failed} failed")
print("=" * 80)
