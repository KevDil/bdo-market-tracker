# dedupe_db.py
import sqlite3
import shutil
import datetime
import os
import sys
from pathlib import Path

# Projekt-Root (zwei Ebenen über scripts/utils/)
ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = str(ROOT_DIR / "bdo_tracker.db")

if not os.path.exists(DB_PATH):
    print("Fehler: Datenbank", DB_PATH, "nicht gefunden.")
    sys.exit(1)

# 1) Backup erstellen
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
backup = f"{DB_PATH}.backup_{ts}"
shutil.copy2(DB_PATH, backup)
print("Backup erstellt:", backup)

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# 2) Suche Gruppen mit mehr als 1 Eintrag (exakte Gleichheit auf item, qty, price, type, timestamp)
cur.execute("""
SELECT item_name, quantity, price, transaction_type, timestamp, COUNT(*) as cnt
FROM transactions
GROUP BY item_name, quantity, price, transaction_type, timestamp
HAVING cnt > 1
""")
dups = cur.fetchall()

if not dups:
    print("Keine exakten Duplikat-Gruppen gefunden.")
else:
    print(f"Gefundene Duplikat-Gruppen: {len(dups)}")
    total_removed = 0
    for item_name, qty, price, tx_type, ts_val, cnt in dups:
        # entferne alle bis auf die kleinste id (behalte eine Zeile)
        cur.execute("""
            DELETE FROM transactions
            WHERE id NOT IN (
                SELECT min(id) FROM transactions
                WHERE item_name = ? AND quantity = ? AND price = ? AND transaction_type = ? AND timestamp = ?
            )
            AND item_name = ? AND quantity = ? AND price = ? AND transaction_type = ? AND timestamp = ?
        """, (item_name, qty, price, tx_type, ts_val, item_name, qty, price, tx_type, ts_val))
        removed = cur.rowcount
        total_removed += removed
        if removed:
            print(f"  → Entfernt: {removed} Duplikate für {item_name} | qty={qty} | price={price} | type={tx_type} | ts={ts_val}")
    conn.commit()
    print("Gesamt entfernt:", total_removed)

# 3) Unique-Index anlegen (verhindert spätere exakte Duplikate)
#    Index auf item_name, quantity, price, transaction_type, timestamp
try:
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_tx_full
        ON transactions(item_name, quantity, price, transaction_type, timestamp)
    """)
    conn.commit()
    print("Unique-Index idx_unique_tx_full erstellt (oder existierte bereits).")
except Exception as e:
    print("Fehler beim Erstellen des Unique-Index:", e)

# 4) Optional: VACUUM zur Reduktion der Dateigröße
try:
    cur.execute("VACUUM")
    print("VACUUM ausgeführt.")
except Exception as e:
    print("VACUUM fehlgeschlagen:", e)

conn.close()
print("Fertig. Bitte die Anwendung neu starten und einen Testlauf machen.")
