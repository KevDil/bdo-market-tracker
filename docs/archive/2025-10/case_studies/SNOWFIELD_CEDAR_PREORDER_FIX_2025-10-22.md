# Snowfield Cedar Sap Preorder Auto-Collect Fix Plan
**Datum:** 2025-10-22  
**Status:** Analysis Complete - Fix Plan Ready

## Problem-Analyse

### Test-Szenario
1. **Ausgangslage:** 0x Snowfield Cedar Sap im Warehouse
2. **User-Aktion:** Click "Relist" auf bestehende Preorder (5000x davon 2188x gefüllt)
3. **Erwartetes Verhalten:** 
   - Alte Preorder wird auto-collected → 2188x ins Warehouse
   - Neue Preorder wird gesetzt: 5000x @ 175,500,000
   - **Eine** Transaktion: `2188x Snowfield Cedar Sap @ 76,580,000` mit `buy_relist_partial`

### Tatsächliches Verhalten (FALSCH)
**Zwei Probleme identifiziert:**

#### Problem 1: Special Strawberry Duplikat (10:30)
- **Datenbank zeigt:**
  ```
  2025-10-22 10:31:00 | buy | 3000x Special Strawberry | 75,600,000 | f45c41550b4425a9
  2025-10-22 10:30:00 | buy | 3000x Special Strawberry | 75,600,000 | 206e2be99ed28610
  ```
- **Problem:** Alte Transaktion aus dem Log wurde fälschlicherweise **doppelt gespeichert**
- **Root Cause:** Die Baseline enthielt bereits die Special Strawberry-Transaktion von 10:30. Beim Exit aus dem Detail-Window wurde die Overview erneut gescannt, und die DELTA-Logik hat die Transaktion **nicht** als Duplikat erkannt, obwohl sie identisch war.

#### Problem 2: Snowfield Cedar Sap - Fehlende Preorder-Detection
- **Datenbank zeigt:**
  ```
  2025-10-22 10:31:00 | buy | 2188x Snowfield Cedar Sap | 76,580,000 | 68ce6202a444db71
  ```
- **Preorder-Tabelle zeigt:**
  ```
  id=19 | item_name=Snowfield Cedar Sap | quantity=5000 | status=active | timestamp=2025-10-22 10:31:00
  ```
- **Problem:** Die neue Preorder wurde korrekt erstellt, **ABER:**
  - Die alte Preorder (2188x gefüllt @ irgendein Preis) war **NICHT** in der Preorder-Tabelle
  - Daher konnte `_check_for_preorder_autocollect()` **nichts** finden
  - Die Transaktion wurde nur aus dem Log gespeichert, OHNE Preorder-Korrektur
  - **Kritisch:** Zu Beginn des Tests war **keine** Preorder für Snowfield Cedar Sap in der DB

### Log-Analyse

#### t=0 - t=0.09s: Initial Buy Overview Scan
```
10:31:36.457 [WINDOW] Transition: unknown → buy_overview
10:31:36.809 structured_count=4
  - 2025-10-22 10:20:00 listed Magical Shard (alt)
  - 2025-10-22 10:20:00 transaction Magical Shard (alt)
  - 2025-10-22 10:29:00 listed Blessed Soul Fragment (alt)
  - 2025-10-22 10:30:00 purchased Special Strawberry ← ERSTE SPEICHERUNG
10:31:37.170 [SAVE] ✅ buy buy_collect 3000x Special Strawberry @ 75,600,000 ts=10:30:00
10:31:37.180 [BASELINE] Updated & persisted: 0 → 594 chars, saved 2 transactions
```
**Baseline enthält jetzt Special Strawberry 10:30:00**

#### t=0.7s: User öffnet Detail-Window (Relist-Click)
```
10:31:40.354 [WINDOW] Transition: buy_overview → buy_item
10:31:40.358 [DETAIL] ⚡ Warehouse=None detected - PERFECT timing! Using 0 as baseline.
10:31:40.908 [DETAIL] ⚡ BASELINE CAPTURED
   Item: Snowfield Cedar Sap
   Warehouse: 0
   Balance: 211,460,029,349
```
**Baseline korrekt: Warehouse=0, Balance=211,460,029,349**

