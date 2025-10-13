# Quick Reference Guide

**Version:** 0.2.4 | **Status:** ✅ BETA (29/29 Tests) | **Last Updated:** 2025-10-12

## 🚀 Commands

### Starten
```bash
python gui.py
```

### Tests
```bash
# Alle Tests (29/29 PASS)
python scripts/run_all_tests.py

# Performance-Benchmark
python scripts/benchmark_performance.py --iterations 10

# Wichtigste Tests
python scripts/test_exact_user_scenario.py          # Real-World-Szenario
python scripts/test_market_data_integration.py      # Live-API-Integration
python scripts/test_item_validation.py              # Whitelist-Validierung
python scripts/test_window_detection.py             # Window-Type-Detection
```

### Utilities
```bash
# DB-Operationen
python scripts/utils/reset_db.py          # DB zurücksetzen
python scripts/utils/dedupe_db.py         # Duplikate entfernen

# Debug
python scripts/utils/compare_ocr.py       # OCR-Methoden vergleichen (EasyOCR vs Tesseract)
python scripts/utils/calibrate_region.py  # Region kalibrieren (DEFAULT_REGION)
python scripts/utils/debug_window.py      # Window-Detection testen
```

## 📁 Wichtige Dateien

### Konfiguration
- `config.py` - Alle Einstellungen (Regions, OCR-Parameter, Performance-Tuning)
- `config/market.json` - Item-Datenbank (4874 Items, Name↔ID Mapping)
- `config/item_categories.csv` - Buy/Sell-Kategorien (Historical Detection)

### Debug
- `ocr_log.txt` - OCR-Output & Transaktionen (ERSTE ANLAUFSTELLE)
- `debug_orig.png` - Original-Screenshot
- `debug_proc.png` - Preprocessed-Screenshot
- `debug/` - Archivierte Debug-Files

### Dokumentation
- `README.md` - Projekt-Übersicht
- `instructions.md` - Vollständige Spezifikation
- `docs/OCR_V2_README.md` - OCR-Details
- `docs/PERFORMANCE_ANALYSIS_2025-10-12.md` - Performance-Tipps

### Tests
- `scripts/TEST_SUITE_OVERVIEW.md` - Test-Dokumentation
- `scripts/` - 14 aktive Tests
- `scripts/archive/` - Alte Tests

## 🐛 Debugging-Workflow

### 1. OCR-Probleme
```bash
# 1. Prüfe ocr_log.txt (letzte 100 Zeilen)
tail -n 100 ocr_log.txt

# 2. Vergleiche Screenshots
# debug_orig.png vs debug_proc.png

# 3. Teste OCR-Methoden
python scripts/utils/compare_ocr.py
```

### 2. Parsing-Probleme
```bash
# 1. Debug-Mode aktivieren (GUI oder MarketTracker(debug=True))
# 2. Prüfe ocr_log.txt für Parsing-Fehler
# 3. Teste mit Parsing-Tests
python scripts/test_parsing_crystal.py
```

### 3. Window-Detection-Probleme
```bash
# 1. Prüfe ocr_log.txt für "Window changed"
# 2. Teste Window-Detection
python scripts/test_window_detection.py

# 3. Kalibriere Region
python scripts/utils/calibrate_region.py
```

### 4. Transaktionen fehlen
```bash
# 1. Prüfe ocr_log.txt: Wurde Transaction erkannt?
# 2. Prüfe Window-Type: sell_overview oder buy_overview?
# 3. Prüfe Item-Name: In config/item_names.csv?
# 4. Prüfe Quantity: Zwischen 1 und 5000?
# 5. DB prüfen:
sqlite3 bdo_tracker.db "SELECT * FROM transactions ORDER BY id DESC LIMIT 10;"
```

## 📊 Window-Types

| Window | Keywords | Log? | Verwendung |
|--------|----------|------|------------|
| sell_overview | "Sales Completed" | ✅ JA | Verkaufs-Transaktionen |
| buy_overview | "Orders Completed" | ✅ JA | Kauf-Transaktionen |
| sell_item | "Set Price" + "Register Quantity" | ❌ NEIN | Item zum Verkauf einstellen |
| buy_item | "Desired Price" + "Desired Amount" | ❌ NEIN | Kauforder platzieren |

**WICHTIG:** Es ist IMMER nur EIN Tab sichtbar (Buy ODER Sell)

## 🎯 Transaction Cases

### Sell-Side
1. **sell_collect** - Item verkauft + abgeholt (1x Transaction)
2. **sell_relist_full** - Komplett verkauft + neu eingestellt (Transaction + Listed)
3. **sell_relist_partial** - Teilweise verkauft + Rest neu (Transaction + Withdrew + Listed)

