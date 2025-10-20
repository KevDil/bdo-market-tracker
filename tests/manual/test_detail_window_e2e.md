# Detail-Fenster End-to-End Test Guide

## Übersicht

Dieser Test-Guide beschreibt manuelle End-to-End-Tests für die Detail-Fenster-Transaktionserkennung.

**Voraussetzungen**:
- BDO Spiel gestartet
- Marketplace geöffnet
- Auto-Track aktiviert (`python gui.py` → Start)
- Debug-Mode aktiviert in `config.py` (`DEBUG_MODE = True`)

---

## Test 1: Sell-Transaction im Detail-Fenster

### Setup
1. Öffne Sell-Overview (Central Market → Sell-Tab)
2. Wähle ein Item aus der Liste (z.B. "Powder of Darkness")
3. Klicke "Sell" → Detail-Fenster öffnet sich

### Vorbereitung
Notiere die aktuellen Werte:
- **Warehouse Quantity (vor Verkauf)**: ______
- **Balance (vor Verkauf)**: ______
- **Set Price**: ______ (stelle Preis ein)
- **Register Quantity**: ______ (stelle Menge ein)

### Durchführung
1. Klicke "Register" → Bestätigungsfenster erscheint
2. Klicke "Yes (ENTER)"
3. Warte bis Bestätigungsfenster schließt (~1 Sekunde)
4. **WICHTIG**: Bleibe im Detail-Fenster! Nicht zurück zum Overview gehen!
5. Warte 2-3 Sekunden

### Erwartetes Ergebnis

**Console-Output** (Debug-Mode):
```
[DETAIL] Entered sell_item window
   Item: Powder of Darkness
   Balance baseline: 1234567890
   Warehouse baseline: 50

[DETAIL] Change detected in sell_item
   Balance: 1234567890 → 1236067890 (Δ +1,500,000)
   Warehouse: 50 → 40 (Δ -10)

[DETAIL] ✅ Inferred transaction: sell 10x Powder of Darkness @ 1690140 Silver (total)
[DETAIL] ✅ Transaction saved successfully
```

**Datenbank**:
```sql
SELECT * FROM transactions 
WHERE tx_case = 'sell_collect' 
  AND transaction_type = 'sell'
ORDER BY timestamp DESC 
LIMIT 1;
```

**Verifikation-Checklist**:
- ✅ `transaction_type = 'sell'`
- ✅ `tx_case = 'sell_collect'`
- ✅ `quantity` = Register Quantity (z.B. 10)
- ✅ `price` ≈ (Set Price × Quantity) / 0.88725 (Brutto-Preis)
- ✅ `item_name` = korrekt (z.B. "Powder of Darkness")
- ✅ `timestamp` = aktuelle Systemzeit (nicht Game-Zeit!)
- ✅ Nur 1 Eintrag (keine Duplikate)

---

## Test 2: Buy-Transaction im Detail-Fenster

### Setup
1. Öffne Buy-Overview (Central Market → Buy-Tab)
2. Wähle ein Item aus der Liste (z.B. "Brutal Death Elixir")
3. Klicke "Buy" → Detail-Fenster öffnet sich

### Vorbereitung
Notiere die aktuellen Werte:
- **Warehouse Quantity (vor Kauf)**: ______
- **Balance (vor Kauf)**: ______
- **Desired Price**: ______ (stelle Preis ein)
- **Desired Amount**: ______ (stelle Menge ein)

### Durchführung
1. Klicke "Buy" → Bestätigungsfenster erscheint
2. Klicke "Yes (ENTER)"
3. Warte bis Bestätigungsfenster schließt (~1 Sekunde)
4. **WICHTIG**: Bleibe im Detail-Fenster!
5. Warte 2-3 Sekunden

### Erwartetes Ergebnis

**Console-Output**:
```
[DETAIL] Entered buy_item window
   Item: Brutal Death Elixir
   Balance baseline: 9876543210
   Warehouse baseline: 10

[DETAIL] Change detected in buy_item
   Balance: 9876543210 → 9854043210 (Δ -22,500,000)
   Warehouse: 10 → 15 (Δ +5)

[DETAIL] ✅ Inferred transaction: buy 5x Brutal Death Elixir @ 22500000 Silver (total)
[DETAIL] ✅ Transaction saved successfully
```

**Datenbank**:
```sql
SELECT * FROM transactions 
WHERE tx_case = 'buy_collect' 
  AND transaction_type = 'buy'
ORDER BY timestamp DESC 
LIMIT 1;
```

**Verifikation-Checklist**:
- ✅ `transaction_type = 'buy'`
- ✅ `tx_case = 'buy_collect'`
- ✅ `quantity` = Desired Amount (z.B. 5)
- ✅ `price` = Desired Price × Quantity (z.B. 4500000 × 5 = 22500000)
- ✅ `item_name` = korrekt
- ✅ `timestamp` = aktuelle Systemzeit
- ✅ Nur 1 Eintrag

---

## Test 3: Abgebrochene Transaktion

