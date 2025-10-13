#!/usr/bin/env python3
"""
Cleanup: Lösche falsche Monk's Branch Einträge
Behalte nur den korrekten: ID 2 (88x für 1,980,000 Silver)
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

db_path = Path(__file__).parent.parent / 'bdo_tracker.db'

def cleanup_monks_branch():
    """Delete incorrect Monk's Branch entries"""
    
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    print("\n" + "="*70)
    print("🧹 CLEANUP: Monk's Branch Duplikate")
    print("="*70)
    
    # Show current state
    cur.execute('''
        SELECT id, timestamp, item_name, quantity, price, tx_case 
        FROM transactions 
        WHERE item_name LIKE ? 
        ORDER BY id
    ''', ('%Monk%',))
    
    rows = cur.fetchall()
    
    print(f"\nAKTUELL: {len(rows)} Einträge gefunden:")
    for r in rows:
        unit_price = r[4] / r[3] if r[3] > 0 else 0
        status = "✅ KORREKT" if r[0] == 2 else "❌ FALSCH"
        print(f"  {status} - ID {r[0]}: {r[2]} x{r[3]} für {r[4]:,.0f} ({unit_price:,.0f}/Stück) [{r[5]}] @ {r[1]}")
    
    # Delete incorrect entries
    print(f"\n🔧 Lösche falsche Einträge (ID 3 und ID 4)...")
    
    cur.execute('DELETE FROM transactions WHERE id IN (3, 4) AND item_name LIKE ?', ('%Monk%',))
    deleted = cur.rowcount
    
    conn.commit()
    
    print(f"   Gelöscht: {deleted} Einträge")
    
    # Show final state
    cur.execute('''
        SELECT id, timestamp, item_name, quantity, price, tx_case 
        FROM transactions 
        WHERE item_name LIKE ? 
        ORDER BY id
    ''', ('%Monk%',))
    
    rows = cur.fetchall()
    
    print(f"\nFINAL: {len(rows)} Eintrag verbleibt:")
    for r in rows:
        unit_price = r[4] / r[3] if r[3] > 0 else 0
        print(f"  ✅ ID {r[0]}: {r[2]} x{r[3]} für {r[4]:,.0f} ({unit_price:,.0f}/Stück) [{r[5]}] @ {r[1]}")
    
    conn.close()
    
    print("\n" + "="*70)
    print("✅ Cleanup abgeschlossen!")
    print("="*70)
    
    return deleted


if __name__ == "__main__":
    deleted_count = cleanup_monks_branch()
    print(f"\n📊 Zusammenfassung: {deleted_count} falsche Einträge gelöscht")
    sys.exit(0)
