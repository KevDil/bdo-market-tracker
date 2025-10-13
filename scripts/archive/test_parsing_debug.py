"""
Test Parsing mit exaktem OCR-Text vom Calibration Tool
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from parsing import split_text_into_log_entries

# Exakter OCR-Text vom Calibration Tool
ocr_text = """Central Market W Buy Warehouse Balance 78,480,390,882 Manage Warehouse Warehouse Capacity 4,829.6 / 11,000 VT 2025.10.11 23.07 2025.10.11 23.07 2025.10.11 23.07 2025.10.11 23.07 Placed order of Sealed Black Magic Crystal x765 for 2,111,400,000 Silver Withdrew order of Sealed Black Magic Crystal x365 for ,003,750,000 silver Transaction of Sealed Black Magic Crystal x468 worth 1,287,000,000 Silver ha_ Transaction of Crystal of Void Destruction xl worth 1,765,627,500 Silver ' has b: 31.590 Sell Pea"""

print("="*80)
print("🧪 PARSING TEST")
print("="*80)

print(f"\n📝 OCR Text ({len(ocr_text)} chars):")
print("-"*80)
print(ocr_text)
print("-"*80)

print(f"\n🔍 Parsing...")
entries = split_text_into_log_entries(ocr_text)

print(f"\n📊 Gefunden: {len(entries)} Einträge")
print("="*80)

for i, entry_tuple in enumerate(entries, 1):
    print(f"\n{i}. Entry (raw):")
    
    # Parse based on length - split_text_into_log_entries returns (pos, ts_text, raw_text)
    if len(entry_tuple) == 3:
        pos, ts_text, raw_text = entry_tuple
    elif len(entry_tuple) == 2:
        ts_text, raw_text = entry_tuple
    else:
        print(f"   ❌ Unexpected tuple length: {len(entry_tuple)}")
        continue
        
    print(f"   Timestamp: {ts_text}")
    print(f"   Raw: {raw_text[:150]}...")
    
    # Parse it
    from parsing import extract_details_from_entry
    ent = extract_details_from_entry(ts_text, raw_text)
    if ent:
        print(f"   ✅ Parsed:")
        print(f"      Type: {ent.get('type', 'N/A')}")
        print(f"      Item: {ent.get('item', 'N/A')}")
        print(f"      Qty: {ent.get('qty', 'N/A')}")
        print(f"      Price: {ent.get('price', 'N/A')}")
    else:
        print(f"   ❌ Parse failed")

print("\n" + "="*80)
print("💡 ERWARTUNG:")
print("="*80)
print("1. Placed order - Sealed Black Magic Crystal x765 for 2,111,400,000")
print("2. Withdrew - Sealed Black Magic Crystal x365 for 1,003,750,000")
print("3. Transaction - Sealed Black Magic Crystal x468 worth 1,287,000,000")
print("4. Transaction - Crystal of Void Destruction x1 worth 1,765,627,500")
print("="*80)
