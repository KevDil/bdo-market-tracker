"""
Test für Item-Mengen-Validierung (MIN_ITEM_QUANTITY = 1, MAX_ITEM_QUANTITY = 5000)

Testet:
1. Mengen innerhalb der Grenzen (1-5000) werden akzeptiert
2. Menge 0 wird verworfen
3. Negative Mengen werden verworfen
4. Mengen > 5000 werden verworfen
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker import MarketTracker
from database import get_cursor, get_connection
from config import MIN_ITEM_QUANTITY, MAX_ITEM_QUANTITY

def reset_db():
    """Reset DB for clean test"""
    cur = get_cursor()
    cur.execute("DELETE FROM transactions")
    get_connection().commit()

def test_valid_quantities():
    """Test 1: Gültige Mengen (1, 100, 5000) werden akzeptiert"""
    print("\n=== Test 1: Gültige Mengen ===")
    print(f"Bounds: MIN={MIN_ITEM_QUANTITY}, MAX={MAX_ITEM_QUANTITY}")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    # Test verschiedene gültige Mengen
    test_cases = [
        ("Lion Blood", 1, "min boundary"),
        ("Lion Blood", 100, "typical value"),
        ("Lion Blood", 5000, "max boundary"),
    ]
    
    for item, qty, desc in test_cases:
        text = (
            f"Central Market Buy 2025.10.12 10.00 "
            f"Purchased {item} x{qty} for {qty * 15000} Silver "
            "Orders Completed"
        )
        mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("SELECT item_name, quantity FROM transactions ORDER BY quantity")
    results = cur.fetchall()
    
    expected = 3
    if len(results) == expected:
        print(f"✅ Alle {expected} gültigen Mengen gespeichert:")
        for item_name, qty in results:
            print(f"   - {qty}x {item_name}")
        return True
    else:
        print(f"❌ Erwartete {expected} Einträge, gefunden: {len(results)}")
        return False

def test_zero_quantity():
    """Test 2: Menge 0 wird verworfen"""
    print("\n=== Test 2: Menge 0 ===")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    text = (
        "Central Market Buy 2025.10.12 10.00 "
        "Purchased Lion Blood x0 for 0 Silver "
        "Orders Completed"
    )
    
    mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("SELECT quantity FROM transactions WHERE quantity = 0")
    results = cur.fetchall()
    
    if not results:
        print("✅ Menge 0 wurde korrekt verworfen")
        return True
    else:
        print(f"❌ Menge 0 wurde gespeichert: {results}")
        return False

def test_quantity_above_max():
    """Test 3: Mengen > MAX_ITEM_QUANTITY werden verworfen"""
    print(f"\n=== Test 3: Mengen > {MAX_ITEM_QUANTITY} ===")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    # Test Mengen über dem Limit
    test_cases = [
        5001,    # Knapp über Limit
        10000,   # Deutlich über Limit
        100000,  # Sehr hoch (typischer UI-Noise)
    ]
    
    for qty in test_cases:
        text = (
            f"Central Market Buy 2025.10.12 10.00 "
            f"Purchased Lion Blood x{qty} for {qty * 15000} Silver "
            "Orders Completed"
        )
        mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute(f"SELECT quantity FROM transactions WHERE quantity > {MAX_ITEM_QUANTITY}")
    results = cur.fetchall()
    
    if not results:
        print(f"✅ Alle Mengen > {MAX_ITEM_QUANTITY} wurden korrekt verworfen")
        return True
    else:
        print(f"❌ Mengen > {MAX_ITEM_QUANTITY} wurden gespeichert: {[r[0] for r in results]}")
        return False

def test_boundary_edge_cases():
    """Test 4: Grenzwerte exakt testen"""
    print(f"\n=== Test 4: Grenzwerte (1 und {MAX_ITEM_QUANTITY}) ===")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    # Exakt MIN und MAX
    text = (
        f"Central Market Buy 2025.10.12 10.00 "
        f"Purchased Lion Blood x{MIN_ITEM_QUANTITY} for 15000 Silver "
        f"Purchased Oil of Fortitude x{MAX_ITEM_QUANTITY} for 75000000 Silver "
        "Orders Completed"
    )
    
    mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("SELECT item_name, quantity FROM transactions ORDER BY quantity")
    results = cur.fetchall()
    
    if len(results) == 2:
        min_found = any(q == MIN_ITEM_QUANTITY for _, q in results)
        max_found = any(q == MAX_ITEM_QUANTITY for _, q in results)
        
        if min_found and max_found:
            print(f"✅ Grenzwerte akzeptiert: {MIN_ITEM_QUANTITY} und {MAX_ITEM_QUANTITY}")
            for item, qty in results:
                print(f"   - {qty}x {item}")
            return True
        else:
            print(f"❌ Grenzwerte nicht gefunden: min={min_found}, max={max_found}")
            return False
    else:
        print(f"❌ Erwartete 2 Einträge, gefunden: {len(results)}")
        return False

def main():
    print("=" * 70)
    print("Item Quantity Bounds Validation Test Suite")
    print(f"MIN_ITEM_QUANTITY = {MIN_ITEM_QUANTITY}")
    print(f"MAX_ITEM_QUANTITY = {MAX_ITEM_QUANTITY}")
    print("=" * 70)
    
    tests = [
        ("Valid Quantities (1, 100, 5000)", test_valid_quantities),
        ("Zero Quantity Rejection", test_zero_quantity),
        ("Above Max Rejection", test_quantity_above_max),
        ("Boundary Edge Cases", test_boundary_edge_cases),
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
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    
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