### Setup
1. Öffne Detail-Fenster (Sell oder Buy)
2. Stelle Preis und Menge ein

### Durchführung
1. Klicke "Register"/"Buy" → Bestätigungsfenster erscheint
2. **ABBRUCH**: Klicke "No" oder drücke ESC
3. Bleibe im Detail-Fenster
4. Warte 6 Sekunden

### Erwartetes Ergebnis

**Console-Output**:
```
[DETAIL] Entered sell_item window
   Balance baseline: 1234567890
   Warehouse baseline: 50

[DETAIL] Timeout after 5.1s - resetting state
```

**Verifikation**:
- ✅ Keine Transaktion gespeichert
- ✅ State wurde nach Timeout zurückgesetzt
- ✅ Keine Fehlermeldungen

---

## Test 4: Duplikat-Prävention (Detail → Log)

### Setup
1. Führe eine Sell-Transaktion im Detail-Fenster durch (siehe Test 1)
2. **SOFORT** nach der Transaktion: Schließe Detail-Fenster (ESC oder "Back")
3. Du solltest nun im Sell-Overview sein

### Durchführung
1. Warte bis Log-OCR die Transaktion erkennt (~2-3 Sekunden)
2. Prüfe Datenbank

### Erwartetes Ergebnis

**Console-Output**:
```
[DETAIL] ✅ Transaction saved successfully
... (Fenster-Wechsel zu sell_overview)
[DEDUPE] Duplicate prevented: content_hash match within 20min tolerance
```

**Datenbank**:
```sql
SELECT COUNT(*) FROM transactions 
WHERE item_name = 'Powder of Darkness' 
  AND timestamp >= datetime('now', '-1 minute');
```

**Verifikation**:
- ✅ Nur 1 Eintrag in Datenbank
- ✅ Log zeigt Duplikat-Erkennung
- ✅ Keine doppelte Speicherung

---

## Test 5: Mehrfach-Transaktionen nacheinander

### Setup
1. Öffne Detail-Fenster (Sell oder Buy)

### Durchführung
1. Führe erste Transaktion durch (z.B. 10x Item verkaufen)
2. Warte 2 Sekunden
3. **Bleibe im Detail-Fenster**
4. Führe zweite Transaktion durch (z.B. 5x Item verkaufen)
5. Warte 2 Sekunden
6. Führe dritte Transaktion durch

### Erwartetes Ergebnis

**Console-Output**:
```
[DETAIL] ✅ Inferred transaction: sell 10x ... @ ...
[DETAIL] Change detected in sell_item (Δ Balance: +..., Δ Warehouse: -10)
[DETAIL] ✅ Transaction saved successfully

[DETAIL] Change detected in sell_item (Δ Balance: +..., Δ Warehouse: -5)
[DETAIL] ✅ Inferred transaction: sell 5x ... @ ...
[DETAIL] ✅ Transaction saved successfully

[DETAIL] Change detected in sell_item (Δ Balance: +..., Δ Warehouse: -2)
[DETAIL] ✅ Inferred transaction: sell 2x ... @ ...
[DETAIL] ✅ Transaction saved successfully
```

**Datenbank**:
```sql
SELECT quantity, price, timestamp 
FROM transactions 
WHERE timestamp >= datetime('now', '-2 minutes')
ORDER BY timestamp ASC;
```

**Verifikation**:
- ✅ 3 separate Transaktionen gespeichert
- ✅ Mengen korrekt (10, 5, 2)
- ✅ Timestamps chronologisch
- ✅ Deltas wurden nach jeder Transaktion aktualisiert

---

## Test 6: Fenstertyp-Wechsel (Sell → Buy)

### Setup
1. Öffne Sell-Detail-Fenster
2. Notiere Balance/Warehouse

### Durchführung
1. Schließe Sell-Detail-Fenster
2. Öffne Buy-Detail-Fenster
3. Notiere neue Balance/Warehouse

### Erwartetes Ergebnis

**Console-Output**:
```
[DETAIL] Entered sell_item window
   Balance baseline: 1234567890
   Warehouse baseline: 50

[DETAIL] Left detail window - resetting state
[DETAIL] Entered buy_item window
   Balance baseline: 1234567890
   Warehouse baseline: 10
```

**Verifikation**:
- ✅ State wurde zurückgesetzt
- ✅ Neue Baseline für Buy-Fenster gesetzt
- ✅ Warehouse-Wert ist unterschiedlich (Sell vs Buy Items)

---

## Test 7: ROI-Kalibrierung Verifikation

### Vorbereitung
1. Aktiviere Debug-Bilder: `utils.py` → `DEBUG_IMAGES = True`
2. Öffne Detail-Fenster (Sell oder Buy)

### Durchführung
1. Warte 1 Scan-Zyklus (~150ms)
2. Prüfe `debug/debug_orig.png` und `debug/debug_proc.png`
3. Laufe Kalibrierungs-Tool:
```powershell
python scripts\utils\calibrate_detail_roi.py --image debug\debug_orig.png --type sell_item
```

### Erwartetes Ergebnis