#### t=1.5s: User setzt neue Preorder → Auto-Collect passiert
```
10:31:42.350 [DETAIL] Change detected in buy_item
   Balance: 211460029349 → 211382949349 (Δ -77,080,000)
   Warehouse: 0 → 2188 (Δ +2188)
10:31:42.427 [RELIST-DETECT] ✅ Pattern matched: balance -77,080,000 (new preorder), warehouse +2188 (auto-collect + possible instant buy)
10:31:42.428 [PREORDER] Cache refreshed: 2 active preorder(s)
10:31:42.428 [RELIST] ❌ No matching preorder found - cannot proceed
```
**KRITISCH:** Preorder-Cache hat **2 aktive Preorders**, aber **KEINE** für Snowfield Cedar Sap!
- Das bedeutet: Die alte Preorder war nie in der DB

#### t=3.9s: Detail-Window schließt → Back to Overview
```
10:31:44.349 [WINDOW] Transition: buy_item → buy_overview
10:31:44.709 structured_count=4
  - 2025-10-22 10:30:00 purchased Special Strawberry ← ZWEITE SPEICHERUNG (DUPLIKAT!)
  - 2025-10-22 10:31:00 placed Snowfield Cedar Sap (neu)
  - 2025-10-22 10:31:00 withdrew Snowfield Cedar Sap (neu)
  - 2025-10-22 10:31:00 transaction Snowfield Cedar Sap (neu)
10:31:44.723 [DELTA] Baseline exists: 594 chars
10:31:44.723 [DELTA] Baseline has 4 entries
10:31:44.723 [DELTA] prev_max_ts=2025-10-22 10:30:00, tx_candidates=2
10:31:44.723 [DELTA] Checking Special Strawberry @ 2025-10-22 10:31:00: newer=True
10:31:44.728 DB SAVE: buy 3000x Special Strawberry @ 75600000 ts=2025-10-22 10:31:00 ← FALSCH!
```

**FALSCHER TIMESTAMP:** Special Strawberry wurde mit `10:31:00` statt `10:30:00` gespeichert!
- OCR hat vermutlich `10.30` gelesen, aber der Structured-Parser hat es zu `10:31:00` interpretiert
- DELTA-Check: `newer=True` weil `10:31:00 > 10:30:00`
- Resultat: **ZWEITE SPEICHERUNG** trotz identischem Inhalt

## Root Causes

### RC1: Missing Preorder in Database
**Ursache:** Die ursprüngliche Preorder (5000x Snowfield Cedar Sap, 2188x gefüllt) wurde **nie** in der Preorder-Tabelle gespeichert.

**Warum?**
1. User hat Preorder **vor** Aktivierung von Auto-Track gesetzt
2. **ODER:** Preorder wurde gesetzt, als Detail-Window-Tracking noch nicht implementiert war
3. **ODER:** Bei Preorder-Platzierung ist ein Fehler aufgetreten (z.B. OCR-Fehler, fehlende Menge)

**Konsequenz:**
- `_check_for_preorder_autocollect()` findet keine Preorder
- Preorder-Preis-Korrektur wird **nicht** angewendet
- Transaktion wird nur aus Log gespeichert (vermutlich korrekter Preis, aber ohne Preorder-Kontext)

### RC2: Timestamp-OCR-Fehler führt zu Duplikaten
**Ursache:** OCR liest Timestamp unscharf → Parser rundet/interpretiert falsch

**Beispiel:**
- Original: `2025.10.22 10.30`
- OCR liest: `2025.10.22 10.30` (korrekt)
- Bei erneutem Scan: OCR liest `2025.10.22 10.31` oder Parser interpretiert wegen Kontext falsch
- DELTA-Check: `10:31:00 > 10:30:00` → `newer=True` → SPEICHERN!

