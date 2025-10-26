# Implementierungsplan: Relist Detail-Window Fix

**Datum:** 26. Oktober 2025  
**Branch:** feature/detail-window-capture  
**Issue:** Detail-Window State-Fehler bei Relist-Operationen führt zu fehlenden Listings und AttributeErrors

---

## Zusammenfassung

Bei Relist-Operationen im Autotrack-Modus tritt ein kritischer Fehler auf:
- Detail-Window State wird nicht korrekt initialisiert (`_reset_detail_window_state` fehlt)
- Neue Listings werden nicht in der DB gespeichert
- Auto-Collect schlägt mit falschem Keyword (`tx_id` statt `transaction_id`) fehl
- Multiple AttributeErrors blockieren die gesamte Pipeline

**Test-Szenario:**
1. Warehouse: 2050 Magical Shard
2. Click "Relist" auf 122×Magical Shard @ 381,020,640 (netto)
3. Neues Listing: 200×@ 706,000,000 (brutto)
4. Erwartet: Altes Listing collected, neues gespeichert
5. Tatsächlich: AttributeError, kein neues Listing, altes Listing bleibt aktiv

---

## Phase 1: Detail-State Wiederherstellung

### 1.1 `_reset_detail_window_state` Methode implementieren
**Datei:** `tracker.py`

**Aufgaben:**
- [ ] Neue Methode `_reset_detail_window_state()` erstellen
- [ ] Alle Detail-Window Flags zurücksetzen:
  - `_detail_window_active`
  - `_detail_baseline_balance`
  - `_detail_cached_input_fields`
  - `_detail_partial_*` (alle partiellen State-Variablen)
  - `_pending_metrics_refresh`
  - `_log_capture_failed`
  - `_detail_last_metrics`
  - `_detail_warehouse_delta`
  - `_detail_balance_delta`

**Code-Struktur:**
```python
def _reset_detail_window_state(self):
    """Reset all detail window state variables to initial values."""
    self._detail_window_active = False
    self._detail_baseline_balance = None
    self._detail_baseline_warehouse = None
    self._detail_cached_input_fields = {}
    self._detail_partial_fields = {}
    self._pending_metrics_refresh = False
    self._log_capture_failed = False
    self._detail_last_metrics = None
    self._detail_warehouse_delta = 0
    self._detail_balance_delta = 0
    # Weitere State-Variablen...
```

**Aufrufstellen:**
- [ ] `__init__` (einmalig bei Initialisierung)
- [ ] Zeile ~4127 (bestehende Referenz)
- [ ] Zeile ~4241 (bestehende Referenz)
- [ ] Zeile ~5137 (bestehende Referenz)
- [ ] Zeile ~5295 (bestehende Referenz)

**Akzeptanzkriterien:**
- ✅ Keine AttributeErrors mehr in `ocr_log.txt`
- ✅ Detail-Window öffnet ohne Crashes
- ✅ Alle Flags sind bei jedem Window-Wechsel definiert

---

## Phase 2: Detail-Baseline & Listing-Erkennung

### 2.1 `_monitor_detail_window` für sell_item stabilisieren
**Datei:** `tracker.py`

**Aufgaben:**
- [ ] Verifizieren dass `_monitor_detail_window` bei `sell_item` korrekt triggert
- [ ] Baseline-Erfassung sicherstellen:
  - Warehouse-Wert: Soll 2050 im Test-Szenario lesen
  - Fallback wenn `Warehouse=None`: Verwende letzten gültigen Wert
- [ ] Delta-Berechnung nach Listing-Aktion:
  - Nach −200 Delta muss `_detect_listing_placement` triggern
  - Balance-Delta für collected Items erfassen (+122)

**Guards hinzufügen:**
```python
# In _monitor_detail_window
if self._detail_baseline_warehouse is None and last_valid_warehouse:
    self._detail_baseline_warehouse = last_valid_warehouse
    
if warehouse_delta and abs(warehouse_delta) > 0:
    self._detect_listing_placement(item_name, warehouse_delta, ...)
```

