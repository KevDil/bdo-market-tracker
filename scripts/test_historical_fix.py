"""
Test: Simulation mit exaktem OCR-Text aus dem ersten Scan
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass

from tracker import MarketTracker
import datetime

# Exakter OCR-Text vom 23:10:43 Scan (aus ocr_log.txt)
ocr_text = """Central Market W Buy Warehouse Balance 78,480,390,882 Manage Warehouse Warehouse Capacity 4,829.6 / 11,000 VT 2025.10.11 23.10 2025.10.11 23.10 2025.10.11 23.07 2025.10.11 23.07 Placed order of Wild Grass x1111 for 8,700,000 Silver Transaction of Wild Grass x1,111 worth 8,943,550 Silver has been completed: Placed order of Sealed Black Magic Crystal x765 for 2,111,400,000 Silver Withdrew order of Sealed Black Magic Crystal x365 for 1,003,750,000 silver Transaction of Sealed Black Magic Crystal x468 worth 1,287,000,000 Silver ha_ Transaction of Crystal of Void Destruction xl worth 1,765,627,500 Silver ' has b: 31.590"""

print("="*80)
print("🧪 INTEGRATION TEST - Historical Transactions")
print("="*80)

print("\n📝 Scenario:")
print("   - User öffnet Marktfenster (buy_overview)")
print("   - Sichtbar:")
print("     1. Wild Grass x1111 @ 23:10 (FRESH - gerade gekauft)")
print("     2. Sealed Black Magic Crystal x468 @ 23:07 (HISTORICAL)")
print("     3. Crystal of Void Destruction x1 @ 23:07 (HISTORICAL)")

print("\n🎯 Erwartung:")
print("   ✅ Alle 3 Transaktionen sollten gespeichert werden!")

print("\n" + "="*80)
print("📸 Processing OCR text...")
print("="*80)

mt = MarketTracker(debug=True)
mt.process_ocr_text(ocr_text)

print("\n" + "="*80)
print("📊 Checking database...")
print("="*80)

from database import get_cursor
cur = get_cursor()
cur.execute("SELECT item_name, quantity, price, transaction_type, timestamp, tx_case FROM transactions ORDER BY timestamp DESC")
rows = cur.fetchall()

print(f"\n✅ Database has {len(rows)} transaction(s):\n")
for row in rows:
    item, qty, price, ttype, ts, case = row
    print(f"   {ttype.upper():4} | {item:30} | x{qty:4} | {price:15,} Silver | {ts} | {case}")

print("\n" + "="*80)
print("💡 RESULT:")
print("="*80)

expected = {
    ('wild grass', 1111, 8943550),
    ('sealed black magic crystal', 468, 1287000000),
    ('crystal of void destruction', 1, 1765627500)
}

found = {(row[0].lower(), row[1], row[2]) for row in rows}

if expected == found:
    print("✅ SUCCESS: All 3 transactions saved correctly!")
else:
    print("❌ FAIL: Missing or incorrect transactions!")
    print(f"   Expected: {expected}")
    print(f"   Found: {found}")
    missing = expected - found
    if missing:
        print(f"   Missing: {missing}")

print("="*80)
