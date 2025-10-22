# Detail-Window Fixes - Change Summary
**Datum**: 2025-10-20  
**Branch**: feature/detail-window-capture

---

## Änderungen an tracker.py

### 1. Neue State-Variable (Line 238)
```python
self._detail_pending_collect_qty = 0  # FIX #1: Preorder-Menge die bei Baseline bereits collected war
```

### 2. Reset-Funktion erweitert (Line 2230)
```python
def _reset_detail_window_state(self):
    # ... existing resets ...
    self._detail_pending_collect_qty = 0  # FIX #1: Reset pending collect
```

### 3. Warehouse-Only Delta Handling (Line 2350)
**Vorher**: Return None (verwerfen)  
**Nachher**: Speichern in `pending_collect_qty` für spätere Kombination

```python
if self._detail_partial_warehouse_delta > 0 and self._detail_partial_balance_delta == 0:
    self._detail_pending_collect_qty += self._detail_partial_warehouse_delta
    self._detail_partial_balance_delta = 0
    self._detail_partial_warehouse_delta = 0
    return None
```

### 4. Kombination bei normalen Käufen (Line 2463)
```python
if self._detail_pending_collect_qty > 0:
    quantity += self._detail_pending_collect_qty
    self._detail_pending_collect_qty = 0
```

### 5. Balance-Only Fallback mit Kombination (Line 2430)
```python
estimated_qty = abs(self._detail_partial_balance_delta) // desired_price
if self._detail_pending_collect_qty > 0:
    estimated_qty += self._detail_pending_collect_qty
    self._detail_pending_collect_qty = 0
```

### 6. Window-Close Force-Save (Line 2635)
```python
if current_balance is None or current_warehouse is None:
    if (self._detail_partial_balance_delta < 0 and 
        self._detail_balance_delta_timestamp is not None):
        # Force-Save mit Balance-Only + pending_collect_qty
        transaction = {
            'tx_case': 'buy_collect_balance_only_forced'
        }
        self.store_transaction_db(transaction)
    self._reset_detail_window_state()
    return
```

### 7. Log-based Price Dedupe (Line 2105)
**Vorher**: Exakte Price-Match  
**Nachher**: Price-Similarity mit ±10% Toleranz

```python
PRICE_TOLERANCE = 0.10
price_min = int(price * (1 - PRICE_TOLERANCE))
price_max = int(price * (1 + PRICE_TOLERANCE))

db_cur.execute(
    """... CAST(price AS INTEGER) BETWEEN ? AND ? ...""",
    (..., price_min, price_max, ...)
)
```

### 8. Delta-Reset nach Transaction (Line 2770)
```python
if transaction:
    # Reset Partial-Deltas (aber NICHT pending_collect_qty!)
    self._detail_partial_balance_delta = 0
    self._detail_partial_warehouse_delta = 0
    self._detail_balance_delta_timestamp = None
```

---

## Neue TX-Cases

### buy_collect_balance_only_forced
- Verwendet wenn Detail-Window geschlossen wird **bevor** Balance-Only Timeout (3s)
- Kombiniert automatisch mit `pending_collect_qty` falls vorhanden
- Schätzt Menge aus `balance / desired_price`

---

## Verhaltensänderungen

### Preorder-Collect (FIX #1)
**Vorher**: Warehouse-Only Delta wurde verworfen → Preorder verloren  
**Nachher**: Warehouse-Only Delta wird gespeichert → Mit nächstem Kauf kombiniert

### Window-Close (FIX #2)
**Vorher**: Balance-Only Timeout abgebrochen → Transaktion verloren  
**Nachher**: Force-Save beim Window-Close → Transaktion gerettet

### Log-based Dedupe (FIX #3)
**Vorher**: Exakte Price-Match → Duplikate mit leicht unterschiedlichen Preisen  
**Nachher**: ±10% Toleranz → Bevorzugt Detail-Window Preis

---

## AGENTS.md Updates erforderlich

### Section: "Operational Workflow & Invariants" → Detail-Window Monitoring
```markdown
- Detail-Window Monitoring nutzt partielle Delta-Akkumulation für asynchrone Balance/Warehouse Updates
- Warehouse-Only Deltas (Preorder-Collect) werden in `_detail_pending_collect_qty` gespeichert und mit nächstem Kauf kombiniert
- Window-Close mit pending Balance-Only Transaction erzwingt sofortigen Save (tx_case=`buy_collect_balance_only_forced`)
- Log-based Dedupe nutzt Price-Similarity (±10%) um OCR-Drift zu tolerieren
```

### Section: "Supported Cases"
```markdown
- buy_collect_ui_inferred: Detail-Window via vollständige Balance+Warehouse Deltas
- buy_collect_balance_only: Detail-Window nach 3s Timeout (Warehouse nicht aktualisiert)
- buy_collect_balance_only_forced: Detail-Window bei Window-Close vor Timeout
```

---

## Test-Empfehlungen

### Unit-Tests benötigt
1. `test_pending_collect_qty_single_preorder()` - Ein Preorder + ein Kauf
2. `test_pending_collect_qty_multiple_preorders()` - Mehrere Preorders + ein Kauf
3. `test_window_close_force_save()` - Balance-Only + sofortiges Schließen
4. `test_window_close_force_save_with_preorder()` - Kombination beider Features
5. `test_price_similarity_dedupe()` - Log-based mit ähnlichem Preis

### Integration-Tests benötigt
1. Pig Blood Scenario (5000x preorder + 2×5000x käufe)
2. Schnelles Schließen (< 3s) nach Kauf
3. Log-based vs Detail-Window Price-Conflict

---

## Performance-Impact

**Erwartung**: NEUTRAL
- ✅ `pending_collect_qty` ist reine RAM-Operation (kein DB-Overhead)
- ✅ Price-Similarity nutzt BETWEEN (schnell, indiziert)
- ✅ Force-Save nur bei Window-Close (selten)
- ✅ Keine zusätzlichen OCR-Calls

---

## Rückwärtskompatibilität

- ✅ Alte Transaktionen unverändert
- ✅ Alte tx_cases funktionieren weiterhin
- ✅ Dedupe funktioniert mit allen Cases
- ✅ Keine DB-Migration erforderlich

---

**Ende der Zusammenfassung**
