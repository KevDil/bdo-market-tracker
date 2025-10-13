"""
Test: Historical Transaction Detection mit Item-Kategorien

Testet verschiedene Szenarien:
1. Transaction ohne Kontext + most_likely_buy → Save als BUY
2. Transaction ohne Kontext + most_likely_sell → Skip auf buy_overview (wrong context)
3. Transaction ohne Kontext + unknown item → Skip (ambiguous)
4. Transaction MIT Kontext (Placed+Withdrew) → Save unabhängig von Kategorie
"""
import sys

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

sys.path.insert(0, "c:\\Users\\kdill\\Desktop\\market_tracker")

from tracker import MarketTracker
from database import get_connection

print("🧪 Test: Historical Transaction Detection V2 (Item Categories)\n")
print("="*80)

# Clean up test data
conn = get_connection()
cur = conn.cursor()
cur.execute("DELETE FROM transactions WHERE timestamp >= '2025-10-11 20:00:00'")
conn.commit()

# -------------------------------------------------------------------
# Scenario 1: Birch Sap (most_likely_buy) - Transaction only
# Expected: SAVE als BUY (Category match)
# -------------------------------------------------------------------
print("\n📸 SCENARIO 1: Birch Sap (most_likely_buy) - Transaction only")
print("-"*80)

tracker = MarketTracker(debug=True)
ocr_1 = """Central Market Buy 2025.10.11 20.10 Transaction of Birch Sap x500 worth 6,000,000 Silver has been completed Orders Completed Collect"""

tracker.process_ocr_text(ocr_1)

cur.execute("SELECT * FROM transactions WHERE item_name='Birch Sap' AND timestamp >= '2025-10-11 20:00:00'")
results = cur.fetchall()
print(f"\n✅ Expected: 1 transaction (BUY)")
print(f"✅ Actual: {len(results)} transaction(s)")
if len(results) == 1 and results[0][4] == 'buy':
    print("✅ PASS: Birch Sap saved as BUY (category match)")
else:
    print("❌ FAIL: Expected 1 BUY transaction")

# -------------------------------------------------------------------
# Scenario 2: Magical Shard (most_likely_sell) on buy_overview
# Expected: SKIP (wrong context)
# -------------------------------------------------------------------
print("\n📸 SCENARIO 2: Magical Shard (most_likely_sell) on buy_overview")
print("-"*80)

tracker2 = MarketTracker(debug=True)  # Fresh tracker to avoid baseline conflicts
ocr_2 = """Central Market Buy 2025.10.11 20.15 Transaction of Magical Shard x100 worth 300,000,000 Silver has been completed Orders Completed Collect"""

tracker2.process_ocr_text(ocr_2)

cur.execute("SELECT * FROM transactions WHERE item_name='Magical Shard' AND timestamp >= '2025-10-11 20:00:00'")
results = cur.fetchall()
print(f"\n✅ Expected: 0 transactions (wrong context - sell item on buy overview)")
print(f"✅ Actual: {len(results)} transaction(s)")
if len(results) == 0:
    print("✅ PASS: Magical Shard skipped on buy_overview (most_likely_sell)")
else:
    print("❌ FAIL: Expected 0 transactions")

# -------------------------------------------------------------------
# Scenario 3: Unknown item (not in category list)
# Expected: SKIP (ambiguous)
# -------------------------------------------------------------------
print("\n📸 SCENARIO 3: Unknown Item (not in category list)")
print("-"*80)

tracker3 = MarketTracker(debug=True)  # Fresh tracker
ocr_3 = """Central Market Buy 2025.10.11 20.20 Transaction of Unknown Mystery Item x10 worth 50,000,000 Silver has been completed Orders Completed Collect"""

tracker3.process_ocr_text(ocr_3)

cur.execute("SELECT * FROM transactions WHERE item_name='Unknown Mystery Item' AND timestamp >= '2025-10-11 20:00:00'")
results = cur.fetchall()
print(f"\n✅ Expected: 0 transactions (ambiguous - no category)")
print(f"✅ Actual: {len(results)} transaction(s)")
if len(results) == 0:
    print("✅ PASS: Unknown item skipped (no category match)")
else:
    print("❌ FAIL: Expected 0 transactions")

# -------------------------------------------------------------------
# Scenario 4: Pine Sap WITH context (Placed+Withdrew+Transaction)
# Expected: SAVE (full context, no category needed)
# Note: Using Pine Sap instead of Birch Sap to avoid baseline conflicts
# -------------------------------------------------------------------
print("\n📸 SCENARIO 4: Pine Sap WITH full context (Placed+Withdrew+Transaction)")
print("-"*80)

tracker4 = MarketTracker(debug=True)  # Fresh tracker
ocr_4 = """Central Market Buy 2025.10.11 20.25 2025.10.11 20.25 2025.10.11 20.25 Placed order of Pine Sap x1000 for 12,000,000 Silver Withdrew order of Pine Sap x500 for 6,000,000 Silver Transaction of Pine Sap x500 worth 6,000,000 Silver has been completed Orders Completed Collect"""

tracker4.process_ocr_text(ocr_4)

cur.execute("SELECT * FROM transactions WHERE item_name='Pine Sap' AND timestamp >= '2025-10-11 20:25:00'")
results = cur.fetchall()
print(f"\n✅ Expected: 1 transaction (BUY with full context)")
print(f"✅ Actual: {len(results)} transaction(s)")
if len(results) == 1 and results[0][4] == 'buy':
    print("✅ PASS: Pine Sap saved as BUY (full context)")
else:
    print("❌ FAIL: Expected 1 BUY transaction")

# -------------------------------------------------------------------
# Scenario 5: Magical Shard (most_likely_sell) on sell_overview
# Expected: SAVE als SELL (correct context)
# -------------------------------------------------------------------
print("\n📸 SCENARIO 5: Magical Shard (most_likely_sell) on sell_overview")
print("-"*80)

tracker5 = MarketTracker(debug=True)  # Fresh tracker
ocr_5 = """Central Market Sell 2025.10.11 20.30 Transaction of Magical Shard x100 worth 286,581,750 Silver has been completed Sales Completed Collect"""

tracker5.process_ocr_text(ocr_5)

cur.execute("SELECT * FROM transactions WHERE item_name='Magical Shard' AND timestamp >= '2025-10-11 20:30:00'")
results = cur.fetchall()
print(f"\n✅ Expected: 1 transaction (SELL)")
print(f"✅ Actual: {len(results)} transaction(s)")
if len(results) == 1 and results[0][4] == 'sell':
    print("✅ PASS: Magical Shard saved as SELL (category match on correct tab)")
else:
    print("❌ FAIL: Expected 1 SELL transaction")

# -------------------------------------------------------------------
# Final Summary
# -------------------------------------------------------------------
print("\n" + "="*80)
print("📊 FINAL SUMMARY")
print("="*80)

cur.execute("SELECT * FROM transactions WHERE timestamp >= '2025-10-11 20:00:00' ORDER BY timestamp")
all_results = cur.fetchall()

print(f"\nTotal transactions saved: {len(all_results)}")
print("\nDetails:")
for row in all_results:
    print(f"   {row[4].upper():4s} | {row[1]:25s} | x{row[2]:<5d} | {row[3]:>13,.0f} Silver | {row[5]}")

print("\n" + "="*80)
print("✅ Test complete! Expected: 3 transactions (Scenario 1, 4, 5)")
print("="*80)
