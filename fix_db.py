"""
Korrigiere die fehlerhafte Magical Shard Transaction vom 2025-10-12 04:04:00
"""
import sqlite3

conn = sqlite3.connect('bdo_tracker.db')
c = conn.cursor()

# Zeige aktuelle falsche Zeile
print("Vorher:")
c.execute("""
    SELECT id, timestamp, transaction_type, item_name, quantity, price, tx_case 
    FROM transactions 
    WHERE item_name = 'Magical Shard' 
      AND timestamp = '2025-10-12 04:04:00'
""")
row = c.fetchone()
if row:
    print(f"  ID: {row[0]} | {row[1]} | {row[2]} | {row[4]}x {row[3]} | Price: {row[5]:,} | Case: {row[6]}")
    
    # Korrigiere Preis auf 585,585,000 (laut OCR-Log Line 2015)
    correct_price = 585585000
    
    c.execute("""
        UPDATE transactions 
        SET price = ?
        WHERE id = ?
    """, (correct_price, row[0]))
    
    conn.commit()
    
    print("\nNachher:")
    c.execute("""
        SELECT id, timestamp, transaction_type, item_name, quantity, price, tx_case 
        FROM transactions 
        WHERE id = ?
    """, (row[0],))
    row2 = c.fetchone()
    print(f"  ID: {row2[0]} | {row2[1]} | {row2[2]} | {row2[4]}x {row2[3]} | Price: {row2[5]:,} | Case: {row2[6]}")
    print("\n✅ Preis korrigiert!")
else:
    print("  ❌ Keine fehlerhafte Zeile gefunden")

conn.close()
