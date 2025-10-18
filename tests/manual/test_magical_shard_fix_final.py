#!/usr/bin/env python3
"""
Final regression test for the Magical Shard missing transaction bug.
"""
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tracker import MarketTracker


def reset_db():
    conn = sqlite3.connect('bdo_tracker.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE timestamp >= '2025-10-12 14:00:00'")
    conn.commit()
    conn.close()


def check_transaction(item_name, expected_type, expected_qty, min_price, max_price):
    conn = sqlite3.connect('bdo_tracker.db')
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT timestamp, transaction_type, item_name, quantity, price, tx_case
        FROM transactions
        WHERE item_name = ?
        AND timestamp >= '2025-10-12 14:00:00'
        ORDER BY timestamp DESC
        LIMIT 1
        """,
        (item_name,),
    )
    result = cursor.fetchone()
    conn.close()
    if not result:
        print(f"   ❌ No transaction found for {item_name}")
        return False

    ts, tx_type, item, qty, price, case = result
    price_ok = min_price <= price <= max_price
    qty_ok = qty == expected_qty
    type_ok = tx_type == expected_type

    success = price_ok and qty_ok and type_ok
    status = "✅" if success else "❌"
    print(f"   {status} {ts} | {tx_type} | {qty}x {item} @ {price:,.0f} Silver | {case}")
    if not success:
        print(f"      Expected: {expected_type} | {expected_qty}x | price between {min_price:,} and {max_price:,}")
        if not type_ok:
            print(f"      Type mismatch: got {tx_type}, expected {expected_type}")
        if not qty_ok:
            print(f"      Quantity mismatch: got {qty}, expected {expected_qty}")
        if not price_ok:
            print(f"      Price out of range: got {price:,.0f}, expected {min_price:,}-{max_price:,}")
    return success


def test_original_issue():
    print("=" * 80)
    print("TEST: Original Magical Shard Missing Transaction (200x @ 585,585,000)")
    print("=" * 80)

    reset_db()
    text = (
        "Central Market Warehouse Balance @ 64,868,771,502 Buy "
        "2025.10.12 14.12 2025.10.12 14.12 2025.10.12 13.50 2025.10.12 13.50 "
        "Listed Magical Shard x2OO for 654,000,000 Silver. The price of enhancement m_. "
        "Transaction of Magical Shard x2OO worth 585,585,000 Silver has been complet__ "
        "Placed order of Pure Powder Reagent x5,000 for 67,500,000 Silver "
        "Transaction of Pure Powder Reagent xl,000 worth 13,600,000 Silver has been "
        "Warehouse Capacity 6 8,714.5 / 11,000 VT Pearl Item Selling Limit 31.590 Sell Sell "
        "Enter a search term Enter a search term: Items Listed 756 Sales Completed"
    )

    print("\n--- Processing OCR Text ---")
    mt = MarketTracker(debug=False)
    mt.process_ocr_text(text)

    print("\n--- Checking Database ---")
    magical_shard_ok = check_transaction("Magical Shard", "sell", 200, 585000000, 586000000)

    print("\n--- Result ---")
    if magical_shard_ok:
        print("✅ Original issue FIXED: Magical Shard transaction saved correctly!")
        return True
    print("❌ Original issue NOT fixed: Magical Shard transaction missing or incorrect!")
    return False


if __name__ == '__main__':
    success = test_original_issue()
    print("\n" + "=" * 80)
    sys.exit(0 if success else 1)
