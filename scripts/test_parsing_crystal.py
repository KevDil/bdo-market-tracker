"""
Test: Parsing mit exaktem Text aus test_historical_fix
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from parsing import split_text_into_log_entries, extract_details_from_entry

# Exakter OCR-Text aus test_historical_fix.py
ocr_text = """Central Market W Buy Warehouse Balance 78,480,390,882 Manage Warehouse Warehouse Capacity 4,829.6 / 11,000 VT 2025.10.11 23.10 2025.10.11 23.10 2025.10.11 23.07 2025.10.11 23.07 Placed order of Wild Grass x1111 for 8,700,000 Silver Transaction of Wild Grass x1,111 worth 8,943,550 Silver has been completed: Placed order of Sealed Black Magic Crystal x765 for 2,111,400,000 Silver Withdrew order of Sealed Black Magic Crystal x365 for 1,003,750,000 silver Transaction of Sealed Black Magic Crystal x468 worth 1,287,000,000 Silver ha_ Transaction of Crystal of Void Destruction xl worth 1,765,627,500 Silver ' has b: 31.590"""

print("="*80)
print("🔍 PARSING TEST - Crystal of Void Destruction")
print("="*80)

entries = split_text_into_log_entries(ocr_text)

print(f"\n📊 Gefunden: {len(entries)} Einträge\n")

for i, entry_tuple in enumerate(entries, 1):
    pos, ts_text, raw_text = entry_tuple
    print(f"{i}. Timestamp: {ts_text}")
    print(f"   Raw: {raw_text[:80]}...")
    
    ent = extract_details_from_entry(ts_text, raw_text)
    if ent:
        print(f"   ✅ Type={ent.get('type')} Item='{ent.get('item')}' Qty={ent.get('qty')} Price={ent.get('price')}")
    else:
        print(f"   ❌ Parse failed")
    print()

print("="*80)
print("🎯 Looking for: Transaction of Crystal of Void Destruction")
print("="*80)
