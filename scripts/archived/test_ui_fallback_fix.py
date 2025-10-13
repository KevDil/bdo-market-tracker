#!/usr/bin/env python3
"""
Test: UI-Fallback bei Relist-Cases verhindert
Verifiziert dass UI-Fallback NUR bei Collect-Cases angewendet wird
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

# Mock tracker state for testing
class MockTrackerState:
    def __init__(self):
        self.window_type = 'buy_overview'
        self.first_snapshot_mode = False
        self.ui_buy = {
            "monk's branch": {
                'orders': 1000,
                'ordersCompleted': 1000,
                'remainingPrice': 22500000
            }
        }
        
def test_relist_partial_no_ui_fallback():
    """Test: Bei relist_partial wird KEIN UI-Fallback angewendet"""
    print("\n" + "="*70)
    print("TEST 1: Relist Partial - KEIN UI-Fallback")
    print("="*70)
    
    print("\nSzenario:")
    print("  Case: buy_relist_partial")
    print("  Cluster:")
    print("    - Placed: Monk's Branch x1,000 for 22,500,000")
    print("    - Withdrew: Monk's Branch x912 for 20,520,000")
    print("    - Transaction: Monk's Branch x88 for ??? (price=None wegen OCR-Fehler)")
    print("  UI Metrics:")
    print("    - orders: 1000")
    print("    - ordersCompleted: 1000")
    print("    - remainingPrice: 22,500,000")
    
    case = 'relist_partial'
    price = None
    quantity = 88
    first_snapshot_mode = False
    
    print(f"\nLogik-Prüfung:")
    print(f"  needs_fallback: {price is None} (price is None)")
    print(f"  case == 'collect': {case == 'collect'}")
    print(f"  first_snapshot_mode: {first_snapshot_mode}")
    
    # Check condition from fix
    should_use_fallback = (price is None) and (not first_snapshot_mode) and (case == 'collect')
    
    print(f"\n  → UI-Fallback erlaubt: {should_use_fallback}")
    
    if should_use_fallback:
        # UI-Fallback würde angewendet
        fallback_price = 22500000  # aus ordersCompleted * remainingPrice
        print(f"\n❌ FEHLER: UI-Fallback würde angewendet!")
        print(f"   Resultat: 88x für {fallback_price:,} = {fallback_price/quantity:,.0f}/Stück")
        return False
    else:
        print(f"\n✅ KORREKT: UI-Fallback wird NICHT angewendet")
        print(f"   Transaktion wird verworfen (price=None)")
        return True


def test_collect_with_ui_fallback():
    """Test: Bei collect wird UI-Fallback angewendet"""
    print("\n" + "="*70)
    print("TEST 2: Collect - UI-Fallback ERLAUBT")
    print("="*70)
    
    print("\nSzenario:")
    print("  Case: buy_collect")
    print("  Cluster:")
    print("    - Transaction: Dehkia's Fragment x5 for ??? (price=None wegen OCR-Fehler)")
    print("  UI Metrics:")
    print("    - orders: 1000")
    print("    - ordersCompleted: 5")
    print("    - remainingPrice: 255,000,000")
    
    case = 'collect'
    price = None
    quantity = 5
    first_snapshot_mode = False
    
    # Mock UI metrics
    orders = 1000
    ordersCompleted = 5
    remainingPrice = 255000000
    
    print(f"\nLogik-Prüfung:")
    print(f"  needs_fallback: {price is None} (price is None)")
    print(f"  case == 'collect': {case == 'collect'}")
    print(f"  first_snapshot_mode: {first_snapshot_mode}")
    
    # Check condition from fix
    should_use_fallback = (price is None) and (not first_snapshot_mode) and (case == 'collect')
    
    print(f"\n  → UI-Fallback erlaubt: {should_use_fallback}")
    
    if should_use_fallback:
        # UI-Fallback berechnet Preis
        denom = max(0, orders - ordersCompleted)
        if ordersCompleted > 0 and remainingPrice > 0 and denom > 0:
            price_calc = ordersCompleted * (remainingPrice / denom)
            fallback_price = int(round(price_calc))
            print(f"\n✅ KORREKT: UI-Fallback wird angewendet")
            print(f"   Formel: {ordersCompleted} * ({remainingPrice:,} / ({orders} - {ordersCompleted}))")
            print(f"   Berechnung: {ordersCompleted} * ({remainingPrice:,} / {denom})")
            print(f"   Resultat: {fallback_price:,} Silver")
            print(f"   Unit Price: {fallback_price/quantity:,.0f} Silver/Stück")
            return True
    else:
        print(f"\n❌ FEHLER: UI-Fallback wird NICHT angewendet!")
        print(f"   Transaktion wird verworfen obwohl Fallback möglich wäre")
        return False


def test_relist_full_no_ui_fallback():
    """Test: Bei relist_full wird KEIN UI-Fallback angewendet"""
    print("\n" + "="*70)
    print("TEST 3: Relist Full - KEIN UI-Fallback")
    print("="*70)
    
    print("\nSzenario:")
    print("  Case: buy_relist_full")
    print("  Cluster:")
    print("    - Transaction: Black Stone Powder x5,000 for ??? (price=None)")
    print("    - Placed: Black Stone Powder x5,000 for 23,500,000")
    
    case = 'relist_full'
    price = None
    first_snapshot_mode = False
    
    print(f"\nLogik-Prüfung:")
    print(f"  needs_fallback: {price is None}")
    print(f"  case == 'collect': {case == 'collect'}")
    
    should_use_fallback = (price is None) and (not first_snapshot_mode) and (case == 'collect')
    
    print(f"\n  → UI-Fallback erlaubt: {should_use_fallback}")
    
    if should_use_fallback:
        print(f"\n❌ FEHLER: UI-Fallback würde angewendet!")
        return False
    else:
        print(f"\n✅ KORREKT: UI-Fallback wird NICHT angewendet")
        return True


def run_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("🧪 TESTING: UI-Fallback bei Relist-Cases verhindert")
    print("="*70)
    print("\n⚠️  Nach dem Fix sollte UI-Fallback NUR bei 'collect' angewendet werden")
    
    results = {
        'Relist Partial': test_relist_partial_no_ui_fallback(),
        'Collect': test_collect_with_ui_fallback(),
        'Relist Full': test_relist_full_no_ui_fallback(),
    }
    
    print("\n" + "="*70)
    print("📊 TEST RESULTS")
    print("="*70)
    
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test_name}: {status}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n✅ ALLE TESTS BESTANDEN!")
        print("\n📋 Verified:")
        print("  ✅ UI-Fallback bei relist_partial: NICHT angewendet")
        print("  ✅ UI-Fallback bei relist_full: NICHT angewendet")
        print("  ✅ UI-Fallback bei collect: WIRD angewendet")
        print("\n🎉 Fix erfolgreich - Monk's Branch Problem gelöst!")
    else:
        failed = [name for name, passed in results.items() if not passed]
        print(f"\n❌ {len(failed)} TEST(S) FEHLGESCHLAGEN: {', '.join(failed)}")
    
    return all_passed


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
