# Test Suite Overview

**Status:** 29/32 Tests bestehen (90%)  
**Last Run:** 2025-10-12  
**Deprecated:** 3 Tests müssen aktualisiert/archiviert werden

## 🧪 Aktive Tests (scripts/) - 29 PASS

### Integration & User-Szenarien (5 Tests)
- ✅ **test_exact_user_scenario.py** - Reales User-Szenario aus Production
- ✅ **test_fast_action_timing.py** - Fast Action Timing (Tab-Wechsel während Transaction)
- ✅ **test_integration.py** - End-to-End Integration Tests
- ✅ **test_user_scenario_magical_shard.py** - Magical Shard mit OCR-Fehler-Recovery
- ⚠️ **test_user_scenario_lion_blood.py** - DEPRECATED (OCR 'f Lion Blood' wird rejected)

### Market Data & API (4 Tests)
- ✅ **test_bdo_api.py** - BDO World Market API Integration
- ✅ **test_market_data_integration.py** - Live API Preis-Validierung
- ✅ **test_market_json_system.py** - market.json Item-ID Lookup
- ✅ **test_garmoth_api.py** - Garmoth API (legacy, minimal)

### Feature-spezifische Tests (8 Tests)
- ✅ **test_historical_fix.py** - Historical Transaction Detection V3
- ✅ **test_historical_placed_with_ui_overview.py** - UI-Overview Interference Fix
- ✅ **test_multiple_purchased.py** - Multiple Purchased Events (unterschiedliche Preise)
- ✅ **test_preorder_and_exact_match.py** - Preorder-Detection + Exact Name Match
- ✅ **test_item_validation.py** - Strikte Item-Whitelist + OCR-Korrektur
- ✅ **test_quantity_bounds.py** - Quantity Limits [1, 5000]
- ✅ **test_quick_fixes.py** - Performance-Optimierungen (Memory, Cache, DB-Indizes)
- ✅ **test_gem_of_void.py** - Gem of Void Parsing (OCR xlO → x10)

### Parsing & OCR (7 Tests)
- ✅ **test_parsing_crystal.py** - Parsing Edge-Cases (Crystal-Items, OCR-Fehler)
- ✅ **test_magical_shard_fix_final.py** - Anchor-Priorität (Listed+Transaction)
- ✅ **test_magical_shard_missing.py** - Magical Shard 200x Recovery
- ✅ **test_price_plausibility.py** - Preis-Plausibilitätsprüfung (fehlende führende Ziffern)
- ✅ **test_spaces_in_price.py** - OCR-Leerzeichen in Preisen ('585, 585, OO0')
- ✅ **test_price_with_spaces.py** - Legacy Preis-Parsing Test
- ⚠️ **test_listed_fix_targeted.py** - DEPRECATED (Anchor-Priorität ersetzt diese Logik)

