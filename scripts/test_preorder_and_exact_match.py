"""
Test für Preorder-Only Detection und Exact Name Match

Testet:
1. Preorder (Placed+Withdrew ohne Transaction) wird NICHT als Kauf gespeichert
2. Echter Kauf (Purchased) wird gespeichert
3. "Sealed Black Magic Crystal" wird NICHT zu "Black Crystal" korrigiert
4. "Black Crystal" bleibt "Black Crystal" (beide Items existieren)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker import MarketTracker
from database import get_cursor, get_connection
from utils import correct_item_name

def reset_db():
    """Reset DB for clean test"""
    cur = get_cursor()
    cur.execute("DELETE FROM transactions")
    get_connection().commit()

def test_preorder_not_saved():
    """Test 1: Preorder (Placed+Withdrew ohne Transaction) wird nicht gespeichert"""
    print("\n=== Test 1: Preorder-Only wird nicht gespeichert ===")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    # Simuliere Preorder: Placed + Withdrew OHNE Transaction
    text = (
        "Central Market Buy 2025.10.12 02.23 "
        "Placed order of Sealed Black Magic Crystal x765 for 2,119,050,000 Silver "
        "Withdrew order of Sealed Black Magic Crystal x572 for 1,561,560,000 Silver "
        "Orders Completed"
    )
    
    mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("SELECT item_name, quantity FROM transactions WHERE quantity = 765")
    results = cur.fetchall()
    
    if not results:
        print("✅ Preorder (765x) wurde korrekt NICHT gespeichert")
        return True
    else:
        print(f"❌ Preorder wurde fälschlicherweise gespeichert: {results}")
        return False

def test_actual_purchase_saved():
    """Test 2: Echter Kauf (Purchased) wird gespeichert"""
    print("\n=== Test 2: Echter Kauf wird gespeichert ===")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    # Simuliere echten Kauf mit Purchased
    text = (
        "Central Market Buy 2025.10.12 02.23 "
        "Purchased Sealed Black Magic Crystal x25 for 70,250,000 Silver "
        "Orders Completed"
    )
    
    mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("SELECT item_name, quantity FROM transactions WHERE quantity = 25")
    results = cur.fetchall()
    
    if results and len(results) == 1:
        item_name, qty = results[0]
        print(f"✅ Echter Kauf gespeichert: {qty}x {item_name}")
        return True
    else:
        print(f"❌ Echter Kauf nicht gespeichert oder falsch: {results}")
        return False

def test_sealed_name_not_corrected():
    """Test 3: 'Sealed Black Magic Crystal' wird nicht zu 'Black Crystal' korrigiert"""
    print("\n=== Test 3: Exact Name Match (Sealed Black Magic Crystal) ===")
    
    # Test die Korrektur-Funktion direkt
    original = "Sealed Black Magic Crystal"
    corrected = correct_item_name(original, min_score=80)
    
    if corrected == original:
        print(f"✅ Name korrekt belassen: '{original}' → '{corrected}'")
        return True
    else:
        print(f"❌ Name falsch korrigiert: '{original}' → '{corrected}'")
        return False

def test_both_names_exist():
    """Test 4: Beide Items werden korrekt unterschieden"""
    print("\n=== Test 4: Black Crystal vs Sealed Black Magic Crystal ===")
    
    # Test beide Namen
    name1 = "Black Crystal"
    name2 = "Sealed Black Magic Crystal"
    
    corrected1 = correct_item_name(name1, min_score=80)
    corrected2 = correct_item_name(name2, min_score=80)
    
    if corrected1 == name1 and corrected2 == name2:
        print(f"✅ Beide Namen korrekt: '{name1}' und '{name2}'")
        return True
    else:
        print(f"❌ Namen falsch: '{name1}'→'{corrected1}', '{name2}'→'{corrected2}'")
        return False

def test_real_scenario():
    """Test 5: Reales Szenario mit Preorder + Kauf"""
    print("\n=== Test 5: Reales Szenario (Preorder + Kauf) ===")
    
    reset_db()
    mt = MarketTracker(debug=True)
    
    # Exakt wie im User-Log
    text = (
        "Central Market Buy 2025.10.12 02.23 2025.10.12 02.23 2025.10.12 02.23 "
        "Placed order of Sealed Black Magic Crystal x765 for 2,119,050,000 Silver "
        "Purchased Sealed Black Magic Crystal x25 for 70,250,000 Silver "
        "Withdrew order of Sealed Black Magic Crystal x572 for 1,561,560,000 Silver "
        "Orders Completed"
    )
    
    mt.process_ocr_text(text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("SELECT item_name, quantity, price FROM transactions ORDER BY quantity")
    results = cur.fetchall()
    
    # Erwartung: NUR der Purchased (25x) wird gespeichert, NICHT die Preorder (765x)
    expected = 1
    if len(results) == expected:
        item, qty, price = results[0]
        if qty == 25 and item == "Sealed Black Magic Crystal" and price == 70250000:
            print(f"✅ Nur Kauf gespeichert: {qty}x {item} für {price:,} Silver")
            print(f"✅ Preorder (765x) wurde nicht gespeichert")
            return True
        else:
            print(f"❌ Falsche Daten: {qty}x {item} für {price} (erwartet: 25x Sealed Black Magic Crystal für 70,250,000)")
            return False
    else:
        print(f"❌ Erwartete {expected} Eintrag, gefunden: {len(results)}")
        for item, qty, price in results:
            print(f"   - {qty}x {item} für {price:,}")
        return False

def main():
    print("=" * 80)
    print("Preorder Detection + Exact Name Match Test Suite")
    print("=" * 80)
    
    tests = [
        ("Preorder Not Saved", test_preorder_not_saved),
        ("Actual Purchase Saved", test_actual_purchase_saved),
        ("Sealed Name Not Corrected", test_sealed_name_not_corrected),
        ("Both Names Exist", test_both_names_exist),
        ("Real Scenario", test_real_scenario),
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
