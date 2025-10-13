# BDO Market Tracker

**Version:** 0.2.4  
**Status:** ✅ BETA - Kernfunktionalität stabil (29/29 Tests), aktive Optimierung  
**Test Coverage:** 100% (29/29 Tests bestehen)

OCR-basierter Market-Tracker für Black Desert Online mit automatischer Transaktionserkennung, Live-API-Integration, GPU-Acceleration und persistenter Baseline.

## 🚀 Quick Start

1. **Installation:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Starten:**
   ```bash
   python gui.py
   ```

3. **Erste Schritte:**
   - Öffne das Central Market im Spiel
   - Klicke "Single Scan" für einen Test
   - Aktiviere "Auto Track" für kontinuierliches Tracking
   - Nutze Filter/Export für Analyse

## 📁 Projektstruktur

```
market_tracker/
├── 📄 Core Files (Hauptlogik)
│   ├── gui.py                 # Tkinter GUI
│   ├── tracker.py             # MarketTracker (Window-Detection, Gruppierung, Cases)
│   ├── parsing.py             # OCR-Parsing (Timestamp, Events, Items)
│   ├── database.py            # SQLite DB-Layer (thread-safe)
│   ├── utils.py               # OCR & Helpers (Preprocessing, Fuzzy-Matching)
│   └── config.py              # Konfiguration (Regions, Parameter)
│
├── 📊 Data & Config
│   ├── config/
│   │   ├── item_names.csv         # Item-Whitelist (für Fuzzy-Korrektur)
│   │   └── item_categories.csv    # Buy/Sell-Kategorien (Historical Detection)
│   ├── bdo_tracker.db             # SQLite Datenbank
│   └── backups/                   # Automatische DB-Backups
│
├── 🧪 Tests (Validierung)
│   ├── scripts/
│   │   ├── run_all_tests.py                        # Test-Runner (22 Tests)
│   │   ├── test_exact_user_scenario.py            # Reales User-Szenario
│   │   ├── test_fast_action_timing.py             # Fast Action Timing
│   │   ├── test_historical_fix.py                 # Historical Detection V3
│   │   ├── test_historical_placed_with_ui_overview.py  # UI-Overview Interference
│   │   ├── test_integration.py                    # Integration Tests
│   │   ├── test_item_validation.py                # Item-Name Whitelist
│   │   ├── test_multiple_purchased.py             # Multiple Purchased Events
│   │   ├── test_parsing_crystal.py                # Parsing Edge-Cases
│   │   ├── test_preorder_and_exact_match.py       # Preorder-Detection
│   │   ├── test_quantity_bounds.py                # Quantity Limits
│   │   ├── test_quick_fixes.py                    # Performance-Optimierungen
│   │   ├── test_user_scenario_lion_blood.py       # Lion Blood Case
│   │   ├── test_utils.py                          # Utils-Funktionen
│   │   ├── test_window_detection.py               # Window-Type Detection
│   │   └── archive/                               # Alte/überholte Tests
│   │
│   └── scripts/utils/                             # Utility-Scripts
│       ├── calibrate_region.py                    # Region-Kalibrierung
│       ├── compare_ocr.py                         # OCR-Methoden-Vergleich
│       ├── dedupe_db.py                           # DB-Deduplizierung
│       └── reset_db.py                            # DB-Reset
│
├── 📖 Documentation
│   ├── instructions.md                            # HAUPTDOKUMENTATION
│   ├── docs/
│   │   ├── OCR_V2_README.md                       # OCR V2 Details
│   │   ├── PERFORMANCE_ANALYSIS_2025-10-12.md     # Performance-Analyse
│   │   └── archive/                               # Alte Dokumentation
│   │
│   └── dev-screenshots/                           # Referenz-Screenshots
│       ├── listings_and_preorders/
│       └── windows/
│
└── 🐛 Debug (Laufzeit-Artefakte)
    ├── debug/                     # Debug-Screenshots & Logs
    ├── debug_orig.png             # Aktueller Original-Screenshot
    ├── debug_proc.png             # Aktueller Preprocessed-Screenshot
    └── ocr_log.txt                # Aktuelles OCR-Log
```

## ✨ Features

### Core Funktionalität
- ✅ **Live Market API:** BDO World Market API für dynamische Preis-Validierung (Min/Max ±10%)
- ✅ **OCR V2:** Sanftes Preprocessing (CLAHE, Sharpen), EasyOCR+Tesseract Hybrid, GPU-Support
- ✅ **4 Window Types:** sell_overview, buy_overview, sell_item, buy_item (auto-detection)
- ✅ **6 Transaction Cases:** collect, relist_full, relist_partial (buy & sell)
- ✅ **Persistent Baseline:** tracker_state DB → überlebt App-Restart, Delta-Detection

