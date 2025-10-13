"""
Quick smoke test with the exact OCR text from ocr_log.txt
to verify the fix handles the real-world case.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from parsing import split_text_into_log_entries, extract_details_from_entry

# Exact OCR text from ocr_log.txt (line 102)
ocr_text = """Central Market Warehouse Balance @ 69,102,595,302 Buy 2025.10.12 04.04 2025.10.12 04.04 2025.10.12 04.04 2025.10.12 04.04 Placed order of Trace of Nature x5,000 for 770,000,000 Silver Transaction of Trace of Nature X5,O00 worth 765,000,000 Silver has been com__. Listed Magical Shard x2OO for 662,000,000 Silver: The price of enhancement m_ Transaction of Magical Shard x2OO worth 585, 585, OO0 Silver has been complet__. Warehouse Capacity 5,051.0 / 11,000 VT 31.590 Sell Pearl Item Selling Limit Sell 386 Enter a search term Enter a search term: Items Listed 556 Sales Completed   200 Collect AI VT Magical Shard Registration Count : 200 / Sales Completed 200 2025 1C-12 04.04 3,310,000 Collect Re-list"""

print("=" * 80)
print("SMOKE TEST: Exact OCR Text from ocr_log.txt")
print("=" * 80)
print("\nOCR Text:")
print(ocr_text[:200] + "...")
print("\n" + "=" * 80)

# Split into entries
entries = split_text_into_log_entries(ocr_text)
print(f"\nFound {len(entries)} log entries\n")

# Extract details from each entry
for i, (pos, ts_text, entry_text) in enumerate(entries, 1):
    details = extract_details_from_entry(ts_text, entry_text)
    
    item = details.get('item', 'None')
    qty = details.get('qty', 'None')
    price = details.get('price', 'None')
    typ = details.get('type', 'other')
    
    print(f"Entry {i}:")
    print(f"  Type: {typ}")
    print(f"  Item: {item}")
    print(f"  Qty: {qty}")
    print(f"  Price: {price:,}" if isinstance(price, int) else f"  Price: {price}")
    
    # Check if this is the Magical Shard transaction we care about
    if item == "Magical Shard" and typ == "transaction" and qty == 200:
        if price == 585585000:
            print("  ✅ SUCCESS: Magical Shard transaction parsed correctly!")
            print(f"     Expected: 585,585,000")
            print(f"     Got:      {price:,}")
        else:
            print(f"  ❌ FAILED: Expected price 585,585,000, got {price}")
    
    print()

print("=" * 80)
print("✅ Smoke test complete - check Magical Shard transaction above")
print("=" * 80)
