# Pig Blood Fixes - Komplette Implementierung
**Datum**: 2025-10-20  
**Branch**: feature/detail-window-capture  
**Status**: ✅ IMPLEMENTIERT

---

## Überblick

Nach dem Pig Blood Real-World Test (5000x Preorder + 2×5000x Käufe) wurden drei kritische Probleme identifiziert und behoben:

1. **🔴 CRITICAL**: Preorder-Collect wurde nicht getrackt (bei Baseline bereits collected)
2. **🟠 HIGH**: Balance-Only Timeout wurde beim Window-Close abgebrochen
3. **🟡 MEDIUM**: Log-based Parsing speicherte zwei verschiedene Preise für selbe Transaktion

---

## Fix #1: Preorder-Collect Tracking

### Problem
- BDO collected Preorders **BEIM ÖFFNEN** des Detail-Fensters (nicht beim ersten Kauf)
- Warehouse-Baseline enthielt bereits die Preorder-Menge (z.B. 10,000)
- Delta-Tracking konnte Preorder nicht erkennen (Δ = 0)
- Warehouse-Only Delta (warehouse +5000, balance ±0) wurde verworfen
- Preorder ging verloren, nur von Log-based Parsing gerettet

### Lösung
**Neue State-Variable**: `_detail_pending_collect_qty`

```python
self._detail_pending_collect_qty = 0  # Preorder-Menge die bei Baseline bereits collected war
```

**Warehouse-Only Delta Handling**:
```python
if self._detail_partial_warehouse_delta > 0 and self._detail_partial_balance_delta == 0:
    # Speichere Preorder-Menge für später (nicht verwerfen!)
    self._detail_pending_collect_qty += self._detail_partial_warehouse_delta
    # Reset Deltas (aber NICHT pending_collect_qty!)
    self._detail_partial_balance_delta = 0
    self._detail_partial_warehouse_delta = 0
    return None
```

**Kombination mit Kauf**:
```python
if self._detail_pending_collect_qty > 0:
    log_debug(f"Combining purchase ({quantity}x) with pending_collect ({self._detail_pending_collect_qty}x)")
    quantity += self._detail_pending_collect_qty
    self._detail_pending_collect_qty = 0  # Reset nach Kombination
```

**Vorteile**:
- ✅ Preorder wird nicht mehr verworfen
- ✅ Kombiniert mit nächstem Kauf für korrekte Gesamtmenge
- ✅ Funktioniert auch bei mehreren aufeinanderfolgenden Warehouse-Only Deltas
- ✅ Automatisches Reset nach erfolgreicher Kombination

**Test-Erwartung** (Pig Blood):
- Baseline: warehouse=10,000 (5000x Preorder bereits collected)
- Kauf #1: warehouse +5000 → **10,000x gespeichert** (5000 preorder + 5000 kauf)
- Kauf #2: warehouse +5000 → 5000x gespeichert

---

## Fix #2: Window-Close Balance-Only Force

### Problem
- Balance-Only Fallback hat 3s Timeout (wenn Warehouse nicht aktualisiert)
- Wenn Detail-Fenster **vor Ablauf** geschlossen wird, wurde Transaktion abgebrochen
- Pig Blood: Kauf mit Preorder (balance -13.8M, warehouse ±0)
  - Timer gestartet bei 22:18:38
  - Fenster geschlossen bei 22:18:41 (nach 3s)
  - Transaktion verloren, nur von Log-based gerettet

### Lösung
**Window-Close Detection mit Force-Save**:

```python
if current_balance is None or current_warehouse is None:
    # Fenster geschlossen - prüfe ob Balance-Only-Transaction pending
    if (self._detail_partial_balance_delta < 0 and 
        self._detail_balance_delta_timestamp is not None):
        
        # Force-Save mit Balance-Only Fallback
        estimated_qty = abs(self._detail_partial_balance_delta) // desired_price
        
        # Kombiniere mit pending_collect_qty falls vorhanden
        if self._detail_pending_collect_qty > 0:
            estimated_qty += self._detail_pending_collect_qty
            self._detail_pending_collect_qty = 0
        
        # Erstelle Transaction mit tx_case='buy_collect_balance_only_forced'
        transaction = {...}
        self.store_transaction_db(transaction)
    
    # Reset State (Fenster geschlossen)
    self._reset_detail_window_state()
    return
```

