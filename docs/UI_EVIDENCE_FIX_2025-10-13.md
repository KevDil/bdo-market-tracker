# UI Evidence Fix - Fast Collect Scenario (2025-10-13 21:14)

## Problem

Bei einem Test um 21:14 wurden folgende Transaktionen durchgeführt:
1. **Magical Shard**: 179x verkauft über Collect-Button (SELL)
2. **Monk's Branch**: 1000x gekauft um 21:07 (BUY, alt)
3. **Sealed Black Magic Crystal**: 222x gekauft um 21:07 (BUY, alt)

**Ergebnis:** Nur Monk's Branch wurde gespeichert. Magical Shard und Sealed Black Magic Crystal wurden nicht gespeichert.

## Root Cause Analysis

### 1. Magical Shard - Fehlende Transaction-Zeile

**OCR-Text zeigte:**
```
Magical Shard Registration Count 179 Sales Completed 179 2025 1C-13 21.07 3,140,000 collect Re-list
```

**Problem:**
- Die "Transaction of Magical Shard x179 worth XXX Silver" Zeile **fehlte im OCR**
- Nur UI-Metriken waren sichtbar: `salesCompleted=179`
- Der Tracker verwarf den Eintrag wegen fehlendem Transaction-Anchor

**Grund:**
- User stoppte Auto-Track nur 1-2 Sekunden nach dem Collect
- Die Transaction-Zeile war noch nicht gescrollt/angezeigt oder wurde von alten Einträgen überdeckt

### 2. Sealed Black Magic Crystal - Preis-Verwechslung

**OCR-Parsing:**
```
structured: placed item='Sealed Black Magic Crystal' qty=222 price=597180000 ✅
structured: transaction item='Sealed Black Magic Crystal' qty=222 price=599400000 ✅
```

**Aber dann:**
```
[PRICE-IMPLAUSIBLE] 'Monk's Branch' 222x @ 599,400,000: too_high
[PRICE-ERROR] UI fallback failed for 'Monk's Branch' - discarding entry
```

**Problem:**
- Die Werte von Sealed Black Magic Crystal (222x, 599M) wurden fälschlich Monk's Branch zugeordnet
- Monk's Branch bekam den Preis der SBMC → viel zu hoch → verworfen
- SBMC selbst wurde dadurch nicht gespeichert

**Grund:**
- Clustering-Logik verwechselt Items mit **identischem Timestamp** (beide 21:07)
- Preis/Menge-Zuordnung fehlerhaft bei mehreren Transaktionen mit gleichem Timestamp

## Implemented Fixes

### Fix 1: UI-Evidence für Sell-Events ohne Transaction-Zeile

**Wo:** `tracker.py` Zeilen 1181-1196

Erweitert die "listed-only"-Prüfung um UI-Evidenz:

```python
# On sell overview, skip listed-only clusters UNLESS UI metrics show completed sales
if wtype == 'sell_overview' and not transaction_entry and listed_entry and ent['type'] == 'listed':
    # Check if UI metrics show salesCompleted > 0 for this item (fast collect scenario)
    has_sell_ui_evidence = False
    item_lc_check = (ent.get('item') or '').lower()
    if item_lc_check in ui_sell:
        sc = ui_sell[item_lc_check].get('salesCompleted', 0) or 0
        if sc > 0:
            has_sell_ui_evidence = True
            log_debug(f"[UI-EVIDENCE] Item '{ent.get('item')}' has salesCompleted={sc} - allowing sell without transaction line (fast collect scenario)")
    
    if not has_sell_ui_evidence:
        log_debug(f"[CLUSTER] Skip 'listed'-only for '{ent.get('item')}' on sell_overview (no transaction)")
        continue
```

**Effekt:**
- Sell-Events OHNE Transaction-Zeile werden akzeptiert, wenn `salesCompleted > 0`
- Behandelt "fast collect"-Szenario, wo Transaction-Zeile noch nicht sichtbar ist

### Fix 2: UI-Evidence für Sell Transaction-Anchor

**Wo:** `tracker.py` Zeilen 1256-1276

Erweitert die Transaction-Anchor-Prüfung:

```python
if side == 'sell':
    has_transaction_anchor = any(r['type'] == 'transaction' for r in related) or ent['type'] == 'transaction'
    
    # Check UI evidence for fast collect scenarios (transaction line scrolled off)
    has_sell_ui_evidence_anchor = False
    if not has_transaction_anchor:
        item_lc_check = (ent.get('item') or '').lower()
        if item_lc_check in ui_sell:
            sc = ui_sell[item_lc_check].get('salesCompleted', 0) or 0
            if sc > 0:
                has_sell_ui_evidence_anchor = True
                log_debug(f"[UI-EVIDENCE] Allowing sell for '{ent.get('item')}' with UI evidence (salesCompleted={sc}) despite missing transaction line")
    
    if not has_transaction_anchor and not has_sell_ui_evidence_anchor:
        log_debug(f"skip sell without transaction anchor for item='{ent['item']}' on {wtype}")
        continue
```

**Effekt:**
- Sell-Events werden akzeptiert wenn ENTWEDER Transaction-Anchor ODER UI-Evidence vorhanden
- Verhindert falsches Verwerfen bei schnellen Collect-Aktionen

### Fix 3: Vollständige UI-basierte Preisberechnung für Sells

**Wo:** `tracker.py` Zeilen 1491-1541