**Akzeptanzkriterien:**
- ✅ Baseline wird im ersten Frame nach Detail-Window-Öffnung gesetzt
- ✅ Delta-Berechnung funktioniert auch bei verzögerten OCR-Frames
- ✅ `_detect_listing_placement` wird bei neuen Listings ausgelöst

### 2.2 Unit-Test für sell_item Detail-Window
**Datei:** `tests/unit/test_sell_detail_window.py`

**Aufgaben:**
- [ ] Test erstellen der sell_item OCR simuliert
- [ ] Mock-Daten: "Magical Shard", Warehouse=2050, Delta=−200
- [ ] Prüfen dass `_detect_listing_placement` aufgerufen wird
- [ ] Prüfen dass `store_listing` Insertion auslöst

```python
def test_sell_item_triggers_listing_detection():
    """Test that sell_item window correctly triggers listing detection."""
    # Setup: Mock OCR results with Magical Shard
    # Assert: _detect_listing_placement called
    # Assert: store_listing creates new DB entry
```

---

## Phase 3: Auto-Collect API korrigieren

### 3.1 Keyword-Fehler beheben
**Datei:** `tracker.py` (Zeile ~1603ff.)

**Aufgaben:**
- [ ] Aufruf in `_handle_preorder_or_listing_collection` korrigieren
  - **Alt:** `mark_listing_collected(..., tx_id=...)`
  - **Neu:** `mark_listing_collected(..., transaction_id=...)`
- [ ] Alternative: `PreorderManager.mark_listing_collected` erweitern
  - Beide Keywords akzeptieren (Kompatibilität)
  - Deprecation-Warning für `tx_id`

**Code-Änderung:**
```python
# Option 1: Direkter Fix
self.preorder_manager.mark_listing_collected(
    listing_id=listing_id,
    transaction_id=tx_id,  # Korrektes Keyword
    collected_at=datetime.now()
)

# Option 2: API-Erweiterung in PreorderManager
def mark_listing_collected(self, listing_id, transaction_id=None, tx_id=None, ...):
    if tx_id and not transaction_id:
        warnings.warn("tx_id deprecated, use transaction_id", DeprecationWarning)
        transaction_id = tx_id
```

**Akzeptanzkriterien:**
- ✅ Kein TypeError mehr bei Auto-Collect
- ✅ Listing wird korrekt als collected markiert

### 3.2 Auto-Collect Test
**Datei:** `tests/unit/test_listing_auto_collect.py` (neu)

**Aufgaben:**
- [ ] Fake-Listing in Test-DB anlegen
- [ ] `_handle_preorder_or_listing_collection` triggern
- [ ] Prüfen:
  - Status = 'collected'
  - `collected_at` gesetzt
  - Cache invalidiert

```python
def test_auto_collect_marks_listing_correctly():
    """Test that auto-collect marks listing as collected with correct params."""
    # Setup: Insert fake listing in DB
    # Trigger: _handle_preorder_or_listing_collection
    # Assert: listing.status == 'collected'
    # Assert: transaction entry created
```

---

## Phase 4: Listing Speichern & Schließen

### 4.1 `_detect_listing_placement` Integration
**Datei:** `tracker.py`

**Aufgaben:**
- [ ] Sicherstellen dass `_detect_listing_placement` beide Aktionen ausführt:
  1. Altes Listing auto-collecten (ID 18 im Test-Szenario)
  2. Neues Listing speichern (200×@ 706M brutto)
- [ ] In `store_listing` Logik prüfen:
  - Alte Listing-ID wird auf `collected` gesetzt
  - Neue Listing-ID wird als `active` angelegt
  - Korrekte Preise (brutto → netto Konvertierung)