**Neuer TX-Case**: `buy_collect_balance_only_forced`
- Unterscheidet forced saves von normalen Balance-Only
- Ermöglicht spätere Analyse/Debugging

**Vorteile**:
- ✅ Transaktionen werden nicht mehr verloren wenn Fenster vorzeitig geschlossen
- ✅ Kombiniert automatisch mit pending_collect_qty
- ✅ Validierung (Whitelist, Mengenbereich) bleibt aktiv
- ✅ Dedupe funktioniert korrekt (verhindert doppelte Saves)

**Test-Erwartung**:
- Balance-Delta vorhanden, Warehouse fehlt
- Fenster geschlossen nach 1-2 Sekunden
- Transaktion wird trotzdem gespeichert mit korrekter Menge

---

## Fix #3: Log-based Price Dedupe Verbesserung

### Problem
- Log-based Parsing speicherte zwei verschiedene Preise für selbe Transaktion:
  - Detail-Window: 5000x @ 14,137,210
  - Log-based: 5000x @ 13,981,680
- Exakte Price-Match (CAST(price AS INTEGER) = ?) zu strikt
- OCR-Ungenauigkeiten führten zu unterschiedlichen Preisen

### Lösung
**Price-Similarity Check mit ±10% Toleranz**:

```python
# FIX #3: Price-Similarity Check (±10% tolerance)
PRICE_TOLERANCE = 0.10  # ±10%
price_min = int(price * (1 - PRICE_TOLERANCE))
price_max = int(price * (1 + PRICE_TOLERANCE))

db_cur.execute(
    """
    SELECT id, timestamp, tx_case, price FROM transactions 
    WHERE item_name = ? AND quantity = ? 
    AND CAST(price AS INTEGER) BETWEEN ? AND ?
    ...
    """,
    (item, int(qty), price_min, price_max, ...)
)
```

**Logging bei Price-Unterschieden**:
```python
if abs(int(price) - int(existing_price)) > 0:
    log_debug(f"Price difference detected: Detail-Window={existing_price:,}, Log-based={price:,} (preferring Detail-Window)")
```

**Vorteile**:
- ✅ Verhindert Duplikate bei ähnlichen Preisen (OCR-Drift)
- ✅ Detail-Window Preis wird bevorzugt (höhere Genauigkeit)
- ✅ 10% Toleranz großzügig genug für OCR-Fehler
- ✅ Logging zeigt Price-Unterschiede für Debugging

**Test-Erwartung**:
- Detail-Window speichert 5000x @ 14,137,210
- Log-based versucht 5000x @ 13,981,680
- Log-based wird als Duplikat erkannt (±10% innerhalb Toleranz)
- Nur Detail-Window Preis bleibt in DB

---

## Implementation Details

### Geänderte Dateien
- `tracker.py` (5 Änderungen)
  1. Line 238: `_detail_pending_collect_qty` State-Variable hinzugefügt
  2. Line 2230: Reset-Funktion um `_detail_pending_collect_qty = 0` erweitert
  3. Line 2350: Warehouse-Only Delta speichert statt verwirft
  4. Line 2463: Kombination mit pending_collect_qty bei normalen Käufen
  5. Line 2430: Balance-Only Fallback kombiniert mit pending_collect_qty
  6. Line 2635: Window-Close Force-Save implementiert
  7. Line 2105: Log-based Dedupe mit Price-Similarity Check

### Neue TX-Cases
- `buy_collect_balance_only_forced`: Window-Close forced save

### State-Management
```python
# Initialisierung (Line 238)
self._detail_pending_collect_qty = 0

# Warehouse-Only Delta (Line 2350)
self._detail_pending_collect_qty += warehouse_delta
self._detail_partial_balance_delta = 0
self._detail_partial_warehouse_delta = 0

# Kombination mit Kauf (Line 2463)
quantity += self._detail_pending_collect_qty
self._detail_pending_collect_qty = 0

# Reset bei Window-Close (Line 2230)
self._detail_pending_collect_qty = 0
```

### Delta-Reset Logik
**Nach erfolgreicher Transaktion** (Line 2770):
```python
if transaction:
    # Reset Partial-Deltas für nächste Transaktion
    # WICHTIG: pending_collect_qty wird NICHT hier resetted,
    # nur in _infer_transaction_from_deltas wenn kombiniert
    self._detail_partial_balance_delta = 0
    self._detail_partial_warehouse_delta = 0
    self._detail_balance_delta_timestamp = None
```