### Buy-Side
4. **buy_collect** - Item gekauft + abgeholt (1x Transaction)
5. **buy_relist_full** - Komplett gekauft + neue Order (Transaction + Listed)
6. **buy_relist_partial** - Teilweise gekauft + Rest neu (Transaction + Withdrew + Listed)

## ⚠️ Critical Rules

1. **NUR instructions.md v2.4 ist gültig** (keine älteren Versionen)
2. **Log nur in Overview-Fenstern auswerten** (nicht in sell_item/buy_item)
3. **Immer nur EIN Tab sichtbar** (Buy ODER Sell, nie beide)
4. **Strikte Item-Whitelist** (config/market.json via market_json_manager, 4874 Items)
5. **Live-API-Validierung** (BDO World Market API für Min/Max-Preise ±10%)
6. **Quantity-Bounds** [1, 5000] (typische BDO Stack-Größen)
7. **Anchor-Priorität** transaction > purchased > placed > listed
8. **Bei Problemen:** debug_proc.png, debug_orig.png, ocr_log.txt analysieren

## 🔧 Häufige Fixes

### "Nichts wird getrackt"
1. Prüfe Window-Detection: `python scripts/utils/debug_window.py`
2. Prüfe OCR-Output: `ocr_log.txt`
3. Aktiviere Debug-Mode in GUI
4. Teste mit: `python scripts/test_window_detection.py`

### "Falsche Items"
1. Prüfe `config/market.json` - Item vorhanden? (4874 Items)
2. Teste Item-Validation: `python scripts/test_item_validation.py`
3. Teste Fuzzy-Matching: `python scripts/test_utils.py`
4. Prüfe `ocr_log.txt` für Korrektur-Meldungen
5. Teste Market-API: `python scripts/test_market_data_integration.py`

### "Duplikate"
1. DB deduplizieren: `python scripts/utils/dedupe_db.py`
2. Prüfe Session-Signatur in DB
3. Delta-Detection prüfen (ocr_log.txt)

### "Performance-Probleme"
1. Benchmark laufen lassen: `python scripts/benchmark_performance.py`
2. Prüfe `ocr_log.txt` Größe (Auto-Rotation @ 10MB)
3. Memory-Check: Task-Manager (~80MB normal)
4. Cache-Hit-Rate prüfen (ocr_log.txt → "Cache hit rate: XX%")
5. Siehe `docs/GPU_GAME_PERFORMANCE.md` für GPU-Optimierung

## 📈 Performance-Metriken (v0.2.4)

### Aktuelle Config (Optimal für RTX 4070 SUPER)
- **Poll-Interval:** 0.3s (~99 scans/min, erfasst >95% der Transaktionen)
- **OCR-Zeit:** ~1000ms avg (50% Cache-Hit-Rate)
- **GPU-VRAM:** 2GB Limit (0 Ruckler, Spiel hat Vorrang)
- **Throughput:** ~99 scans/min (GPU cached) vs ~60 scans/min (CPU)
- **Memory:** Stabil bei ~80MB (deque maxlen=1000)
- **Cache:** Screenshot-Hash-Cache (2s TTL, max 10 entries)
- **Log-Rotation:** Automatisch bei 10MB
- **Item-Cache:** LRU 500 (50-70% schnellere Fuzzy-Korrektur)

### Empfohlene Settings für andere Hardware
- **Ältere GPUs:** USE_GPU=False (CPU-Mode, 0 Ruckler, ~83 scans/min)
- **AFK-Tracking:** USE_GPU=True, POLL_INTERVAL=0.3s (max Speed)
- **Aktives Gaming:** CPU-Mode oder GPU @ 2GB Limit + Low Priority

## 🔄 Workflow

### Normaler Betrieb
1. Öffne Central Market im Spiel
2. Starte `python gui.py`
3. Klicke "Auto Track"
4. Tracker läuft im Hintergrund
5. Filter/Export nach Bedarf

### Testing
1. Ändere Code
2. Teste mit relevanten Tests aus `scripts/`
3. Führe `python scripts/run_all_tests.py` aus
4. Prüfe `ocr_log.txt` bei Fehlern
5. Update `instructions.md` bei Änderungen

### Debugging
1. Reproduziere Problem
2. Prüfe `ocr_log.txt` (IMMER ZUERST)
3. Prüfe `debug_proc.png` & `debug_orig.png`
4. Teste mit entsprechendem Test-Skript
5. Nutze Utility-Scripts bei Bedarf

---

**Version:** 0.2.3 | **Last Updated:** 2025-10-12
