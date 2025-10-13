"""
Direct test of parsing.py mit dem exakten OCR-Text aus dem Log
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsing import extract_details_from_entry

# Exakt aus ocr_log.txt Line 2084
ts_text = "2025.10.12 04:04"
entry_text = "Transaction of Magical Shard x200 worth 126,184 Silver has been completed"

print("=" * 80)
print("TEST: Parsing mit OCR-Fehler (fehlende führende Ziffern)")
print("=" * 80)
print(f"Input: {entry_text}")
print()

result = extract_details_from_entry(ts_text, entry_text)

print(f"Result:")
print(f"  type: {result.get('type')}")
print(f"  item: {result.get('item')}")
print(f"  qty: {result.get('qty')}")
print(f"  price: {result.get('price')}")
print(f"  timestamp: {result.get('timestamp')}")

if result.get('qty') == 200 and result.get('price') is None:
    print("\n✅ SUCCESS: Plausibility check worked - price set to None for unrealistically low value")
elif result.get('price') == 126184:
    print("\n❌ FAIL: Plausibility check did NOT work - wrong price kept")
    print(f"   Expected: price=None (for UI fallback)")
    print(f"   Got: price={result.get('price')}")
else:
    print(f"\n⚠️ UNEXPECTED: price={result.get('price')}")