### Transaction Cases & Clustering (3 Tests)
- ⚠️ **test_listed_transaction_fix.py** - DEPRECATED (redundant mit test_magical_shard_fix_final)
- ✅ **test_monks_branch_issue.py** - UI-Fallback bei Relist (Monk's Branch Problem)
- ✅ **test_ui_fallback_fix.py** - UI-Fallback NUR bei Collect
- ✅ **test_ui_fallback_qty_fix.py** - UI-Fallback verwendet Transaction-Menge

### Window Detection (1 Test)
- ✅ **test_window_detection.py** - Window-Type Detection (sell/buy overview/item)

### Utils & Helpers (3 Tests)
- ✅ **test_utils.py** - Utility-Funktionen (Fuzzy-Matching, Preprocessing, etc.)
- ✅ **test_black_stone_powder_debug.py** - Black Stone Powder Parsing
- ✅ **test_end_to_end.py** - End-to-End System Workflow

### Check & Verification (2 Tests)
- ✅ **check_gem_of_void_db.py** - DB Verification für Gem of Void
- ✅ **check_monks_branch.py** - Monk's Branch Issue Verification

### Test-Runner
- **run_all_tests.py** - Führt alle Tests aus, sammelt Ergebnisse, Unicode-Fix

## 📦 Archivierte Tests (scripts/archive/)

Diese Tests waren für spezifische Bugfixes/Features und sind jetzt durch neuere Tests ersetzt:

- test_comprehensive_timestamp_fixes.py
- test_delta_detection.py
- test_first_snapshot.py
- test_first_snapshot_fix.py
- test_historical_transaction.py
- test_historical_v2.py
- test_infer_partial_buy.py
- test_ocr_improvements.py
- test_parsing_debug.py
- test_parsing_usercase.py
- test_persistent_baseline.py
- test_price_correction.py
- test_process.py
- test_quick_stop.py
- test_ui_metrics.py
- test_user_scenario.py (ersetzt durch test_exact_user_scenario.py)

## 🛠️ Utility Scripts (scripts/utils/)

### Debug & Kalibrierung
- **calibrate_region.py** - Region-Kalibrierung (DEFAULT_REGION validieren)
- **compare_ocr.py** - OCR-Methoden vergleichen (EasyOCR vs Tesseract vs Both)
- **debug_window.py** - Window-Detection debuggen
- **debug_timestamp_positions.py** - Timestamp-Positionen analysieren

### Database
- **dedupe_db.py** - Datenbank deduplizieren
- **reset_db.py** - Datenbank zurücksetzen

### Parsing
- **smoke_parsing.py** - Quick Parsing Smoke-Test

### Misc
- **fix_test_unicode.py** - Unicode-Probleme in Tests fixen (Windows)

## 📊 Test-Kategorien nach Priorität

### 1. Kritische Bugfixes (MUST-PASS) - 6 Tests
✅ test_preorder_and_exact_match.py - Preorder vs echter Kauf  
✅ test_item_validation.py - Item-Name Whitelist  
✅ test_historical_placed_with_ui_overview.py - UI-Overview Interference  
✅ test_multiple_purchased.py - Multiple Purchased Events  
✅ test_magical_shard_fix_final.py - Anchor-Priorität Fix
✅ test_spaces_in_price.py - OCR-Leerzeichen in Preisen

### 2. Market Data & API (MUST-PASS) - 3 Tests
✅ test_market_data_integration.py - Live API Preis-Validierung
✅ test_market_json_system.py - Item-ID Lookup
✅ test_bdo_api.py - BDO API Integration

### 3. Feature-Validierung (HIGH-PRIORITY) - 7 Tests
✅ test_historical_fix.py - Historical Detection V3  
✅ test_fast_action_timing.py - Mixed Context Detection  
✅ test_quantity_bounds.py - Quantity Limits  
✅ test_quick_fixes.py - Performance-Optimierungen  
✅ test_price_plausibility.py - Preis-Plausibilität
✅ test_monks_branch_issue.py - UI-Fallback bei Relist
✅ test_ui_fallback_qty_fix.py - UI-Fallback Menge

### 4. Core-Funktionalität (MEDIUM-PRIORITY) - 5 Tests
✅ test_window_detection.py - Window-Type Detection  
✅ test_parsing_crystal.py - Parsing Edge-Cases  
✅ test_utils.py - Utility-Funktionen  
✅ test_gem_of_void.py - Gem of Void Parsing
✅ test_magical_shard_missing.py - Magical Shard Recovery

### 5. End-to-End (HIGH-PRIORITY) - 4 Tests
✅ test_exact_user_scenario.py - Production-Szenario  
✅ test_user_scenario_magical_shard.py - Magical Shard mit OCR-Fehler
✅ test_integration.py - Integration Tests
✅ test_end_to_end.py - Complete System Workflow

### 6. UI & Fallback (MEDIUM-PRIORITY) - 2 Tests
✅ test_ui_fallback_fix.py - UI-Fallback NUR bei Collect
✅ test_black_stone_powder_debug.py - Black Stone Powder Debug

### 7. DEPRECATED (ARCHIVIEREN/UPDATEN) - 3 Tests
⚠️ test_user_scenario_lion_blood.py - OCR 'f Lion Blood' wird rejected (Whitelist-Validierung funktioniert)
⚠️ test_listed_fix_targeted.py - Anchor-Priorität ersetzt diese Logik
⚠️ test_listed_transaction_fix.py - Redundant mit test_magical_shard_fix_final  

## 🚀 Test ausführen

```bash
# Alle Tests (29/32 PASS, 3 deprecated)
python scripts/run_all_tests.py

# Einzelner Test
python scripts/test_exact_user_scenario.py

# Performance-Benchmark
python scripts/benchmark_performance.py --iterations 10

# Mit Debug-Output
python scripts/test_historical_fix.py
```

## 📋 Empfohlene Actions

### Sofort (Deprecated Tests)
1. **test_user_scenario_lion_blood.py** → Archivieren in scripts/archive/
   - 'f Lion Blood' wird korrekt durch Whitelist-Validierung rejected
   - Funktionalität bereits durch test_item_validation.py abgedeckt

2. **test_listed_fix_targeted.py** → Archivieren in scripts/archive/
   - Anchor-Priorität (test_magical_shard_fix_final) ersetzt diese Logik
   - Redundant, alte Implementierung

3. **test_listed_transaction_fix.py** → Archivieren in scripts/archive/
   - Redundant mit test_magical_shard_fix_final.py
   - Abgedeckt durch neueren, umfassenderen Test

### Mittelfristig (Test Coverage)
- Systematische Test-Review: Edge-Cases dokumentieren
- Regression-Tests für GPU-Performance
- Mock-Tests für BDO API (ohne Live-Daten)
- Load-Tests für Langzeitbetrieb

## 📝 Neuen Test hinzufügen

1. Datei erstellen: `scripts/test_<feature_name>.py`
2. Struktur:
   ```python
   import sys
   import os
   sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
   
   from tracker import MarketTracker
   from database import reset_database
   
   def test_<feature>():
       # Setup
       reset_database()
       mt = MarketTracker(debug=True)
       
       # Test
       text = "..."
       mt.process_ocr_text(text)
       
       # Assertions
       assert condition, "Error message"
       
       print("✅ Test passed")
   
   if __name__ == "__main__":
       test_<feature>()
   ```
3. In `run_all_tests.py` registrieren (falls gewünscht)

## 🐛 Debugging fehlgeschlagener Tests

1. **OCR-Probleme:**
   - Prüfe `ocr_log.txt`
   - Vergleiche `debug_proc.png` vs `debug_orig.png`
   - Nutze `scripts/utils/compare_ocr.py`

2. **Parsing-Fehler:**
   - Debug-Flag aktivieren: `MarketTracker(debug=True)`
   - Nutze `scripts/utils/smoke_parsing.py`

3. **Window-Detection:**
   - Nutze `scripts/utils/debug_window.py`
   - Prüfe `ocr_log.txt` für "Window changed"

4. **Database-Probleme:**
   - Reset: `python scripts/utils/reset_db.py`
   - Dedupe: `python scripts/utils/dedupe_db.py`

## 📈 Test-Coverage

| Kategorie | Tests | Passing | Status |
|-----------|-------|---------|--------|
| Kritische Bugfixes | 6 | 6 | ✅ 100% |
| Market Data & API | 3 | 3 | ✅ 100% |
| Feature-Validierung | 7 | 7 | ✅ 100% |
| Core-Funktionalität | 5 | 5 | ✅ 100% |
| End-to-End | 4 | 4 | ✅ 100% |
| UI & Fallback | 2 | 2 | ✅ 100% |
| Utils & Helpers | 3 | 3 | ✅ 100% |
| Deprecated | 3 | 0 | ⚠️ 0% (archivieren) |
| **TOTAL** | **32** | **29** | **✅ 90%** |

### Test-Health-Status
- ✅ **29 Tests PASS** - Kernfunktionalität stabil
- ⚠️ **3 Tests DEPRECATED** - Müssen archiviert werden
- 🎯 **Target:** 100% nach Archivierung (29/29)

---

**Last Updated:** 2025-10-12  
**Next Review:** Nach Archivierung der 3 deprecated Tests