**Code-Flow:**
```python
def _detect_listing_placement(self, item_name, warehouse_delta, ...):
    # 1. Auto-collect alte Listings
    old_listings = self._find_matching_listings(item_name)
    for old in old_listings:
        self._handle_preorder_or_listing_collection(old)
    
    # 2. Neues Listing speichern
    new_listing = {
        'item_name': item_name,
        'quantity': abs(warehouse_delta),
        'price': self._cached_price_brutto,
        'status': 'active'
    }
    self.preorder_manager.store_listing(new_listing)
```

**Akzeptanzkriterien:**
- ✅ Alte Listing: `status='collected'`, `collected_at` gesetzt
- ✅ Neue Listing: `status='active'`, korrekte Quantity/Price
- ✅ Transaction-Eintrag für collected Items (122×381,020,640 netto)

### 4.2 Logging & Duplicate-Guards
**Datei:** `preorder_manager.py`

**Aufgaben:**
- [ ] Optional: Logging in `store_listing` aktivieren
  - Log bei Auto-Collect: "Auto-collected listing_id={old_id}"
  - Log bei Neu-Anlage: "Created new listing_id={new_id}"
- [ ] TTL-basierte Duplicate-Guards (analog Preorder-Logik):
  - Verhindert doppelte Listings innerhalb von 5 Sekunden
  - Cache: `{item_name}_{quantity}_{price}: timestamp`

**Akzeptanzkriterien:**
- ✅ Klare Log-Messages bei Listing-Operationen
- ✅ Keine Duplikate bei schnellen Relist-Aktionen

---

## Phase 5: Integration & Validierung

### 5.1 Integrierter Szenario-Test
**Test:** Magical Shard Relist (manuell)

**Schritte:**
1. [ ] Warehouse vorbereiten: 2050 Magical Shard
2. [ ] Autotrack starten
3. [ ] Relist durchführen:
   - Click Relist auf 122×Magical Shard
   - Neues Listing: 200×@ 706,000,000
4. [ ] Validierung:
   - [ ] `ocr_log.txt`: Keine AttributeErrors
   - [ ] `ocr_log.txt`: Baseline=2050, Delta=−200 erkannt
   - [ ] DB-Tabelle `listings`:
     - Zeile 1: ID 18, status='collected', quantity=122
     - Zeile 2: Neue ID, status='active', quantity=200
   - [ ] DB-Tabelle `transactions`:
     - Eintrag: 122×381,020,640 netto (Sale)

### 5.2 Unit-Tests ausführen
**Dateien:**
- `tests/unit/test_sell_detail_window.py`
- `tests/unit/test_listing_auto_collect.py`
- `tests/manual/test_magical_shard_fix_final.py`

**Kommando:**
```powershell
python scripts/run_all_tests.py
```

**Akzeptanzkriterien:**
- ✅ Alle Unit-Tests bestehen
- ✅ Keine Regressions-Fehler in bestehenden Tests

### 5.3 Manuelle Autotrack-Session
**Durchführung:**
1. [ ] Mehrere Relist-Operationen hintereinander
2. [ ] Verschiedene Items (Magical Shard, Mushroom, etc.)
3. [ ] Verschiedene Mengen (klein, groß, Edge-Cases)

**Validierung:**
- [ ] `ocr_log.txt` ohne Fehler
- [ ] DB-Konsistenz (alte collected, neue active)
- [ ] Keine fehlenden Listings

---

## Phase 6: Dokumentation & Cleanup

### 6.1 Code-Dokumentation
**Dateien:** `tracker.py`, `preorder_manager.py`

**Aufgaben:**
- [ ] Docstrings für `_reset_detail_window_state`
- [ ] Kommentare bei Auto-Collect-Logik
- [ ] Type-Hints prüfen und ergänzen

### 6.2 Repository-Guidelines aktualisieren
**Datei:** `docs/performance_optimization_plan.md` oder neues Dokument

**Aufgaben:**
- [ ] Dokumentieren:
  - Detail-Window State-Management
  - Listing Auto-Collect Pipeline
  - Relist-Workflow (Step-by-Step)
