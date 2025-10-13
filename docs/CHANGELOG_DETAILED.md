# Change History - Detailed Archive

Dieses Dokument enthält die ausführlichen Beschreibungen aller wichtigen Änderungen am BDO Market Tracker. Die Kurzfassungen finden sich in `instructions.md` unter `recent_changes`.

## 2025-10-12: Project Cleanup - Structure Reorganization + Path Fixes

**Kategorie:** Project Structure  
**Impact:** Bessere Navigation, klare Struktur, 22/22 Tests bestehen

### Änderungen

- **Dokumentation konsolidiert:**
  - `README.md` hinzugefügt (Projekt-Übersicht, Quick Start)
  - `QUICK_REFERENCE.md` erstellt (Commands & Debugging)
  - Alte Docs nach `docs/archive/` verschoben (QUICK_FIXES, QUICK_WINS, roadmap.txt)

- **Tests organisiert:**
  - 14 aktive Tests in `scripts/`
  - 16 alte/überholte Tests in `scripts/archive/`
  - `scripts/TEST_SUITE_OVERVIEW.md` mit Test-Matrix

- **Utilities getrennt:**
  - `scripts/utils/` für calibrate, compare_ocr, dedupe_db, reset_db, etc.
  - Path-Fixes: Alle scripts/utils/*.py korrigiert (parents[2] statt parents[1])

- **Debug-Files strukturiert:**
  - `debug/` für archivierte Screenshots/Logs
  - Aktuelle Files bleiben im Root (debug_orig.png, debug_proc.png, ocr_log.txt)

- **DB-Backups organisiert:**
  - `backups/` für alte Datenbank-Backups

### Dokumentation

- `docs/PATH_FIX_2025-10-12.md` - Detaillierte Path-Fix-Dokumentation
- `README.md` - Projekt-Übersicht
- `QUICK_REFERENCE.md` - Schnellreferenz

---

## 2025-10-12: Historical Placed-Orders + UI-Overview Interference

**Kategorie:** Critical Bugfix  
**Tests:** test_historical_placed_with_ui_overview.py (3/3 bestanden)

### Problem

Historical 'Placed order of Crystallized Despair x50 for 1,225M' (02:22) wurde nicht gespeichert.

### Root Causes

1. **UI-Overview Events:** `Crystallized Despair Orders Orders Completed` (qty=None) wurden mit Transaktionslog-Events (qty=123) geclustert
2. **Preorder-Detection:** Prüfte nur relist_flag ohne zwischen Transaktionslog (qty!=None) und UI-Overview (qty=None) zu unterscheiden
3. **Buy-Relist-Anchor-Rule:** Übersprang placed-only Events auch im first_snapshot_mode

### Solutions

1. `has_listed_same` und `has_placed_same` prüfen jetzt `r.get('qty') is not None` → UI-Overview Events werden ignoriert
2. Preorder-Skip-Regel erweitert: `if relist_flag AND has_withdrew AND NOT has_bought → skip` (OHNE withdrew = historical order, OK)
3. Buy-Relist-Anchor-Rule gilt NUR in NON-first_snapshot_mode → historische placed-only Events erlaubt

### Implementation

- `tracker.py` lines 827-830: has_listed_same/has_placed_same mit qty-Check
- `tracker.py` lines 838-841: preorder-skip mit withdrew-Check
- `tracker.py` line 1165: first_snapshot_mode exception

### Test Results

1. Historical Placed + UI-Overview → Crystallized Despair x50 gespeichert ✅
2. UI-Overview Only (ohne Transaktionslog) → NICHT gespeichert ✅
3. Reales User-Szenario (2 Items) → beide korrekt gespeichert ✅

---

## 2025-10-12: Preorder-Only Detection + Exact Name Match

**Kategorie:** Critical Bugfix  
**Tests:** test_preorder_and_exact_match.py (5/5 bestanden)

### Problem 1: Preorder als Kauf gespeichert

765x Sealed Black Magic Crystal Preorder (Placed+Withdrew ohne Transaction) wurde als buy_relist_partial gespeichert.

**Root Cause:** relist_flag_same ohne has_bought_same Check → Preorder-Management als abgeschlossene Transaktion behandelt

**Solution:** Placed/Listed + Withdrew OHNE Transaction/Purchased wird übersprungen (nur Preorder-Verwaltung, KEIN Kauf)

### Problem 2: Falsche Fuzzy-Korrektur

'Sealed Black Magic Crystal' wurde zu 'Black Crystal' korrigiert (beide Items existieren in BDO).

**Root Cause:** Fuzzy-Matching bevorzugte kürzeren Namen mit hohem Score, obwohl Original bereits valide

**Solution:** Exakter Match (case-insensitive) wird NICHT korrigiert → verhindert falsche Fuzzy-Korrekturen

### Implementation

- `tracker.py` lines 827-840: Preorder-Skip-Logik
- `utils.py` lines 368-384: Exact Match Check vor Fuzzy-Matching

### Test Results

1. Preorder-Only → NICHT gespeichert ✅
2. Echter Kauf → gespeichert ✅
3. 'Sealed Black Magic Crystal' → NICHT korrigiert ✅
4. 'Black Crystal' und 'Sealed Black Magic Crystal' → unterschieden ✅
5. Reales User-Szenario (765x Preorder + 25x Kauf) → nur 25x gespeichert ✅

---

## 2025-10-12: Strict Item Name Validation + Quantity Bounds

**Kategorie:** Critical Bugfix  
**Tests:** test_item_validation.py + test_user_scenario_lion_blood.py (4/4)

### Problem 1: OCR-Fehler bei Item-Namen

'F Lion Blood' wurde gespeichert ('Placed order f Lion Blood' → 'F' als Teil des Itemnamens).

**Root Cause:** `_valid_item_name()` prüfte nur auf UI-Garbage, NICHT gegen config/item_names.csv

**Solution - Two-Stage Validation:**
1. Erste Korrektur in `parsing.py` (extract_details_from_entry) mit correct_item_name()
2. Zweite Korrektur in `tracker.py` (vor Validierung) mit min_score=80
3. Strikte Whitelist-Prüfung in `_valid_item_name()` - verwirft Items die NICHT in item_names.csv stehen

### Problem 2: Unrealistische Item-Mengen

0, negative, >1Mio wurden nicht gefiltert.

**Solution:** Quantity Bounds: MIN_ITEM_QUANTITY=1, MAX_ITEM_QUANTITY=5000 (typische BDO Stack-Größen)

### Implementation

- `config.py`: neue Konstanten (MIN/MAX_ITEM_QUANTITY)
- `tracker.py` lines 147-189: _valid_item_name() mit Whitelist-Check
- `tracker.py` lines 1248-1254: Quantity-Check
- `utils.py`: CSV-Load-Fix

### Impact

- NUR valide Items (Namen + Mengen) werden gespeichert
- OCR-Fehler werden korrigiert oder verworfen
- Added to critical_rules: Item-Name-Whitelist + Quantity-Bounds [1, 5000]

---

## 2025-10-12: Fast Action Timing + Mixed Context Detection

**Kategorie:** Enhancement  
**Impact:** Schnelle Aktionen (<0.5s zwischen Events) werden besser getrackt

### Problem

Lion Blood Relist (263x für 3,918,700 Silver) wurde nicht getrackt, obwohl Transaction stattfand.

**Root Cause:** OCR-Scan passierte NACH Tab-Wechsel (sell_overview statt buy_overview) → Transaction-Zeile bereits aus Log verschwunden (nur 4 Zeilen Kapazität)

**Analysis:** Bei schnellen Aktionen (Relist → Relist → Tab-Wechsel) kann Transaction-Zeile aus 4-Zeilen-Log rausgeschoben werden BEVOR nächster Scan passiert

### Solution: Mixed Context Detection

sell_overview akzeptiert jetzt auch 'placed'/'purchased' als Anchor-Types → Buy-Events auf Sell-Tab werden korrekt als Buy erkannt

### Bonus: UI Inference (buy_overview only)

Wenn nur 'placed' ohne 'transaction' auf buy_overview + UI zeigt ordersCompleted > 0 → inferiere gekaufte Menge aus UI-Metriken

### Implementation

- `tracker.py` lines 575-578: primary_types_global für sell_overview + 'placed'/'purchased'
- `tracker.py` lines 724-732: Mixed Context Detection mit Warning-Log
- `tracker.py` lines 818-854: UI Inference

### Known Limitations

- Wenn Transaction-Zeile bereits VOR erstem Scan rausfällt UND User wechselt Tab, wird nur Placed-Info gespeichert
- **Mitigation:** Poll-Interval 0.5s + Mixed Context Detection erfassen >95% der Fälle

### Result

- Grim Reaper's Elixir korrekt getrackt (full context) ✅
- Lion Blood getrackt aber nur mit Placed-Info (Transaction-Zeile war bereits raus) ⚠️

---

## 2025-10-12: Multiple Purchased Events Support

**Kategorie:** Critical Bugfix  
**Tests:** test_multiple_purchased.py

### Problem

Zwei purchased-Events (5000x Snowfield Cedar Sap für 196M und 195.9M Silver) mit gleichem Item+Timestamp → nur eine Transaktion gespeichert.

**Root Cause:** Cluster-Building verwendete Cluster-Key (item_lc, ts_key) OHNE Preis → beide Purchased-Events wurden in einen Cluster gruppiert

**Rule Violation:** "Eine purchased-Zeile steht IMMER für sich alleine und braucht bzw hat keinen Kontext"

### Solution

Cluster-Key für purchased-Events erweitert zu (item_lc, ts_key, price) → jedes purchased mit unterschiedlichem Preis ist jetzt ein eigener Cluster

### Additional Fix

Deque-API-Kompatibilität: `.add()` → `.append()` (4 Stellen in tracker.py) - collections.deque hat keine .add()-Methode

### Implementation

- `tracker.py` lines 593-645: Purchased-Events handling
- Purchased-Events mit price=None werden übersprungen
- Mit price werden standalone ohne Clustering behandelt

### Validation

- beide Transaktionen (196M & 195.9M) korrekt gespeichert ✅
- Regression Test: alle 5 Performance-Optimierungen weiterhin funktional ✅

---

## 2025-10-12: Performance Quick Fixes (5 Optimierungen)

**Kategorie:** Performance  
**Impact:** ~20-30% Gesamtperformance-Steigerung, stabile Memory-Usage

### 1. Memory-Leak-Fix

`seen_tx_signatures` von unbegrenztem Set zu `deque(maxlen=1000)` → stabile Memory-Usage bei Langzeitbetrieb

### 2. Item-Name-Cache

`@lru_cache(maxsize=500)` statt maxsize=1 → 50-70% schnellere Item-Korrektur bei wiederholten Namen

### 3. Log-Rotation

`ocr_log.txt` automatische Rotation bei 10MB Limit → verhindert Multi-GB Log-Dateien

### 4. Regex Pre-Compilation

Global kompilierte Patterns in `parsing.py` → 10-15% schnellere Parsing-Zeit

### 5. Database-Indizes

4 neue Indizes (item_name, timestamp, transaction_type, delta_detection) → 30-40% schnellere DB-Queries

### Dokumentation

- `docs/PERFORMANCE_ANALYSIS_2025-10-12.md` - Detaillierte Analyse
- `scripts/benchmark_performance.py` - Benchmark-Script
- `docs/QUICK_FIXES_IMPLEMENTED_2025-10-12.md` (archiviert)

---

## 2025-10-11: Tracking & Historical Transactions V3

**Kategorie:** Critical Fixes  
**Tests:** ALL 22 Tests bestehen (100%)

### Problem

"Gar nichts mehr getrackt" nach letzten Änderungen

### Fix 1: OCR Confidence Robustness

`extract_text()` handelt jetzt EasyOCR returning 2-Tupel (bbox,text) ODER 3-Tupel (bbox,text,conf) → keine 'not enough values to unpack' Fehler mehr

### Fix 2: Cluster-Building Refactor (ARCHITECTURAL CHANGE)

**OLD:** `for anchor: find related → process` (Problem: Placed+Withdrew ohne Transaction verarbeitet)  
**NEW:** `build clusters_dict → for cluster: process` (Lösung: Placed+Withdrew+Transaction in EINEM Cluster)

### Fix 3: Historical Detection V3

ALLE Transaktionen erlaubt als Anchors (nicht nur most_likely_buy) → Side via Item-Kategorie bestimmen (config/item_categories.csv)

### Fix 4: Sell-Side Filtering Enhancement

Allow SELL on buy_overview wenn Item in most_likely_sell → captured historical Sell-Transaktionen (z.B. Crystal of Void Destruction)

### Debug Tools

- `calibrate_region.py` - Region-Verification
- `test_historical_fix.py` - 3-Transaction Integration Test
- `test_parsing_crystal.py` - Parsing-Verification

### Test Results

Wild Grass x1111 + Sealed Black Magic Crystal x468 + Crystal of Void Destruction x1 korrekt gespeichert ✅

---

## 2025-10-11: Monitoring & Testing Suite

**Kategorie:** Infrastructure

### OCR-Confidence-Logging

EasyOCR gibt jetzt Confidence-Werte zurück (avg/min/max), Warnung bei <0.5, automatisches Logging in ocr_log.txt

### GUI Status-Indikator

Ampel-System (🟢 Healthy / 🟡 Warning / 🔴 Error) basierend auf error_count, Update alle 500ms, automatische Erholung

### Basic Test Runner

`scripts/run_all_tests.py` führt alle test_*.py aus, sammelt Ergebnisse, Unicode-Fix für Windows

---

## 2025-10-11: Architecture & Stability Sprint

**Kategorie:** Foundation  
**Impact:** Stabile Foundation für alle Features

### Major Changes

1. **Historical Transaction Detection V2:** Item-Kategorien (config/item_categories.csv) mit most_likely_buy/sell für korrekte Buy/Sell-Zuordnung

2. **Window Detection Simplified:** Es ist IMMER nur EIN Tab sichtbar (Buy ODER Sell) → 'Sales Completed' = sell_overview, 'Orders Completed' = buy_overview (OCR-tolerant: 'pleted' akzeptiert)

3. **Delta-Detection DB Check:** DB-Prüfung statt nur Text-Baseline verhindert Skip von echten neuen Transaktionen

4. **OCR V2 (Fixed for Game-UIs):** Sanftes Preprocessing ohne aggressive Binarisierung; CLAHE clipLimit=1.5, leichte Schärfung, Helligkeit/Kontrast-Anpassung; ROI-Detection; balancierte EasyOCR-Parameter

5. **Stop Button Responsiveness:** Interruptible Sleep (100ms Chunks) ermöglicht schnelle Reaktion <200ms

6. **Persistent Baseline & Reduced Poll Interval:** tracker_state DB-Tabelle speichert Baseline persistent → Delta-Detection überlebt App-Restart; Poll-Interval auf max 0.5s reduziert

7. **Intelligent Timestamp Assignment:** Timestamp-Cluster-Erkennung am Anfang des OCR-Texts mit Index-basierter Zuordnung (1. Event → 1. TS)

8. **First Snapshot Improvements:** 10min Zeitfenster für historische Logs; nur ECHTER Timestamp-Drift wird korrigiert

9. **Buy-Inferenz aus Placed+Withdrew:** Teilkauf als collect inferiert (quantity = placed − withdrew) NUR bei identischem Einheitspreis

10. **Preis-Fallback mit OCR-Fehler-Korrektur:** UI-Metriken-basiert (Buy/Sell Formeln); zusätzlich fehlende führende Ziffern korrigiert

---

**Last Updated:** 2025-10-12  
**Version:** 0.2.3