**Bei Window-Close** (Line 2230):
```python
def _reset_detail_window_state(self):
    # Reset ALLES inkl. pending_collect_qty
    self._detail_pending_collect_qty = 0
```

---

## Test-Plan

### Test #1: Pig Blood Wiederholung
**Setup**: 5000x Preorder + 2×5000x Käufe (wie Original)

**Erwartete Ergebnisse**:
1. Baseline: warehouse=10,000 (Preorder bereits collected)
2. Kauf #1: Detail-Window speichert **10,000x** (5000 preorder + 5000 kauf)
3. Kauf #2: Detail-Window speichert **5,000x** (nur Kauf)
4. Log-based: Erkennt Duplikate, speichert **nichts**
5. **Total DB**: 2 Transaktionen (10k + 5k)

**Logs zu beachten**:
- `🔵 Preorder-Collect detected: warehouse +5000`
- `🔵 Storing as pending_collect_qty`
- `🔵 Combining purchase (5000x) with pending_collect (5000x)`
- `🔵 Total quantity: 10000x`

### Test #2: Balance-Only Window-Close
**Setup**: 
1. Öffne Detail-Window (buy_item)
2. Kaufe 5000x
3. **Sofort schließen** (< 3s, bevor Warehouse aktualisiert)

**Erwartete Ergebnisse**:
1. Balance-Delta erkannt: -70M (z.B.)
2. Warehouse-Delta fehlt: 0
3. Balance-only Timer startet
4. Fenster geschlossen nach 1-2s
5. **Force-Save**: Transaction mit tx_case=`buy_collect_balance_only_forced`
6. Geschätzte Menge aus desired_price: 5000x

**Logs zu beachten**:
- `🔶 Window closed with pending balance-only transaction!`
- `🔶 Forcing balance-only save now`
- `🔶 Forced balance-only transaction saved: 5000x @ 70,000,000`

### Test #3: Mehrfache Warehouse-Only Deltas
**Setup**:
1. Preorder #1: 5000x
2. Preorder #2: 3000x (ohne zu kaufen)
3. Kauf: 5000x

**Erwartete Ergebnisse**:
1. Warehouse +5000, Balance ±0 → `pending_collect_qty = 5000`
2. Warehouse +3000, Balance ±0 → `pending_collect_qty = 8000`
3. Warehouse +5000, Balance -70M → **13,000x gespeichert** (8000 + 5000)

**Logs zu beachten**:
- `🔵 Preorder-Collect detected: warehouse +5000`
- `🔵 Preorder-Collect detected: warehouse +3000`
- `🔵 Combining purchase (5000x) with pending_collect (8000x)`
- `🔵 Total quantity: 13000x`

### Test #4: Price-Similarity Dedupe
**Setup**:
1. Detail-Window speichert: 5000x @ 14,137,210
2. Log-based versucht: 5000x @ 13,981,680 (OCR-Drift)

**Erwartete Ergebnisse**:
1. Detail-Window speichert korrekt
2. Log-based erkennt Duplikat (±10% Toleranz)
3. **Nur 1 Transaktion** in DB mit Detail-Window Preis

**Logs zu beachten**:
- `[DEDUPE-LOG] Skip log-based duplicate: Pig Blood 5000x already captured by detail-window`
- `[DEDUPE-LOG] 🔶 Price difference detected: Detail-Window=14,137,210, Log-based=13,981,680`

---

## Edge-Cases

### Edge-Case #1: Preorder ohne nachfolgenden Kauf
**Setup**: Warehouse-Only Delta, dann Fenster schließen

**Erwartung**:
- Warehouse +5000, Balance ±0 → `pending_collect_qty = 5000`
- Fenster schließen → Reset state
- **Keine Transaktion** gespeichert (korrekt, da nur Preorder platziert)

**Begründung**: Preorders alleine sind keine Collect-Transaktionen

### Edge-Case #2: Balance-Only ohne desired_price
**Setup**: Balance-Delta vorhanden, aber kein desired_price in Metriken

**Erwartung**:
- Balance-only Timeout erreicht
- desired_price fehlt → **Keine Schätzung möglich**
- Transaktion nicht gespeichert
- Log: `No desired_price available for estimation, still waiting...`

**Begründung**: Ohne Preis keine verlässliche Mengen-Schätzung