**Konsequenz:**
- Identische Transaktion wird mit anderem Timestamp gespeichert
- Content-Hash ist **unterschiedlich** wegen Timestamp-Differenz
- 5-Minuten-Value-Guard greift nicht, weil Timestamps exakt 1 Minute auseinander liegen

### RC3: Aggressive Detail-Window-Exit-Rescans
**Ursache:** Nach Detail-Window-Exit werden aggressive Burst-Rescans ausgelöst

```
10:31:44.351 [BURST-AGGRESSIVE] Returned from buy_item to buy_overview 
                                 -> 15 fast scans + 5 immediate rescans (TARGET: <1s capture)
```

**Problem:**
- **15 schnelle Scans** + **5 sofortige Rescans** = 20 OCR-Läufe in kurzer Zeit
- Jeder Scan kann Timestamp leicht unterschiedlich interpretieren
- DELTA-Check vergleicht nur mit `prev_max_ts=2025-10-22 10:30:00`
- Wenn **ein** Scan `10:31:00` statt `10:30:00` liest → DUPLIKAT!

## Fix-Strategie

### Fix 1: Preorder-Detection beim Relist verbessern
**Ziel:** Erkenne fehlende Preorders und rekonstruiere sie aus dem Log

**Ansatz:**
1. **Log-Based Preorder-Reconstruction:**
   - Wenn `withdrew` + `transaction` + `placed` für dasselbe Item erkannt werden
   - **UND** keine Preorder in DB gefunden wird
   - **DANN:** Rekonstruiere alte Preorder aus `withdrew`-Zeile:
     ```python
     # withdrew: quantity=2812, price=98,420,000
     # transaction: quantity=2188
     # → Original preorder: quantity=2812+2188=5000, filled=2188
     ```

2. **Fallback für fehlende Preorders:**
   - Wenn `_check_for_preorder_autocollect()` keine Preorder findet
   - **ABER** Delta-Pattern eindeutig ist (Balance↓ + Warehouse↑)
   - **UND** Log zeigt `withdrew` + `transaction`
   - **DANN:** Erstelle "synthetische" Preorder für Preis-Korrektur

**Implementierung:**
```python
def _reconstruct_missing_preorder(self, item_name, withdrew_qty, withdrew_price, transaction_qty, timestamp):
    """Reconstruct preorder from withdrew + transaction log entries."""
    original_qty = withdrew_qty + transaction_qty
    original_filled = transaction_qty
    
    # Berechne durchschnittlichen Preorder-Preis
    # withdrew_price ist Rückerstattung für unfilled orders
    # transaction zeigt collected amount
    preorder_price_estimate = withdrew_price  # Vereinfachung
    
    logger.debug(f"[PREORDER-RECONSTRUCT] Missing preorder detected for {item_name}")
    logger.debug(f"   Original: {original_qty}x (filled={original_filled})")
    logger.debug(f"   Withdrew: {withdrew_qty}x @ {withdrew_price:,}")
    
    return {
        'quantity': original_qty,
        'quantity_filled': original_filled,
        'price': preorder_price_estimate,
        'timestamp': timestamp
    }
```

### Fix 2: Timestamp-Toleranz bei Duplikats-Check
**Ziel:** Verhindere Duplikate durch Timestamp-OCR-Fehler

**Aktuell:**
```python
# in _should_save_transaction():
if timestamp > prev_max_ts:  # "newer" check
    return True  # SAVE!
```

**Problem:** `10:31:00 > 10:30:00` → SAVE!, auch wenn Inhalt identisch

