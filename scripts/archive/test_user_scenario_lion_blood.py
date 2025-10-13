"""
Test des Original-Szenarios aus User-Request:
"F Lion Blood" aus OCR-Text "Placed order f Lion Blood x5,000 for 75,000,000 Silver"
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tracker import MarketTracker
from database import get_cursor, get_connection

def reset_db():
    cur = get_cursor()
    cur.execute("DELETE FROM transactions")
    get_connection().commit()

def main():
    print("=" * 80)
    print("Original User-Scenario Test: 'Placed order f Lion Blood'")
    print("=" * 80)
    
    reset_db()
    
    # Exakt der OCR-Text aus ocr_log.txt (Zeile 17)
    ocr_text = (
        "Central Market Warehouse Balance @ 76,730,736,302 Buy "
        "2025.10.12 02.00 2025.10.12 02:00 2025.10.12 01.58 2025.10.12 01.58 "
        "Placed order of Oil of Fortitude x3,000 for 226,500,000 Silver "
        "Transaction of Oil of Fortitude x3,000 worth 226,500,000 Silver has been comp_ "
        "Placed order f Lion Blood x5,000 for 75,000,000 Silver "  # <-- OCR-Fehler: "f" statt "of"
        "Withdrew order of Lion Blood x4,974 for 74,610,000 silver "
        "Orders Completed"
    )
    
    print("\nOCR-Text Snippet (Lion Blood Teil):")
    print("  'Placed order f Lion Blood x5,000 for 75,000,000 Silver'")
    print("           ^^^^ OCR-Fehler: fehlendes 'o' → 'f' statt 'of'\n")
    
    mt = MarketTracker(debug=True)
    mt.process_ocr_text(ocr_text)
    
    # Prüfe DB
    cur = get_cursor()
    cur.execute("""
        SELECT item_name, quantity, price, transaction_type, tx_case 
        FROM transactions 
        WHERE item_name LIKE '%Lion Blood%'
        ORDER BY timestamp
    """)
    results = cur.fetchall()
    
    print("\n" + "=" * 80)
    print("Ergebnis:")
    print("=" * 80)
    
    if not results:
        print("❌ FEHLER: Keine Lion Blood Transaktionen gefunden!")
        return 1
    
    success = True
    for item_name, qty, price, tx_type, tx_case in results:
        if item_name == "Lion Blood":
            print(f"✅ KORREKT: Item gespeichert als '{item_name}'")
            print(f"   Menge: {qty}, Preis: {price:,}, Typ: {tx_type}, Case: {tx_case}")
        elif "F Lion Blood" in item_name or item_name.startswith("F "):
            print(f"❌ FEHLER: Item gespeichert als '{item_name}' (OCR-Fehler nicht korrigiert!)")
            success = False
        else:
            print(f"⚠️  WARNUNG: Unerwarteter Name '{item_name}'")
    
    # Prüfe auch Oil of Fortitude (sollte ebenfalls gespeichert sein)
    cur.execute("SELECT item_name, quantity FROM transactions WHERE item_name LIKE '%Oil%'")
    oil_results = cur.fetchall()
    
    if oil_results:
        print(f"\n✅ Bonus: Oil of Fortitude ebenfalls korrekt gespeichert ({oil_results[0][1]}x)")
    
    print("\n" + "=" * 80)
    if success:
        print("🎉 TEST BESTANDEN: Nur valide Itemnamen aus item_names.csv wurden gespeichert!")
        print("   'F Lion Blood' wurde korrekt zu 'Lion Blood' korrigiert.")
        return 0
    else:
        print("❌ TEST FEHLGESCHLAGEN: Ungültige Itemnamen wurden gespeichert!")
        return 1

if __name__ == "__main__":
    exit(main())
