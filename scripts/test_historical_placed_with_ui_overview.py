"""
Test für Historical Placed-Order mit UI-Overview Interference

Problem:
- Transaktionslog: "Placed order of Crystallized Despair x50 for 1,225,000,000 Silver" (02:22)
- UI-Overview: "Crystallized Despair Orders Orders Completed Collect" (qty=None)
- Beide werden mit gleichem Timestamp geclustert
- Preorder-Detection verwechselt UI-Overview-Event (listed, qty=None) mit echtem Relist
- Resultat: "skip preorder-only" obwohl es ein echter Kauf war

Erwartung:
- NUR Events mit qty (aus Transaktionslog) dürfen relist_flag_same triggern
- UI-Overview-Events (qty=None) werden ignoriert
- Historical Placed-Order wird als buy_relist_full gespeichert
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker import MarketTracker
from database import get_cursor, get_connection

def reset_db():
    """Reset DB for clean test"""
    cur = get_cursor()
    cur.execute("DELETE FROM transactions")
    cur.execute("DELETE FROM tracker_state")
    get_connection().commit()

def test_historical_placed_with_ui():
    """Test: Historical Placed-Order wird nicht von UI-Overview blockiert"""
    print("\n=== Test: Historical Placed + UI-Overview ===")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    # Simuliere First Snapshot mit:
    # 1. Transaktionslog: Placed order of Crystallized Despair x50 for 1,225M (02:22)
    # 2. UI-Overview: Crystallized Despair Orders/Completed (qty=None)
    # Wichtig: OCR erkennt beide mit gleichem Timestamp
    # MUSS "Orders Completed" enthalten für buy_overview detection!
    text = (
        "Central Market Warehouse Balance 74,129,996,302 Buy "
        "2025.10.12 02.22 "
        "Placed order of Crystallized Despair x50 for 1,225,000,000 Silver "
        "Orders 126462 Orders Completed 6150 Collect AI VT "
        "Crystallized Despair Orders Orders Completed Collect '159 155 155 424 612,500,000 Re-list"
    )
    
    mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("SELECT item_name, quantity, price, transaction_type, tx_case FROM transactions WHERE item_name = 'Crystallized Despair'")
    results = cur.fetchall()
    
    if not results:
        print("❌ Crystallized Despair wurde NICHT gespeichert (preorder-only false positive)")
        return False
    
    if len(results) != 1:
        print(f"❌ Erwartete 1 Transaktion, gefunden: {len(results)}")
        for item, qty, price, tx_type, tx_case in results:
            print(f"   - {qty}x {item} für {price:,} Silver, type={tx_type}, case={tx_case}")
        return False
    
    item, qty, price, tx_type, tx_case = results[0]
    
    # Erwartung: 50x Crystallized Despair als buy_relist_full
    # (placed ohne withdrew/transaction = relist_full in historical context)
    if qty == 50 and price == 1225000000 and tx_type == 'buy':
        print(f"✅ Crystallized Despair korrekt gespeichert: {qty}x für {price:,} Silver")
        print(f"   Type: {tx_type}, Case: {tx_case}")
        return True
    else:
        print(f"❌ Falsche Daten: {qty}x für {price:,} Silver, type={tx_type}, case={tx_case}")
        print(f"   Erwartet: 50x für 1,225,000,000 Silver, type=buy")
        return False

def test_ui_overview_only():
    """Test: UI-Overview ohne Transaktionslog wird NICHT gespeichert"""
    print("\n=== Test: UI-Overview Only (kein Transaktionslog) ===")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    # NUR UI-Overview, KEIN Transaktionslog-Event
    # MUSS "Orders Completed" enthalten für buy_overview detection!
    text = (
        "Central Market Warehouse Balance 74,129,996,302 Buy "
        "2025.10.12 02.22 "
        "Orders 126462 Orders Completed 6150 Collect AI VT "
        "Crystallized Despair Orders Orders Completed Collect '159 155 155 424 612,500,000 Re-list"
    )
    
    mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("SELECT item_name FROM transactions WHERE item_name = 'Crystallized Despair'")
    results = cur.fetchall()
    
    if not results:
        print("✅ UI-Overview-Only wird korrekt NICHT gespeichert")
        return True
    else:
        print(f"❌ UI-Overview wurde fälschlicherweise gespeichert: {results}")
        return False

def test_real_user_scenario():
    """Test: Reales User-Szenario mit Sealed Black Magic Crystal + Crystallized Despair"""
    print("\n=== Test: Reales User-Szenario (2 Items) ===")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    # Exakt wie im User-Log (ocr_log.txt lines 17-18)
    text = (
        "Central Market Warehouse Balance @ 74,129,996,302 Buy "
        "2025.10.12 02.23 2025.10.12 02.23 2025.10.12 02.23 2025.10.12 02.22 "
        "Placed order of Sealed Black Magic Crystal x765 for 2,119,050,000 Silver "
        "Purchased Sealed Black Magic Crystal x25 for 70,250,000 Silver "
        "Withdrew order of Sealed Black Magic Crystal x572 for 1,561,560,000 silver "
        "Placed order of Crystallized Despair x50 for 1,225,000,000 Silver "
        "Warehouse Capacity 6,277.1 /11,000 VT Pearl Item Selling Limit 31.590 Sell "
        "Orders   126462 Orders Completed 6150 Collect AI VT "
        "Sealed Black Magic Crystal Orders 765 Orders Completed 765 Collect Re-list "
        "Crystallized Despair Orders Orders Completed Collect '159 155 155 424 612,500,000 Re-list"
    )
    
    mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("SELECT item_name, quantity, price, transaction_type, tx_case FROM transactions ORDER BY item_name, quantity")
    results = cur.fetchall()
    
    # Erwartung: 2 Transaktionen
    # 1. Sealed Black Magic Crystal x25 (purchased, buy_collect oder buy_relist_partial)
    # 2. Crystallized Despair x50 (placed, buy_relist_full)
    expected = 2
    if len(results) != expected:
        print(f"❌ Erwartete {expected} Transaktionen, gefunden: {len(results)}")
        for item, qty, price, tx_type, tx_case in results:
            print(f"   - {qty}x {item} für {price:,} Silver, type={tx_type}, case={tx_case}")
        return False
    
    # Check Crystallized Despair
    cd_result = [r for r in results if r[0] == 'Crystallized Despair']
    if not cd_result:
        print("❌ Crystallized Despair wurde NICHT gespeichert")
        return False
    
    item, qty, price, tx_type, tx_case = cd_result[0]
    if qty == 50 and price == 1225000000 and tx_type == 'buy':
        print(f"✅ Crystallized Despair: {qty}x für {price:,} Silver, type={tx_type}, case={tx_case}")
    else:
        print(f"❌ Crystallized Despair falsch: {qty}x für {price:,} Silver, type={tx_type}, case={tx_case}")
        return False
    
    # Check Sealed Black Magic Crystal
    sbmc_result = [r for r in results if r[0] == 'Sealed Black Magic Crystal']
    if not sbmc_result:
        print("❌ Sealed Black Magic Crystal wurde NICHT gespeichert")
        return False
    
    item, qty, price, tx_type, tx_case = sbmc_result[0]
    if qty == 25 and price == 70250000 and tx_type == 'buy':
        print(f"✅ Sealed Black Magic Crystal: {qty}x für {price:,} Silver, type={tx_type}, case={tx_case}")
    else:
        print(f"❌ Sealed Black Magic Crystal falsch: {qty}x für {price:,} Silver, type={tx_type}, case={tx_case}")
        return False
    
    print("✅ Beide Transaktionen korrekt gespeichert")
    return True

def main():
    print("=" * 80)
    print("Historical Placed-Order + UI-Overview Test Suite")
    print("=" * 80)
    
    tests = [
        ("Historical Placed + UI-Overview", test_historical_placed_with_ui),
        ("UI-Overview Only (no save)", test_ui_overview_only),
        ("Real User Scenario (2 items)", test_real_user_scenario),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"❌ Test '{name}' failed with error: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 80)
    print("Test Summary")
    print("=" * 80)
    
    passed = sum(1 for _, p in results if p)
    total = len(results)
    
    for name, p in results:
        status = "✅ PASS" if p else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️ Some tests failed")
        return 1

if __name__ == "__main__":
    exit(main())