**Lösung:**
```python
def _should_save_transaction(self, item, qty, price, timestamp, tx_side, baseline_text):
    """Enhanced duplicate check with timestamp tolerance."""
    
    # 1. Exact match in baseline text (existing logic)
    if self._transaction_in_baseline_text(item, qty, price, baseline_text):
        return False
        
    # 2. Value-based duplicate check with ±2min timestamp tolerance
    if self._is_value_duplicate_with_time_tolerance(item, qty, price, timestamp, tolerance_minutes=2):
        logger.debug(f"[DELTA] Value duplicate with timestamp tolerance: {item} {qty}x @ {price:,} ts={timestamp}")
        return False
    
    # 3. Check if timestamp is "newer" than baseline
    prev_max_ts = self._get_baseline_max_timestamp()
    if timestamp <= prev_max_ts:
        return False  # Historical duplicate
    
    return True  # OK to save

def _is_value_duplicate_with_time_tolerance(self, item, qty, price, timestamp, tolerance_minutes=2):
    """Check if transaction exists in DB with same values but slightly different timestamp."""
    from datetime import datetime, timedelta
    
    ts_obj = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
    ts_min = ts_obj - timedelta(minutes=tolerance_minutes)
    ts_max = ts_obj + timedelta(minutes=tolerance_minutes)
    
    # Query DB for matching transaction within time window
    with get_cursor() as cursor:
        cursor.execute('''
            SELECT COUNT(*) FROM transactions
            WHERE item_name = ?
              AND quantity = ?
              AND ABS(price - ?) < 1000
              AND timestamp BETWEEN ? AND ?
        ''', (item, qty, price, ts_min.strftime('%Y-%m-%d %H:%M:%S'), ts_max.strftime('%Y-%m-%d %H:%M:%S')))
        
        count = cursor.fetchone()[0]
        return count > 0
```

### Fix 3: Reduziere aggressive Burst-Rescans nach Detail-Window-Exit
**Ziel:** Verhindere übermäßige OCR-Läufe, die zu Timestamp-Inkonsistenzen führen

**Aktuell:**
```python
# 15 fast scans + 5 immediate rescans
self._request_immediate_rescan = 5
self._request_burst_scans = 15
```

**Problem:** 20 Scans in <3 Sekunden → hohe Wahrscheinlichkeit für Timestamp-Varianz

**Lösung:**
```python
# Reduziere auf 3 immediate + 5 burst scans
self._request_immediate_rescan = 3
self._request_burst_scans = 5

# Total: 8 Scans statt 20 → schneller + weniger Duplikat-Risiko
```

**Oder:** Führe **Single-Shot-Capture** ein:
```python
def _handle_detail_window_exit(self):
    """Single comprehensive scan after detail window exit."""
    # Warte kurz, bis UI settled ist
    time.sleep(0.3)
    
    # Ein einziger gründlicher Scan
    self._force_full_ocr = True
    self._pending_metrics_refresh = True
    
    # Keine Burst-Scans
    self._request_immediate_rescan = 0
    self._request_burst_scans = 0
```

### Fix 4: Enhanced Logging für Duplikats-Detection
**Ziel:** Bessere Diagnostics für zukünftige Probleme

```python
def _should_save_transaction(self, item, qty, price, timestamp, tx_side, baseline_text):
    logger.debug(f"[DELTA-CHECK] Evaluating {item} {qty}x @ {price:,} ts={timestamp}")
    
    # Log baseline state
    prev_max_ts = self._get_baseline_max_timestamp()
    logger.debug(f"[DELTA-CHECK]   Baseline max_ts: {prev_max_ts}")
    logger.debug(f"[DELTA-CHECK]   Baseline size: {len(baseline_text)} chars")
    
    # Check 1: Exact text match
    in_baseline = self._transaction_in_baseline_text(item, qty, price, baseline_text)
    logger.debug(f"[DELTA-CHECK]   In baseline text: {in_baseline}")
    
    # Check 2: Value duplicate
    is_value_dup = self._is_value_duplicate_with_time_tolerance(item, qty, price, timestamp, tolerance_minutes=2)
    logger.debug(f"[DELTA-CHECK]   Value duplicate (±2min): {is_value_dup}")
    
    # Check 3: Timestamp newer
    is_newer = timestamp > prev_max_ts if prev_max_ts else True
    logger.debug(f"[DELTA-CHECK]   Is newer: {is_newer}")
    
    # Decision
    should_save = not (in_baseline or is_value_dup) and is_newer
    logger.debug(f"[DELTA-CHECK]   → Decision: {'SAVE' if should_save else 'SKIP'}")
    
    return should_save
```

