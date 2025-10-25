import sqlite3
from pathlib import Path

# Projekt-Root (zwei Ebenen über scripts/utils/)
ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = ROOT_DIR / "bdo_tracker.db"
OCR_LOG_PATH = ROOT_DIR / "ocr_log.txt"

# DB: ALLE Daten löschen, aber Struktur behalten
conn = sqlite3.connect(str(DB_PATH))
cur = conn.cursor()
cur.execute("DELETE FROM transactions")
cur.execute("DELETE FROM tracker_state")
cur.execute("DELETE FROM listings")
cur.execute("DELETE FROM preorders")
conn.commit()
conn.close()
print("✅ Alle Transaktionen gelöscht (Datenbankstruktur bleibt erhalten).")

# ocr_log.txt entfernen (falls vorhanden)
if OCR_LOG_PATH.exists():
	OCR_LOG_PATH.unlink()
	print("🧹 ocr_log.txt gelöscht.")
else:
	print("ℹ️ ocr_log.txt nicht gefunden (nichts zu löschen).")