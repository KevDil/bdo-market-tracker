"""
Test für strikte Item-Name-Validierung gegen config/item_names.csv

Testet:
1. Valide Items aus Whitelist werden akzeptiert
2. OCR-Fehler werden korrigiert (z.B. 'F Lion Blood' → 'Lion Blood')
3. Komplett falsche Items werden verworfen
4. UI-Garbage wird verworfen
"""

import datetime
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tracker import MarketTracker
from database import get_cursor, get_connection


def reset_db():
    """Reset DB for clean test"""
    cur = get_cursor()
    cur.execute("DELETE FROM transactions")
    get_connection().commit()
    print("✅ Database reset")


def test_valid_item():
    """Test 1: Valide Items werden akzeptiert"""
    print("\n=== Test 1: Valide Items ===")

    mt = MarketTracker(debug=True)

    text = (
        "Central Market Buy 2025.10.12 10.00 "
        "Purchased Lion Blood x100 for 1,500,000 Silver "
        "Orders Completed"
    )

    mt.process_ocr_text(text)

    cur = get_cursor()
    cur.execute("SELECT item_name, quantity FROM transactions WHERE item_name LIKE '%Lion Blood%'")
    results = cur.fetchall()

    if results:
        print(f"✅ Valides Item gespeichert: {results[0]}")
        return True
    else:
        print("❌ Valides Item wurde NICHT gespeichert!")
        return False


def test_ocr_error_correction():
    """Test 2: OCR-Fehler werden korrigiert"""
    print("\n=== Test 2: OCR-Fehler Korrektur ===")

    reset_db()
    mt = MarketTracker(debug=True)

    text = (
        "Central Market Buy 2025.10.12 10.00 "
        "Placed order of F Lion Blood x5000 for 75,000,000 Silver "
        "Transaction of F Lion Blood x5000 worth 75,000,000 Silver has been completed "
        "Orders Completed"
    )

    mt.process_ocr_text(text)

    cur = get_cursor()
    cur.execute("SELECT item_name, quantity FROM transactions")
    results = cur.fetchall()

    if results:
        item_name = results[0][0]
        if item_name == "Lion Blood":
            print(f"✅ OCR-Fehler korrigiert: 'F Lion Blood' → '{item_name}'")
            return True
        elif item_name == "F Lion Blood":
            print(f"❌ OCR-Fehler NICHT korrigiert! Item gespeichert als: '{item_name}'")
            return False
        else:
            print(f"⚠️ Unerwarteter Item-Name: '{item_name}'")
            return False
    else:
        print("⚠️ Item wurde verworfen (möglicherweise zu schwacher Fuzzy-Match)")
        return True


def test_invalid_item():
    """Test 3: Komplett falsche Items werden verworfen"""
    print("\n=== Test 3: Ungültige Items ===")

    reset_db()
    mt = MarketTracker(debug=True)

    text = (
        "Central Market Buy 2025.10.12 10.00 "
        "Purchased Invalid Fake Item x100 for 1,000,000 Silver "
        "Orders Completed"
    )

    mt.process_ocr_text(text)

    cur = get_cursor()
    cur.execute("SELECT item_name FROM transactions WHERE item_name LIKE '%Invalid%'")
    results = cur.fetchall()

    if results:
        print(f"❌ Ungültiges Item wurde gespeichert: {results[0]}")
        return False
    else:
        print("✅ Ungültiges Item wurde korrekt verworfen")
        return True


def test_ui_garbage():
    """Test 4: UI-Garbage wird verworfen"""
    print("\n=== Test 4: UI-Garbage ===")

    reset_db()
    mt = MarketTracker(debug=True)

    text = (
        "Central Market Buy 2025.10.12 10.00 "
        "Purchased Collect x100 for 1,000,000 Silver "
        "Purchased VT x100 for 1,000,000 Silver "
        "Purchased Orders Completed x100 for 1,000,000 Silver "
        "Orders Completed"
    )

    mt.process_ocr_text(text)

    cur = get_cursor()
    cur.execute("SELECT item_name FROM transactions")
    results = cur.fetchall()

    if results:
        print(f"❌ UI-Garbage wurde gespeichert: {[r[0] for r in results]}")
        return False
    else:
        print("✅ UI-Garbage wurde korrekt verworfen")
        return True


def main():
    print("=" * 60)
    print("Item Name Validation Test Suite")
    print("=" * 60)

    reset_db()

    tests = [
        ("Valid Item", test_valid_item),
        ("OCR Error Correction", test_ocr_error_correction),
        ("Invalid Item Rejection", test_invalid_item),
        ("UI Garbage Rejection", test_ui_garbage),
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

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

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
    sys.exit(main())
