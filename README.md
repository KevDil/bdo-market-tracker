# BDO Market Tracker

Ein OCR-basierter Marktplatz-Tracker für Black Desert Online. Das Projekt nimmt Screenshots des Marktfensters, führt Game-UI-optimierte Vorverarbeitung und OCR (EasyOCR / optional PaddleOCR / Tesseract) aus, parsed erkannte Log-Zeilen, wendet Heuristiken und Fuzzy-Korrekturen an und persistiert gefundene Transaktionen in einer lokalen SQLite-Datenbank.

Dieses Repository enthält eine einfache Tkinter-GUI (`gui.py`) zur Live-Überwachung, Export-Funktionen (CSV/JSON) sowie mehrere Hilfs- und Diagnoseskripte unter `scripts/`.

## Kurzüberblick (auf Deutsch)

- Primäre Programmsprache: Python 3.10–3.13
- Haupt-Einstiegspunkt (GUI): `python gui.py`
- Datenbank: `bdo_tracker.db` (SQLite, liegt im Repo für Entwicklung)
- Primäre OCR-Engine: EasyOCR (default). Tesseract als Fallback. PaddleOCR optional (nicht standardmäßig aktiviert wegen Latenz).

## Features

- Live-Detection von Markt-Transaktionen (buy/sell)
- Multi-Engine OCR-Strategie mit Game-UI-spezifischer Vorverarbeitung
- Persistente Baseline und Deduplication-Logik, um doppelte Ereignisse zu vermeiden
- Config/Region-Kalibrierung, Auto-Track-Modus, Einzel-Scan
- Export als CSV / JSON aus der GUI
- Debug-artefakte: `debug_orig.png`, `debug_proc.png` und `ocr_log.txt`

## Voraussetzungen

- Windows 10+ (getestet)
- Python 3.10 bis 3.13
- Empfohlene Python-Pakete (siehe `requirements.txt`): EasyOCR, pytesseract, opencv-python, numpy, Pillow, mss, pandas, matplotlib, rapidfuzz, requests
- Optional: Tesseract-OCR (System-Installer), CUDA + cuDNN für GPU-Beschleunigung (nur wenn `USE_GPU` gesetzt)

Installation (empfohlen in einem virtuellen Environment):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Hinweis: Tesseract muss gesondert installiert werden, wenn Sie die Tesseract-Fallback-Engine nutzen wollen. EasyOCR lädt Modelle beim ersten Start automatisch herunter.

## Schnelle Anleitung

1. Spiel starten und das Marktfenster öffnen (Buy- oder Sell-Übersicht).
2. `python gui.py` starten.
3. Region anpassen (Standardregion ist im `config.py` voreingestellt). Alternativ im GUI auf "Auswahl" klicken und zwei Punkte im Bildschirm markieren.
4. "Einmal scannen" zum Testen oder "Auto-Tracking starten" aktivieren.

## Wichtige Dateien & Ordner

- `gui.py` — Tkinter GUI und Export-Funktionen
- `tracker.py` — Kern-Logik: Capture, OCR-Integration, Parsing, Heuristiken, Persistenz
- `parsing.py` — Muster/Parser für die Spiel-Logs
- `database.py` — SQLite-Wrapper und Hilfsfunktionen
- `market_json_manager.py` — Item-Korrektur (RapidFuzz + lokale Cache)
- `bdo_api_client.py` — Live-Preis-Checks (optional)
- `config.py` — zentrale Konfigurationswerte & persistent settings helpers
- `scripts/` — Hilfs- und Test-Skripte (z. B. `scripts/utils/reset_db.py`)

## Tests

Automatisierte Unit-Tests befinden sich in `tests/unit/`. Es gibt auch manuelle Replays unter `tests/manual/`.

Kurzer Testlauf:

```powershell
python scripts/run_all_tests.py
```

Für gezielte Tests (Beispiele):

```powershell
python tests/unit/test_parsing_crystal.py
python tests/unit/test_collect_anchor.py
```

## Packaging

Es gibt pyinstaller-Spezifikationen unter `pyinstaller/` und ein Powershell-Packaging-Skript `PackagingScript.ps1`. Use the specs `pyinstaller/market_tracker_cpu.spec` or `market_tracker_cuda.spec` depending on whether you package for GPU-support.

Wichtige Hinweise beim Packaging:

- Wenn GPU-Unterstützung aktiviert wird, stellen Sie sicher, dass Zielsystem CUDA/Driver-kompatibel ist.
- Prüfen Sie `config.TESS_PATH` falls Tesseract verwendet wird.
- Behalten Sie `bdo_tracker.db` und `config/` Dateien im Paket oder dokumentieren Sie, wie sie initialisiert werden.

## Debugging

- OCR-Probleme: `ocr_log.txt` prüfen, `debug_orig.png` vs. `debug_proc.png` vergleichen. Verwenden Sie `scripts/utils/compare_ocr.py`.
- Parsing-Probleme: Unit-Tests in `tests/unit/` ausführen. Aktivieren Sie `Debug-Modus` in der GUI.
- DB-Probleme: `inspect_db.py` oder `check_db.py` laufen lassen. `scripts/utils/reset_db.py` setzt Entwicklungs-DB zurück.

## Betrieb & Design-Invarianten (Kurzform)

- Fokus-Guard: Nur scannen, wenn das Spiel-Fenster aktiv ist (konfiguriert in `config.py`).
- ROI: Standard-Region wird auf Top ~75% des Marktfensters getrimmt; Anpassungen nur über `scripts/utils/calibrate_region.py`.
- OCR-Cache: Screenshot-MD5-Caching aktiv (siehe `utils.py`) — nicht deaktivieren.
- Item-Whitelist & Korrektur: Items laufen durch `market_json_manager.correct_item_name` (RapidFuzz-Schwelle konfigurierbar).
- Quantity-Bounds: 1..5000 (Filter für UI-Rauschen).

## Weiteres / Contributors

Siehe `AGENTS.md` für die internen Richtlinien, Architektur-Notes und die Betriebsanleitung. Änderungen an Kernparametern (ROI, Polling, Cache-Policy) müssen mit reproduzierbaren Metriken dokumentiert werden (siehe `docs/`).

Wenn Sie etwas anpassen, führen Sie die vorhandenen Unit-Tests aus und fügen Sie weitere Tests hinzu, wenn sich das Verhalten ändert.

---

Version: aktualisiert am 2025-10-18