**Output**:
```
============================================================
ROI Calibration for SELL_ITEM
============================================================

✅ Image loaded: debug\debug_orig.png
   Dimensions: 1089x699 px

🔍 Detecting ROIs...
   ✅ Item Name ROI: x=87, y=21, w=403, h=42
   ✅ Balance ROI: x=43, y=321, w=207, h=63
   ✅ Warehouse ROI: x=32, y=77, w=76, h=63

============================================================
✅ ROI visualization saved to: debug\calibrate_sell_item_roi.png
   ROIs detected: 3/3
============================================================

✅ All ROIs detected successfully!
```

**Verifikation**:
- ✅ Öffne `debug/calibrate_sell_item_roi.png`
- ✅ Grünes Rechteck umschließt Item-Name vollständig
- ✅ Violettes Rechteck umschließt "Balance: ... Silver"
- ✅ Gelbes Rechteck umschließt "Warehouse Quantity: ..."

Falls ROIs falsch positioniert:
1. Öffne `utils.py`
2. Passe Prozent-Werte in `detect_detail_*_roi()` an
3. Wiederhole Kalibrierungs-Lauf
4. Iteriere bis perfekt

---

## Troubleshooting

### Problem: Transaktion wird nicht erkannt

**Symptome**:
- Keine Console-Ausgabe nach Transaktion
- Balance/Warehouse ändern sich nicht

**Diagnose**:
1. Prüfe `ocr_log.txt`:
```powershell
Get-Content ocr_log.txt | Select-Object -Last 50
```

2. Prüfe ob Balance/Warehouse erkannt werden:
```
Balance: 1,234,567,890 Silver  ← Sollte vorhanden sein
Warehouse Quantity: 50         ← Sollte vorhanden sein
```

**Lösungen**:
- ROI-Positionen mit `calibrate_detail_roi.py` anpassen
- OCR-Engine prüfen (`USE_EASYOCR = True`)
- Debug-Mode aktivieren für detaillierte Logs

---

### Problem: Duplikate in Datenbank

**Symptome**:
- Gleiche Transaktion 2x gespeichert
- Log zeigt keine Duplikat-Warnung

**Diagnose**:
```sql
SELECT item_name, quantity, price, COUNT(*) as count
FROM transactions 
WHERE timestamp >= datetime('now', '-5 minutes')
GROUP BY item_name, quantity, price
HAVING count > 1;
```

**Lösungen**:
- Prüfe `content_hash` Berechnung
- Erhöhe Deduplication-Window (aktuell 20 Minuten)
- Reset Datenbank falls korrupt: `python scripts/utils/reset_db.py`

---

### Problem: Falsche Preise/Mengen

**Symptome**:
- Preis stimmt nicht mit Set Price / Desired Price überein
- Menge ist 0 oder absurd hoch

**Diagnose**:
1. Aktiviere Debug-Mode
2. Prüfe Console-Output:
```
[DETAIL] Change detected in sell_item
   Balance: 1000000 → 1500000 (Δ +500,000)
   Warehouse: 50 → 40 (Δ -10)
```

3. Berechne manuell:
- Sell: Brutto = Balance-Delta / 0.88725
- Buy: Brutto = |Balance-Delta|

**Lösungen**:
- OCR-Fehler bei Balance/Warehouse → ROI anpassen
- Plausibilitätsprüfung zu streng → Code anpassen
- Tax-Factor überprüfen (BDO: 0.88725)

---

## Performance-Monitoring

### Metriken sammeln
1. Aktiviere Debug-Mode
2. Führe 10 Transaktionen durch
3. Prüfe `ocr_log.txt` für Performance-Metriken:
```
[PERF-SYNC] OCR: 45.2ms [CACHED] (BALANCED)
[PERF-SYNC] Process: 12.3ms, Total scan: 67.8ms
```

### Erwartete Werte
- **Preprocess**: 15-30ms (balanced mode)
- **OCR (cached)**: 0-5ms
- **OCR (uncached)**: 40-80ms (Detail-ROIs)
- **Process**: 10-20ms
- **Total**: 60-150ms (Detail-Fenster), 40-80ms (Overview)

### Warnsignale
- ⚠️ Total > 300ms → ROI-Optimierung nötig
- ⚠️ OCR > 150ms → Canvas-Size reduzieren
- ⚠️ Process > 50ms → Parsing-Optimierung nötig

---

## Zusammenfassung

Alle Tests sollten erfolgreich durchlaufen. Bei Problemen:

1. **ROI-Kalibrierung**: `calibrate_detail_roi.py` ausführen
2. **Debug-Logs**: `ocr_log.txt` und Console prüfen
3. **Datenbank**: SQL-Queries zur Verifikation
4. **Performance**: Metriken im Debug-Mode überwachen

Bei weiteren Fragen siehe:
- `docs/DETAIL_WINDOW_TRANSACTION_CAPTURE_PLAN.md`
- `docs/DETAIL_WINDOW_ROI_REFERENCE.md`
- `AGENTS.md` (System-Übersicht)
