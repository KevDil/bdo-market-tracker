"""
Test für Preis-Plausibilitätsprüfung bei unrealistisch niedrigen Preisen
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsing import extract_details_from_entry

# Test Cases
test_cases = [
    {
        "name": "Korrekter Preis (585M Silver)",
        "ts": "2025-10-12 04:04:00",
        "text": "Transaction of Magical Shard x200 worth 585,585,000 Silver has been completed",
        "expected_price": 585585000
    },
    {
        "name": "OCR-Fehler: Fehlende führende Ziffern (126K statt 585M)",
        "ts": "2025-10-12 04:04:00",
        "text": "Transaction of Magical Shard x200 worth 126,184 Silver has been completed",
        "expected_price": None  # Should be marked as invalid
    },
    {
        "name": "Legitim niedriger Preis bei kleiner Menge (10x für 500K)",
        "ts": "2025-10-12 04:04:00",
        "text": "Transaction of Black Stone Powder x5 worth 23,500 Silver has been completed",
        "expected_price": 23500  # Small qty, low price is OK
    },
    {
        "name": "Hoher Preis bei hoher Menge (5000x für 765M)",
        "ts": "2025-10-12 04:04:00",
        "text": "Transaction of Trace of Nature x5000 worth 765,000,000 Silver has been completed",
        "expected_price": 765000000
    },
]

print("=" * 80)
print("TEST: Preis-Plausibilitätsprüfung")
print("=" * 80)

passed = 0
failed = 0

for test in test_cases:
    print(f"\nTest: {test['name']}")
    print(f"  Input: {test['text'][:80]}...")
    
    result = extract_details_from_entry(test['ts'], test['text'])
    
    actual_price = result.get('price')
    expected_price = test['expected_price']
    
    if actual_price == expected_price:
        print(f"  ✅ PASS: price={actual_price}")
        passed += 1
    else:
        print(f"  ❌ FAIL: Expected price={expected_price}, got price={actual_price}")
        print(f"     Full result: {result}")
        failed += 1

print("\n" + "=" * 80)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 80)