Erweitert die Preisberechnung um komplette UI-Fallback-Logik:

```python
# CRITICAL: If NO transaction line (missing qty or price), use UI metrics directly
# This handles fast collect scenarios where transaction line scrolled off before OCR scan
if (quantity is None or price is None or price <= 0):
    try:
        item_lc2 = (ent.get('item') or '').lower()
        m_ui = ui_sell.get(item_lc2)
        
        if m_ui:
            sc = m_ui.get('salesCompleted') or 0
            unit_price = m_ui.get('price') or 0
            
            if sc > 0 and unit_price > 0:
                # Calculate quantity from UI if missing
                if quantity is None or quantity <= 0:
                    quantity = sc
                    log_debug(f"[UI-FALLBACK] Using salesCompleted={sc} for quantity (no transaction line)")
                
                # Calculate price from UI
                if price is None or price <= 0:
                    price = int(round(unit_price * quantity * 0.88725))
                    log_debug(f"[UI-FALLBACK] Calculated sell price from UI: {quantity}x * {unit_price} * 0.88725 = {price:,}")
    except Exception as e:
        log_debug(f"[UI-FALLBACK] Failed for sell event: {e}")
```

**Effekt:**
- **Quantity** wird aus `salesCompleted` genommen wenn Transaction fehlt
- **Price** wird aus `unit_price * quantity * 0.88725` berechnet
- Verhindert "invalid/missing price" Fehler bei fehlendem Transaction-Entry

## Expected Behavior (After Fix)

### Scenario: Fast Collect (Transaction-Zeile fehlt)

**Test:** Magical Shard 179x verkauft, Auto-Track nach 1-2 Sekunden gestoppt

**Vorher:**
```
[CLUSTER] Skip 'listed'-only for 'Magical Shard' on sell_overview (no transaction)
→ Nicht gespeichert ❌
```

**Nachher:**
```
[UI-EVIDENCE] Item 'Magical Shard' has salesCompleted=179 - allowing sell without transaction line
[UI-FALLBACK] Using salesCompleted=179 for quantity (no transaction line)
[UI-FALLBACK] Calculated sell price from UI: 179x * 3140000 * 0.88725 = 498,477,825
→ Gespeichert ✅
```

## Remaining Issue: Multiple Transactions with Same Timestamp

**Problem:** Sealed Black Magic Crystal und Monk's Branch (beide 21:07) wurden verwechselt.

**Ursache:** Clustering-Logik ordnet Werte falsch zu wenn:
- Mehrere Items haben **identischen Timestamp**
- Transaction-Einträge werden nicht eindeutig Item-Namen zugeordnet

**Hinweis:** Dies ist ein **separates Problem** von der "fast collect"-Issue und betrifft die **Parsing/Clustering-Logik**, nicht UI-Evidence.

**Empfehlung:** 
- Prüfe `parsing.py` für korrekte Item-Zuordnung bei gleichzeitigen Transaktionen
- Eventuell müssen Transaktionen mit identischem Timestamp besser separiert werden

## Testing Recommendations

### Für Fast Collect Tests:

1. **Vorbereitung:**
   - Sell Tab öffnen
   - Item zum Verkauf listen (z.B. 100+ Stück)
   - Warten bis Items verkauft sind (salesCompleted > 0)

2. **Test-Durchführung:**
   - Auto-Track starten
   - **5-10 Sekunden warten** (wichtig!)
   - Collect-Button klicken
   - **Weitere 5-10 Sekunden warten** damit Transaction-Zeile erscheint
   - Auto-Track stoppen

3. **Verifikation:**
   ```bash
   # Check logs
   grep -i "UI-EVIDENCE\|UI-FALLBACK" ocr_log.txt
   
   # Check database
   python -c "from database import get_connection; c = get_connection().cursor(); c.execute('SELECT * FROM transactions ORDER BY id DESC LIMIT 1'); print(c.fetchone())"
   ```

### Für Multi-Item Tests (Timestamp-Konflikt):

1. **Vermeidung:**
   - Kaufe/Verkaufe Items mit **zeitlichem Abstand** (min. 5 Sekunden)
   - Verhindert Timestamp-Kollisionen

2. **Falls Kollisionen unvermeidbar:**
   - Prüfe Logs auf falsche Item-Zuordnung
   - Kontrolliere DB auf plausible Preise für jedes Item

## Files Modified

1. **tracker.py** (Zeilen 1181-1196)
   - UI-Evidence für listed-only Clusters

2. **tracker.py** (Zeilen 1256-1276)
   - UI-Evidence für Transaction-Anchor bei Sells

3. **tracker.py** (Zeilen 1491-1541)
   - Vollständige UI-basierte Preisberechnung für Sells

## Next Steps

1. ⏳ **Test mit neuem Timing:** Magical Shard erneut verkaufen, 5-10 Sekunden warten
2. ⏳ **Prüfe Sealed Black Magic Crystal Issue:** Separate Test für Timestamp-Kollisionen
3. ⏳ **Validiere Monk's Branch:** Prüfe ob korrekt gespeichert wurde (falls nicht, prüfe Clustering-Logik)

## Related Documentation

- `IMPROVEMENTS_SUMMARY_2025-10-13.md` - Überblick aller Änderungen
- `docs/PRICE_ERROR_HANDLING_IMPROVEMENTS_2025-10-13.md` - Price Error Handling