- [ ] Troubleshooting-Sektion:
  - AttributeErrors beim Detail-Window
  - Fehlende Listings nach Relist

### 6.3 Release Notes
**Datei:** `release_notes.txt`

**Eintrag hinzufügen:**
```
## [Version X.X.X] - 2025-10-26

### Fixed
- Detail-Window State wird jetzt korrekt initialisiert (keine AttributeErrors mehr)
- Relist-Operationen speichern neue Listings korrekt in der DB
- Auto-Collect verwendet korrektes API-Keyword (transaction_id)
- Warehouse-Baseline wird auch bei verzögertem OCR korrekt erfasst

### Added
- Duplicate-Guards für Listing-Operationen (TTL-basiert)
- Erweiterte Logging für Auto-Collect Pipeline
- Unit-Tests für sell_item Detail-Window
```

---

## Reihenfolge der Umsetzung

1. **Phase 1** (Kritisch): Detail-State Fix → Blockiert alles andere
2. **Phase 3.1** (Schnell): Keyword-Fix → Einfache API-Korrektur
3. **Phase 2** (Core-Logik): Baseline & Listing-Erkennung
4. **Phase 4** (Integration): Listing Speichern & Auto-Collect
5. **Phase 3.2 & 2.2** (Tests): Unit-Tests parallel zur Entwicklung
6. **Phase 5** (Validierung): Integration & Manuelle Tests
7. **Phase 6** (Cleanup): Dokumentation & Release

---

## Geschätzte Aufwände

| Phase | Aufwand | Priorität |
|-------|---------|-----------|
| Phase 1 | 2-3h | P0 (Kritisch) |
| Phase 3.1 | 30min | P0 (Kritisch) |
| Phase 2 | 3-4h | P1 (Hoch) |
| Phase 4 | 2-3h | P1 (Hoch) |
| Phase 3.2 & 2.2 | 2-3h | P2 (Mittel) |
| Phase 5 | 2-3h | P2 (Mittel) |
| Phase 6 | 1-2h | P3 (Niedrig) |
| **Gesamt** | **13-18h** | |

---

## Risiken & Mitigationen

| Risiko | Wahrscheinlichkeit | Auswirkung | Mitigation |
|--------|-------------------|------------|------------|
| Detail-State enthält mehr Variablen als dokumentiert | Mittel | Hoch | Vollständige Code-Analyse, alle `_detail_*` finden |
| OCR-Timing-Issues bei Baseline-Erfassung | Mittel | Mittel | Fallback auf letzten gültigen Wert, Guards |
| Bestehende Tests brechen | Niedrig | Mittel | Regressions-Tests vor Commit |
| DB-Schema-Inkonsistenzen | Niedrig | Hoch | Backup vor Tests, Schema-Validation |

---

## Erfolgskriterien

**Must-Have:**
- ✅ Keine AttributeErrors mehr in `ocr_log.txt`
- ✅ Relist erstellt neues Listing in DB
- ✅ Altes Listing wird korrekt als collected markiert
- ✅ Transaction-Eintrag für collected Items

**Should-Have:**
- ✅ Alle Unit-Tests bestehen
- ✅ Manuelle Autotrack-Session ohne Fehler
- ✅ Dokumentation aktualisiert

**Nice-to-Have:**
- ✅ Duplicate-Guards implementiert
- ✅ Erweiterte Logging-Optionen
- ✅ Performance-Metriken (Detail-Window-Latency)

---

## Nächste Schritte

1. Branch bestätigen: `feature/detail-window-capture`
2. Phase 1 starten: `_reset_detail_window_state` implementieren
3. Nach Phase 1: Commit + Push für Review
4. Parallele Arbeit an Phase 3.1 möglich (unabhängig)

**Start:** 26. Oktober 2025  
**Ziel-Fertigstellung:** 27-28. Oktober 2025
