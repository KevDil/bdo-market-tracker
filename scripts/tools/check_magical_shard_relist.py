"""Check Magical Shard relist test results."""
import sqlite3
from datetime import datetime

db = sqlite3.connect('bdo_tracker.db')
cursor = db.cursor()

print("=" * 80)
print("MAGICAL SHARD RELIST TEST - DATABASE STATE")
print("=" * 80)

# Check listings
print("\nLISTINGS:")
cursor.execute("""
    SELECT id, item_name, quantity, price, status, created_at, collected_at
    FROM listings
    WHERE item_name LIKE '%Magical Shard%'
    ORDER BY id DESC
    LIMIT 5
""")
for row in cursor.fetchall():
    id, item, qty, price, status, created, collected = row
    print(f"  ID={id}: {qty}x @ {price:,} Silver")
    print(f"    Status: {status}")
    print(f"    Created: {created}")
    print(f"    Collected: {collected}")
    print()

# Check transactions
print("\nTRANSACTIONS (Latest 3):")
cursor.execute("""
    SELECT id, item_name, quantity, silver_each, silver_total, type, case, timestamp
    FROM transactions
    WHERE item_name LIKE '%Magical Shard%'
    ORDER BY id DESC
    LIMIT 3
""")
for row in cursor.fetchall():
    id, item, qty, each, total, type, case, ts = row
    print(f"  ID={id}: {qty}x {item}")
    print(f"    Each: {each:,} | Total: {total:,}")
    print(f"    Type: {type} | Case: {case}")
    print(f"    Time: {ts}")
    print()

db.close()

print("=" * 80)
print("ANALYSIS")
print("=" * 80)
print("""
TEST SCENARIO:
- Initial: 172x Magical Shard in warehouse
- Old listing: 200x @ 580,261,500 (net) - FULLY FILLED
- Clicked "Relist" on old listing
- New listing: 172x @ 569,320,000 (gross)
- Detail-Window CLOSES AUTOMATICALLY after relist!

EXPECTED:
âœ… Old listing marked collected (200x @ 580,261,500)
âœ… Transaction saved (200x @ 580,261,500, case=sell_relist_partial)
âœ… NEW listing created (172x @ 569,320,000)

CRITICAL ISSUE:
âš ï¸ Sell-Detail-Window AUTO-CLOSES immediately after relist!
âš ï¸ No time for Delta-Detection (Warehouse: 172 â†' 0)!
âš ï¸ Only 2 scans before window closed!

LOG TIMELINE:
22:35:20.201: BASELINE CAPTURED - Warehouse: 172 âœ…
22:35:21.965: Scan #2 - Warehouse: None (FAILED!) - Window closing
22:35:23.399: Overview-Log parsing - Transaction saved âœ…
22:35:23.408: Listing marked collected âœ…

ROOT CAUSE:
Sell-Detail-Window schließt sich SOFORT nach Relist-Submit!
â†' Keine Zeit für Scan #3 um Warehouse=0 zu sehen
â†' Detail-Window Relist-Detection UNMÖGLICH für Sell-Side!
â†' MUSS auf Overview-Log Fallback verlassen!
""")
