#!/usr/bin/env python3
"""
Test: Monks Branch Duplikat-Problem
Reproduziert das Problem wo UI-Fallback falschen Preis nimmt
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from parsing import extract_details_from_entry

def test_ocr_missing_leading_digit():
    """Test OCR-Fehler: fehlende führende Ziffer in Transaction"""
    print("\n" + "="*70)
    print("TEST 1: OCR Missing Leading Digit (1,980,000 → 980,000)")
    print("="*70)
    
    # OCR hat "1," am Anfang nicht erkannt
    ts = '2025.10.12 13.38'
    txt = "Transaction of Monk's Branch x88 worth 980,000 Silver has been completed"
    
    print(f"\nOCR Text: {txt}")
    
    details = extract_details_from_entry(ts, txt)
    
    if details:
        print(f"\n✅ Parsed:")
        print(f"   Item: {details['item']}")
        print(f"   Quantity: {details['qty']}")
        print(f"   Price: {details['price']}")
        print(f"   Type: {details['type']}")
        
        if details['price'] is None:
            print(f"\n⚠️  Price is None (wahrscheinlich wegen Plausibilitätsprüfung)")
            print(f"   980,000 / 88 = {980000/88:,.2f} Silver/Stück")
            print(f"   Das ist zu niedrig für Monk's Branch!")
        else:
            unit_price = details['price'] / details['qty']
            print(f"   Unit Price: {unit_price:,.2f} Silver/Stück")
    else:
        print(f"❌ Failed to parse")
    
    return details


def test_correct_price():
    """Test mit korrektem Preis"""
    print("\n" + "="*70)
    print("TEST 2: Correct Price (1,980,000)")
    print("="*70)
    
    ts = '2025.10.12 13.38'
    txt = "Transaction of Monk's Branch x88 worth 1,980,000 Silver has been completed"
    
    print(f"\nOCR Text: {txt}")
    
    details = extract_details_from_entry(ts, txt)
    
    if details:
        print(f"\n✅ Parsed:")
        print(f"   Item: {details['item']}")
        print(f"   Quantity: {details['qty']}")
        print(f"   Price: {details['price']:,}")
        print(f"   Type: {details['type']}")
        
        unit_price = details['price'] / details['qty']
        print(f"   Unit Price: {unit_price:,.2f} Silver/Stück")
    else:
        print(f"❌ Failed to parse")
    
    return details


def test_ui_fallback_issue():
    """Test: Was passiert wenn Transaction price=None und Placed price!=None?"""
    print("\n" + "="*70)
    print("TEST 3: UI Fallback Problem Simulation")
    print("="*70)
    
    print("\nSzenario:")
    print("  - Transaction: Monk's Branch x88 worth 980,000 → price=None (Plausibilitätsprüfung)")
    print("  - Placed: Monk's Branch x1,000 for 22,500,000")
    print("  - Withdrew: Monk's Branch x912 for 20,520,000")
    
    print("\n❌ PROBLEM:")
    print("  Tracker nimmt qty aus Transaction (88) ✅")
    print("  ABER price aus Placed (22,500,000) ❌")
    print("  Resultat: 88x für 22,500,000 = 255,682 Silver/Stück (FALSCH!)")
    
    print("\n✅ SOLLTE SEIN:")
    print("  88x für 1,980,000 = 22,500 Silver/Stück")
    
    print("\n🔧 LÖSUNG:")
    print("  UI-Fallback sollte NUR bei Collect verwendet werden (buy_collect/sell_collect)")
    print("  Bei Relist (buy_relist_partial/sell_relist_partial) darf KEIN UI-Fallback erfolgen")
    print("  Oder: UI-Fallback muss die gekaufte/verkaufte Menge aus Transaction verwenden")


def run_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("🧪 TESTING: Monk's Branch Duplikat-Problem")
    print("="*70)
    
    test_ocr_missing_leading_digit()
    test_correct_price()
    test_ui_fallback_issue()
    
    print("\n" + "="*70)
    print("📊 ZUSAMMENFASSUNG")
    print("="*70)
    print("\nRoot Cause:")
    print("  1. OCR verliert führende '1,' in Preis (1,980,000 → 980,000)")
    print("  2. Plausibilitätsprüfung reject Preis (980,000 / 88 = 11,136/Stück)")
    print("  3. Transaction-Event hat price=None")
    print("  4. UI-Fallback nimmt Placed-Preis (22,500,000) statt Transaction-Preis")
    print("  5. Resultat: 88x für 22,500,000 (FALSCH!)")
    
    print("\nFix-Strategie:")
    print("  A) UI-Fallback NUR bei Collect (keine Placed/Withdrew in Cluster)")
    print("  B) Bei Relist: Transaction-Preis ist Pflicht, UI-Fallback verboten")
    print("  C) Oder: UI-Fallback berechnet Preis aus UI MINUS withdrew (kompliziert)")
    
    print("\n⚠️  Empfehlung: Option B - Kein UI-Fallback bei Relist-Cases")


if __name__ == "__main__":
    run_tests()
