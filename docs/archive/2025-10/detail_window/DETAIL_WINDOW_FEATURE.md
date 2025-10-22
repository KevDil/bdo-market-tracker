# Detail-Fenster Transaktionserkennung - User Guide

## Übersicht

Die **Detail-Fenster Transaktionserkennung** ist ein neues Feature, das Transaktionen direkt im Buy-/Sell-Detail-Fenster erkennt, auch wenn das Transaktionslog nach der Transaktion nicht sichtbar ist.

**Status**: ✅ Implementiert und getestet  
**Version**: 1.0  
**Datum**: 2025-10-20

---

## Wie es funktioniert

### Automatische Erkennung

Wenn Sie eine Transaktion im Detail-Fenster durchführen:

1. **Öffnen Sie ein Detail-Fenster** (Sell-Item oder Buy-Item)
2. **Stellen Sie Preis und Menge ein**
3. **Bestätigen Sie die Transaktion** (Register/Buy → Yes)
4. **Bleiben Sie im Detail-Fenster** (optional)

Die Anwendung erkennt die Transaktion automatisch durch Überwachung von:
- **Kontostand (Balance)**: Ändert sich nach erfolgreicher Transaktion
- **Lagerbestand (Warehouse Quantity)**: Steigt bei Kauf, sinkt bei Verkauf

### Was wird erkannt?

- **Item-Name**: Aus dem Detail-Fenster
- **Menge**: Berechnet aus Warehouse-Delta
- **Preis**: Berechnet aus Balance-Delta (nach Steuern korrigiert)
- **Typ**: Sell oder Buy
- **Zeitstempel**: System-Zeit (nicht Game-Zeit!)

---

## Vorteile

### Ohne Detail-Fenster-Erkennung
❌ Transaktion nur im Log sichtbar  
❌ Wenn Sie Detail-Fenster nicht verlassen: **Transaktion wird nicht gespeichert**  
❌ Mehrfach-Transaktionen im Detail-Fenster gehen verloren

### Mit Detail-Fenster-Erkennung
✅ Transaktion wird **sofort erkannt** (< 1 Sekunde nach Bestätigung)  
✅ Kein Verlassen des Detail-Fensters nötig  
✅ **Mehrfach-Transaktionen** werden alle erkannt  
✅ Automatische **Duplikat-Prävention** (Detail + Log)

---

## Limitierungen

### System-Timestamp
- **Detail-Transaktionen** verwenden **System-Zeit** (nicht Game-Zeit)
- **Grund**: Game-Zeit ist im Detail-Fenster nicht verfügbar
- **Markierung**: `tx_case = 'sell_collect'` oder `'buy_collect'` zeigt Detail-Transaktion an

### OCR-Abhängigkeit
- Erkennung basiert auf OCR-Extraktion von Balance/Warehouse
- Bei **OCR-Fehlern** kann Transaktion fehlschlagen
- **Lösung**: ROI-Kalibrierung mit `calibrate_detail_roi.py`

### Nur direkte Transaktionen
- Detail-Fenster-Erkennung funktioniert nur für **direkte Käufe/Verkäufe**
- **Platzierte Orders** (Placed/Withdrew) werden weiterhin aus dem Log erkannt

---

## Kalibrierung

Falls Transaktionen nicht erkannt werden:

### ROI-Kalibrierung

1. **Öffne ein Detail-Fenster** im Spiel
2. **Führe Kalibrierung aus**:
```powershell
# Für Sell-Item-Fenster
python scripts\utils\calibrate_detail_roi.py --image dev-screenshots\sell_item_marked.png --type sell_item

# Für Buy-Item-Fenster
python scripts\utils\calibrate_detail_roi.py --image dev-screenshots\buy_item_marked.png --type buy_item
```

3. **Prüfe Ergebnis**:
- Öffne `debug/calibrate_sell_item_roi.png`
- **Grünes Rechteck**: Item-Name (oben links)
- **Violettes Rechteck**: Balance (mittig links)
- **Gelbes Rechteck**: Warehouse (oben/unten links)

4. **Falls ROIs falsch**:
- Öffne `utils.py`
- Suche nach `detect_detail_item_name_roi`, `detect_detail_balance_roi`, `detect_detail_warehouse_roi`
- Passe Prozent-Werte an
- Wiederhole Kalibrierung

---

## Troubleshooting

### Problem: Transaktion wird nicht erkannt

**Lösung 1 - Debug-Mode aktivieren**:
1. Öffne `config.py`
2. Setze `DEBUG_MODE = True`
3. Starte GUI neu
4. Prüfe Console-Output

**Lösung 2 - ROI-Kalibrierung**:
```powershell
python scripts\utils\calibrate_detail_roi.py --image debug\debug_orig.png --type sell_item
```