### Intelligente Verarbeitung
- ✅ **Anchor-Priorität:** transaction > purchased > placed > listed
- ✅ **Smart Parsing:** Leerzeichen-tolerant, OCR-Fehler-Korrektur (O→0, I→1), Fuzzy-Matching
- ✅ **Strict Validation:** market.json Whitelist (4874 Items), Quantity Bounds [1, 5000]
- ✅ **Historical Detection:** Item-Kategorien für Buy/Sell ohne Kontext

### Performance & UX
- ✅ **Screenshot-Hash-Cache:** 50-80% Reduktion bei statischen Screens
- ✅ **GPU-Acceleration:** RTX 4070 SUPER @ 2GB = 0 Ruckler, 20% schneller (~99 scans/min)
- ✅ **Memory-Optimiert:** Stabile 80MB, deque(maxlen=1000), Log-Rotation @ 10MB
- ✅ **GUI:** Live-Window-Status, Health-Indikator (🟢🟡🔴), Filter, Export (CSV/JSON), Plot
- ✅ **Fast Stop:** Interruptible Sleep <200ms Reaktionszeit

## 🧪 Testing

```bash
# Alle Tests ausführen (22/22 Tests)
python scripts/run_all_tests.py

# Einzelne Tests
python scripts/test_exact_user_scenario.py
python scripts/test_item_validation.py
python scripts/test_window_detection.py
```

## 🔧 Utility Scripts

```bash
# DB-Deduplizierung
python scripts/utils/dedupe_db.py

# DB-Reset
python scripts/utils/reset_db.py

# OCR-Methoden vergleichen
python scripts/utils/compare_ocr.py

# Region kalibrieren
python scripts/utils/calibrate_region.py
```

## 📊 Performance

- **Poll-Interval:** 0.5s (erfasst >95% der Transaktionen)
- **Stop-Response:** <200ms (Interruptible Sleep)
- **Memory-Usage:** Stabil (deque mit maxlen=1000)
- **DB-Queries:** 30-40% schneller (4 Indizes)
- **Item-Korrektur:** 50-70% schneller (LRU-Cache)

Siehe `docs/PERFORMANCE_ANALYSIS_2025-10-12.md` für Details.

## ⚠️ Wichtige Hinweise

- **NUR** `instructions.md` ist gültig (alle älteren Versionen obsolet)
- Transaktionslog nur in **sell_overview** und **buy_overview** auswerten
- Es ist **IMMER** nur EIN Tab sichtbar (Buy ODER Sell)
- **Strikte Item-Whitelist:** Nur Items aus `config/item_names.csv`
- **Quantity-Bounds:** MIN=1, MAX=5000 (typische BDO Stack-Größen)
- Bei Problemen: `debug_proc.png`, `debug_orig.png`, `ocr_log.txt` analysieren

## 🐛 Debugging

1. **OCR-Probleme:**
   - Prüfe `ocr_log.txt` (letzte 100 Zeilen)
   - Vergleiche `debug_orig.png` vs `debug_proc.png`
   - Teste mit `scripts/utils/compare_ocr.py`

2. **Parsing-Probleme:**
   - Aktiviere Debug-Toggle in GUI
   - Prüfe `ocr_log.txt` auf Parsing-Fehler
   - Teste mit `scripts/test_parsing_crystal.py`

3. **Window-Detection:**
   - Prüfe `ocr_log.txt` für "Window changed"
   - Teste mit `scripts/test_window_detection.py`
   - Nutze `scripts/utils/calibrate_region.py`

## 📝 Dokumentation

- **Hauptdokumentation:** `instructions.md` (vollständige Spec)
- **OCR Details:** `docs/OCR_V2_README.md`
- **Performance:** `docs/PERFORMANCE_ANALYSIS_2025-10-12.md`

## 🔮 Roadmap

- [ ] Parsing-Heuristiken vereinfachen (nach OCR V2 Validierung)
- [ ] Performance Phase 2 (Screenshot-Hash-Caching, GPU-Acceleration)
- [ ] GUI Improvements (Timeline-Panel, OCR-Toggle)
- [ ] Formale State-Machine für Fenster-Übergänge
- [ ] ML-basierter Confidence-Score für Buy/Sell-Entscheidung

## 📜 Lizenz

Für persönlichen Gebrauch.

---

**Version:** 0.2.3 | **Last Updated:** 2025-10-12 | **Status:** 🔧 In Entwicklung
