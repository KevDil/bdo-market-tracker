text = """Central Market Iw Warehouse Balance 60,158,962,383 2025.10.13 21.07 2025.10.13 21.07 2025.10.13 21.07 2025.10.13 21.07 Placed order of Sealed Black Magic Crystal x222 for 597,180,000 Silver Transaction of Sealed Black Magic Crystal x222 worth 599,400,000 Silver has Placed order of Monk's Branch xl,O00 for 22,500,000 Silver QER Transaction of Monk's Branch OO0 worth 22,500,000 Silver has been comple_ Warehouse Capacity 3 9,987.5 / 11,000 VT Sell Pearl Item Selling Limit 31.590 0 / 35 Sell 4B00d Enter a search term: Enter a search term: VT Items Listed 555 Sales Completed 179 Collect AII Magical Shard Registration Count 179 Sales Completed 179 2025 1C-13 21.07 3,140,000 collect Re-list"""

print("="*80)
print("OCR TEXT ANALYSIS - MAGICAL SHARD")
print("="*80)

# Find all lines containing "Transaction"
import re
tx_lines = []
for match in re.finditer(r'Transaction[^\n]*', text, re.IGNORECASE):
    tx_lines.append(match.group(0))

print(f"\nGefundene 'Transaction'-Zeilen: {len(tx_lines)}")
for i, line in enumerate(tx_lines, 1):
    print(f"  {i}. {line}")

# Find Magical Shard context
print("\n" + "="*80)
print("MAGICAL SHARD KONTEXT")
print("="*80)

idx = text.find("Magical Shard")
if idx != -1:
    print(f"\nPosition im Text: {idx}")
    start = max(0, idx - 300)
    end = min(len(text), idx + 300)
    context = text[start:end]
    
    # Highlight Magical Shard
    context_display = context.replace("Magical Shard", ">>> MAGICAL SHARD <<<")
    print(f"\nKontext (300 chars vor/nach):")
    print("-" * 80)
    print(context_display)
    print("-" * 80)
else:
    print("\n❌ 'Magical Shard' NICHT im OCR-Text gefunden!")

# Check for any "sold" or "collected" patterns
print("\n" + "="*80)
print("SUCHE NACH SELL-PATTERNS")
print("="*80)

patterns = [
    (r'sold.*?silver', 'sold...silver'),
    (r'transaction.*?sold', 'transaction...sold'),
    (r'collected.*?silver', 'collected...silver'),
    (r'sales?\s+completed.*?\d+', 'Sales Completed + number')
]

for pattern, desc in patterns:
    matches = list(re.finditer(pattern, text, re.IGNORECASE | re.DOTALL))
    if matches:
        print(f"\n✓ Pattern '{desc}': {len(matches)} Match(es)")
        for m in matches[:3]:  # Show first 3
            snippet = m.group(0)[:100]
            print(f"  - {snippet}")
    else:
        print(f"\n✗ Pattern '{desc}': Keine Matches")

# Check timestamps around Magical Shard
print("\n" + "="*80)
print("TIMESTAMPS IM MAGICAL SHARD BEREICH")
print("="*80)

if idx != -1:
    region = text[max(0, idx-100):min(len(text), idx+200)]
    ts_matches = list(re.finditer(r'20\d{2}[.\-/]\d{2}[.\-/]\d{2}\s+\d{2}[:\-]\d{2}', region))
    if ts_matches:
        print(f"\nGefunden: {len(ts_matches)} Timestamp(s)")
        for m in ts_matches:
            print(f"  - {m.group(0)}")
    else:
        print("\n❌ Keine Timestamps im Magical Shard Bereich gefunden")

# Check for price near Magical Shard
print("\n" + "="*80)
print("PREISE IM MAGICAL SHARD BEREICH")
print("="*80)

if idx != -1:
    region = text[max(0, idx-50):min(len(text), idx+200)]
    price_matches = list(re.finditer(r'\d{1,3}(?:[,\.]\d{3})+', region))
    if price_matches:
        print(f"\nGefunden: {len(price_matches)} Preis(e)")
        for m in price_matches:
            print(f"  - {m.group(0)}")
    else:
        print("\n❌ Keine Preise im Magical Shard Bereich gefunden")

print("\n" + "="*80)
print("FAZIT")
print("="*80)

print("""
Der OCR-Text enthält:
✓ 2x 'Transaction of' Zeilen (Sealed Black Magic Crystal, Monk's Branch)
✓ 'Magical Shard' im UI-Bereich (Registration Count, Sales Completed)
✗ KEINE 'Transaction of Magical Shard' Zeile!

Das bedeutet:
→ Die Transaction-Zeile für Magical Shard ist NICHT im OCR erfasst
→ Entweder war sie außerhalb des sichtbaren Bereichs
→ Oder wurde von anderen UI-Elementen überlagert
→ Oder wurde bereits herausgescrollt

Lösung: Parsing muss aus UI-Metriken rekonstruieren!
""")