**Lösung 3 - OCR-Log prüfen**:
```powershell
Get-Content ocr_log.txt | Select-Object -Last 50
```
Sollte enthalten: `Balance: ... Silver` und `Warehouse Quantity: ...`

---

### Problem: Duplikate in Datenbank

**Symptom**: Gleiche Transaktion 2x gespeichert

**Diagnose**:
```sql
SELECT item_name, quantity, price, COUNT(*) as count
FROM transactions 
WHERE timestamp >= datetime('now', '-5 minutes')
GROUP BY item_name, quantity, price
HAVING count > 1;
```

**Lösung**: 
- Duplikate entfernen: `python scripts\utils\dedupe_db.py`
- Datenbank neu aufsetzen: `python scripts\utils\reset_db.py`

---

### Problem: Falsche Preise

**Symptom**: Preis stimmt nicht mit eingestelltem Preis überein

**Ursache**: 
- OCR-Fehler bei Balance-Extraktion
- Tax-Factor-Berechnung

**Diagnose**:
1. Debug-Mode aktivieren
2. Prüfe Console: `[DETAIL] Change detected ... (Δ Balance: +...)`
3. Berechne manuell:
   - **Sell**: Brutto = Balance-Delta / 0.88725
   - **Buy**: Brutto = |Balance-Delta|

**Lösung**: ROI für Balance anpassen

---

## FAQ

### Q: Muss ich das Detail-Fenster verlassen?
**A**: Nein! Die Transaktion wird im Detail-Fenster erkannt. Sie können beliebig lange im Detail-Fenster bleiben.

### Q: Werden mehrfach-Transaktionen erkannt?
**A**: Ja! Sie können mehrere Transaktionen nacheinander im Detail-Fenster durchführen, alle werden erkannt.

### Q: Warum System-Zeit statt Game-Zeit?
**A**: Im Detail-Fenster ist keine Game-Zeit verfügbar (Log ist nicht sichtbar). System-Zeit ist eine Näherung.

### Q: Wie erkenne ich Detail-Transaktionen in der Datenbank?
**A**: `tx_case = 'sell_collect'` oder `'buy_collect'` ohne zugehörigen Log-Eintrag.

### Q: Kann ich das Feature deaktivieren?
**A**: Ja, öffne `tracker.py` und kommentiere den Call zu `_monitor_detail_window()` in `process_ocr_text()` aus.

---

## Performance

### Zusätzlicher Overhead

- **Overview-Fenster**: Keine Änderung (0ms)
- **Detail-Fenster**: +150-300ms pro Scan
  - Item-Name-ROI: ~50-100ms (nur beim Eintritt)
  - Balance-ROI: ~50-100ms
  - Warehouse-ROI: ~50-100ms

### Optimierungen

- **OCR-Cache**: Identische ROIs werden nicht neu ausgelesen
- **Lazy-Evaluation**: Item-Name nur beim Fenster-Eintritt
- **Parallel-Processing**: Balance/Warehouse werden parallel verarbeitet (geplant)

---

## Export

Detail-Transaktionen werden normal exportiert:

### CSV-Export
```csv
item_name,quantity,price,transaction_type,timestamp,tx_case
Powder of Darkness,10,1690140,sell,2025-10-20 15:30:45,sell_collect
```

### JSON-Export
```json
{
  "item_name": "Powder of Darkness",
  "quantity": 10,
  "price": 1690140,
  "transaction_type": "sell",
  "timestamp": "2025-10-20 15:30:45",
  "tx_case": "sell_collect"
}
```

**Hinweis**: `tx_case` zeigt an, dass es eine Detail-Transaktion ist.

---

## Weitere Dokumentation

- **Implementierungs-Details**: `docs/DETAIL_WINDOW_TRANSACTION_CAPTURE_PLAN.md`
- **ROI-Referenz**: `docs/DETAIL_WINDOW_ROI_REFERENCE.md`
- **Manual Tests**: `tests/manual/test_detail_window_e2e.md`
- **Unit-Tests**: `tests/unit/test_detail_window_transactions.py`
- **System-Übersicht**: `AGENTS.md`

---

## Support

Bei Fragen oder Problemen:

1. **Debug-Mode aktivieren**: `DEBUG_MODE = True` in `config.py`
2. **Logs prüfen**: `ocr_log.txt` und Console-Output
3. **ROI-Kalibrierung**: `calibrate_detail_roi.py` ausführen
4. **Issue erstellen**: Mit Debug-Logs und Screenshots

---

**Version**: 1.0  
**Letzte Aktualisierung**: 2025-10-20  
**Feature-Status**: ✅ Produktionsreif