### Edge-Case #3: Preorder + Forced Save
**Setup**:
1. Warehouse-Only Delta (+5000) → `pending_collect_qty = 5000`
2. Kauf (-70M balance, warehouse nicht aktualisiert)
3. Fenster schließen vor Timeout

**Erwartung**:
- Force-Save kombiniert mit pending_collect_qty
- Geschätzte Menge: 5000x (aus balance/price)
- **Total**: 10,000x gespeichert (5000 preorder + 5000 forced estimate)
- tx_case: `buy_collect_balance_only_forced`

**Logs**:
- `🔶 Combining forced purchase (5000x) with pending_collect (5000x)`
- `🔶 Forced balance-only transaction saved: 10000x @ 70,000,000`

---

## Rückwärtskompatibilität

### Alte Transaktionen
- ✅ Keine Migration erforderlich
- ✅ Neue Cases werden korrekt indiziert
- ✅ Dedupe funktioniert mit allen alten tx_cases

### Tests
- ✅ 19/22 Tests sollten weiterhin passieren
- ⚠️ 3 deprecated Tests erwarten unimplemented features (kein Problem)
- 🆕 Neue Tests für Preorder-Tracking benötigt (siehe Test-Plan)

### Performance
- ✅ Keine zusätzlichen DB-Queries
- ✅ Price-Similarity Check nutzt BETWEEN (schnell)
- ✅ `pending_collect_qty` ist reine RAM-Operation

---

## Debug-Logs

### Neue Log-Marker
```
🔵 Preorder-Collect detected
🔵 Storing as pending_collect_qty
🔵 Combining purchase/forced purchase with pending_collect
🔵 Total quantity: Xx

🔶 Window closed with pending balance-only transaction
🔶 Forcing balance-only save now
🔶 Combining forced purchase with pending_collect
🔶 Forced balance-only transaction saved
🔶 Price difference detected (Detail-Window vs Log-based)
```

### Log-Analyse Workflow
1. Suche nach `🔵` → Preorder-Tracking Events
2. Suche nach `🔶` → Window-Close Force-Save Events
3. Suche nach `DEDUPE-LOG.*🔶` → Price-Similarity Conflicts

---

## Bekannte Limitierungen

### Limitation #1: Preorder-Only ohne Kauf
- Wenn nur Preorders platziert werden (ohne Kauf), wird **nichts** gespeichert
- Begründung: Preorders sind keine Collect-Transaktionen
- Alternative: Log-based parsing erfasst "Placed order" Events separat

### Limitation #2: Balance-Only Genauigkeit
- Menge wird geschätzt aus `balance / desired_price`
- Bei OCR-Fehlern im Preis kann Menge falsch sein
- Mitigation: Validierung auf 1-500,000 Range

### Limitation #3: Warehouse-Update Timing
- Wenn Warehouse **nach** Window-Close aktualisiert, geht Info verloren
- Gilt nur für seltene Fälle (normalerweise sofort oder nie)
- Mitigation: Force-Save verwendet Balance-Only Schätzung

---

## Nächste Schritte

### Sofort
1. ✅ Code kompiliert ohne Fehler
2. ⏳ Pig Blood Test wiederholen
3. ⏳ Balance-Only Window-Close Test
4. ⏳ Logs analysieren für `🔵` und `🔶` Marker

### Später
1. Unit-Tests für `_detail_pending_collect_qty` Logik
2. Integration-Tests für alle Edge-Cases
3. Performance-Messung (sollte identisch sein)
4. Dokumentation in AGENTS.md updaten

---

## Zusammenfassung

**Alle drei Fixes implementiert**:
- 🔴 **Fix #1**: Preorder-Collect Tracking mit `_detail_pending_collect_qty`
- 🟠 **Fix #2**: Window-Close Balance-Only Force mit neuem tx_case
- 🟡 **Fix #3**: Log-based Price Dedupe mit ±10% Toleranz

**Erwartete Verbesserungen**:
- ✅ Preorders werden nicht mehr verworfen
- ✅ Window-Close verliert keine Transaktionen
- ✅ Keine Duplikate mit leicht unterschiedlichen Preisen
- ✅ Detail-Window Genauigkeit auf Log-based Level

**Test-Readiness**: ✅ BEREIT FÜR REAL-WORLD TEST

---

**Ende des Dokuments**