## Implementation Priority

### Priority 1 (CRITICAL): Fix 2 - Timestamp-Toleranz
**Warum:** Verhindert sofort alle Timestamp-OCR-Duplikate
**Aufwand:** Mittel (neue DB-Query, Integration in DELTA-Check)
**Impact:** Hoch (löst Special Strawberry-Problem)

### Priority 2 (HIGH): Fix 3 - Reduziere Burst-Rescans
**Warum:** Reduziert Timestamp-Varianz-Risiko erheblich
**Aufwand:** Niedrig (Konstanten ändern)
**Impact:** Mittel (weniger OCR-Load, schnellere Scans, weniger Duplikat-Risiko)

### Priority 3 (MEDIUM): Fix 1 - Preorder-Reconstruction
**Warum:** Löst Snowfield Cedar Sap-Problem (fehlende Preorder)
**Aufwand:** Hoch (komplexe Logik, neue Rekonstruktions-Funktion)
**Impact:** Mittel (nur bei fehlenden Preorders relevant)

### Priority 4 (LOW): Fix 4 - Enhanced Logging
**Warum:** Diagnostics für zukünftige Probleme
**Aufwand:** Niedrig (nur Logging)
**Impact:** Niedrig (kein Bugfix, nur Debugging-Hilfe)

## Testing Strategy

### Test 1: Timestamp-Toleranz
1. Manuell zwei identische Transaktionen mit Timestamps `10:30:00` und `10:31:00` erstellen
2. Verify: Zweite Transaktion wird **nicht** gespeichert
3. Check DB: Nur **eine** Transaktion vorhanden

### Test 2: Missing Preorder Reconstruction
1. Lösche Preorder für Item X aus DB
2. Setze Relist (Detail-Window)
3. Verify: Auto-Collect wird erkannt + Preis-Korrektur angewendet
4. Check DB: **Eine** korrekte Transaktion mit korrigiertem Preis

### Test 3: Reduced Burst-Rescans
1. Exit aus Detail-Window
2. Count OCR-Läufe in Log
3. Verify: ≤8 Scans statt 20
4. Check DB: Keine Duplikate

## Open Questions

1. **Warum war keine Preorder in der DB?**
   - User hat Preorder vor Auto-Track-Aktivierung gesetzt?
   - OCR-Fehler bei ursprünglicher Preorder-Platzierung?
   - Preorder-Tracking war damals noch nicht implementiert?

2. **Warum exakt 1 Minute Timestamp-Differenz?**
   - OCR-Fehler? (10.30 → 10.31)
   - Parser-Rundung?
   - Game-UI-Bug?

3. **Sollten wir Single-Shot-Capture statt Burst-Rescans verwenden?**
   - Pro: Weniger OCR-Load, weniger Timestamp-Varianz
   - Contra: Risiko, dass Transaktion verpasst wird

## Next Steps

1. **Implementiere Fix 2** (Timestamp-Toleranz) in `tracker.py`
2. **Implementiere Fix 3** (Reduziere Burst-Rescans) in `tracker.py`
3. **Test mit Snowfield Cedar Sap Relist-Szenario**
4. **Entscheide:** Fix 1 (Preorder-Reconstruction) notwendig?
5. **Review:** Single-Shot-Capture als Alternative?

## Conclusion

**Hauptproblem:** Timestamp-OCR-Varianz führt zu Duplikaten  
**Lösung:** Timestamp-Toleranz (±2min) + weniger Burst-Rescans  
**Sekundärproblem:** Fehlende Preorders können nicht korrigiert werden  
**Lösung:** Log-basierte Preorder-Reconstruction (optional)
