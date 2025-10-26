# Zusammenfassung aller Fixes (2025-10-13)

## Probleme und Lösungen

### ✅ Problem 1: Doppelte Transaktionen
**Symptom:** 953x Special Hump Mushroom wurde zweimal gespeichert (14:37 + 14:55)

**Root Cause:**
- Fresh Transaction Detection prüfte nur ob Item im Baseline-**Text** vorkommt
- Prüfte NICHT ob spezifische Transaktion (item/qty/price) bereits in **DB** existiert
- Alte Log-Einträge wurden als "frisch" erkannt → Duplikate mit neuem Timestamp

**Lösung:**
- DB-Check VOR Timestamp-Adjustment
- Nur adjustieren wenn Transaktion noch NICHT in DB existiert

**Datei:** `tracker.py` Zeilen 826-918  
**Dokumentation:** `DUPLICATE_FIX_2025-10-13.md`

---

### ✅ Problem 2: Fehlende Käufe (schnelles Buying)
**Symptom:** 2564x Maple Sap + 5000x Pure Powder Reagent nicht erfasst

**Root Cause:**
- Transaction-Zeilen erscheinen 1-3 Sekunden NACH Rückkehr ins Overview
- Bei schnellen Käufen: User schon im nächsten Dialog bevor Transaction-Zeile erscheint
- Burst-Scans waren zu kurz (2s, 3 scans)

**Lösung:**
- Burst-Scans erhöht: **4.5s, 8 scans** (vorher: 2s, 3 scans)
- +125% längeres Fenster, +167% mehr Scans
- Fängt verzögerte Transaction-Zeilen

**Datei:** `tracker.py` Zeilen 660-670  
**Dokumentation:** `MISSING_PURCHASES_FIX_2025-10-13.md`

---

### ✅ Problem 3: Abgeschnittene Preise
**Symptom:** Lange Itemnamen → Preis wird abgeschnitten ("1,234,567..." statt "1,234,567,890")

**Root Cause:**
- Transaction-Zeile hat feste Breite im BDO UI
- Lange Itemnamen → Preis am Ende abgeschnitten
- OCR sieht nur: `"Transaction of Very Long Name x100 worth 1,234,567..."`
- Abgeschnittener Preis sieht valide aus (nicht `None`, oft innerhalb API-Range)

**Lösung - 3-stufige Preis-Validierung:**

#### 1. Komplett fehlend
```python
if price is None or price <= 0:
    needs_fallback = True
```

#### 2. Implausibel (BDO Market API)
```python
plausibility = check_price_plausibility(item_name, quantity, price)
if not plausibility['plausible'] and reason in ('too_low', 'too_high'):
    needs_fallback = True  # Preis außerhalb API min/max range
```

#### 3. Abgeschnitten (UI-Metriken Vergleich)
```python
parsed_unit = price / quantity
expected_unit = remainingPrice / (orders - ordersCompleted)
if expected_unit > parsed_unit * 10:
    needs_fallback = True  # Mindestens 10x Unterschied → abgeschnitten!
```

**UI-Fallback berechnet korrekten Preis:**
```python
unit_price = remainingPrice / (orders - ordersCompleted)
correct_price = unit_price * quantity_from_transaction
```

**Datei:** `tracker.py` Zeilen 1550-1600  
**Dokumentation:** `TRUNCATED_PRICE_FIX_2025-10-13.md`

---

### ✅ Problem 4: Parser - Falsche "listed" Erkennung
**Symptom:** Buy Overview UI-Buttons ("Re-list") wurden als "listed" events fehlinterpretiert

**Root Cause:**
- Parser sah "Re-list" im Text → markierte als "listed"
- Aber: "Re-list" ist ein **UI-Button**, keine Transaction-Log Zeile
- Buy Overview: `"Maple Sap Orders 5000 ... Collect 17,295,600 Re-list"`

**Lösung:**
- Kontext-Prüfung: Nur echte Transaction-Log Einträge als "listed"
- Filtert "Orders Completed" Kontext aus (= UI, nicht Log)

**Datei:** `parsing.py` Zeilen 234-247

---

### ✅ Feature: Auto-Track Logging
**Was:** Start/Stop von Auto-Track wird im `ocr_log.txt` geloggt

**Nutzen:**
- Besseres Debugging
- Nachvollziehbarkeit wann Tracker aktiv war
- Einfacher zu sehen ob fehlende Transactions während/außerhalb Auto-Track

**Log-Format:**
```
[AUTO-TRACK] ▶️ STARTED - Auto-Track mode enabled
[AUTO-TRACK] ⏸️ STOPPED - Auto-Track mode disabled
```

**Datei:** `gui.py` Zeilen 54-65

---

## Geänderte Dateien

| Datei | Zeilen | Änderung |
|-------|--------|----------|
| `tracker.py` | 826-918 | Duplicate Prevention (DB-Check) |
| `tracker.py` | 660-670 | Extended Burst Scans |
| `tracker.py` | 1550-1600 | 3-stufige Preis-Validierung |
| `parsing.py` | 234-247 | "listed" Context-Prüfung |
| `gui.py` | 54-65 | Auto-Track Logging |

---

## Verwendung von UI-Metriken

**❌ FALSCH (wurde NICHT implementiert):**
```python
if no_transaction_line_exists:
    # Erstelle neue Transaction nur aus UI-Metriken
    # → NEIN! User will das nicht
```

**✅ KORREKT (implementiert):**
```python
if transaction_line_exists and (price_missing OR price_implausible OR price_truncated):
    # Verwende UI-Metriken um korrekten Preis zu berechnen
    unit_price = remainingPrice / (orders - ordersCompleted)
    correct_price = unit_price * quantity_from_transaction
```

**Wichtig:** 
- UI-Metriken nur als **Preis-Korrektur**
- NICHT um komplett neue Transactions zu erstellen
- Quantity kommt IMMER aus Transaction-Zeile (nicht `ordersCompleted`)

---

## Test-Empfehlungen

### Szenario 1: Normale Käufe
1. Item kaufen
2. 1-2 Sekunden warten
3. Zurück zu Overview
4. ✅ Transaction erfasst

### Szenario 2: Schnelle Käufe
1. 3 Items schnell hintereinander kaufen (jeweils < 2s)
2. Extended Burst-Scans laufen 4.5s pro Dialog-Return
3. ✅ Alle 3 Transaktionen erfasst

### Szenario 3: Langer Itemname
1. Item mit langem Namen kaufen (z.B. "[Manor] Olvian Bookshelf")
2. Transaction-Zeile hat abgeschnittenen Preis
3. ✅ UI-Fallback korrigiert Preis automatisch

### Szenario 4: Duplikate vermeiden
1. Alte Transaction ist im Log sichtbar
2. Neuer Scan verarbeitet das Log erneut
3. ✅ DB-Check verhindert Duplikat

---

## Limitationen & Bekannte Edge Cases

### 1. Sehr schnelles Bulk-Buying
**Problem:** 5+ Items in 10 Sekunden → frühe Transaction-Zeilen scrollen raus

**Mitigation:**
- Extended Burst-Scans fangen mehr, aber nicht alle
- Empfehlung: 1-2 Sekunden Pause zwischen Käufen

### 2. Komplett abgeschlossene Orders
**Problem:** Item nicht mehr in UI (alle Orders done) → keine UI-Metriken

**Mitigation:**
- BDO API Plausibilitäts-Check als Fallback
- Sehr unrealistische Preise werden abgelehnt

### 3. Items nicht in API
**Problem:** Neue/seltene Items haben keine Market-Daten

**Mitigation:**
- Parser versucht Preis trotzdem zu extrahieren
- Kein Fallback möglich wenn abgeschnitten

---

## Performance Impact

- **Burst-Scans:** Minimal (+2.5s pro buy_item return, nur bei aktiven Käufen)
- **API-Calls:** Bereits cached in `_unit_price_cache`
- **DB-Checks:** Indexed queries, < 1ms
- **Gesamt:** Keine merkbare Performance-Verschlechterung

---

## Nächste Schritte

1. ✅ Teste mit realen Käufen (verschiedene Item-Namen-Längen)
2. ✅ Verifiziere keine Duplikate mehr auftreten
3. ✅ Prüfe Preise gegen BDO Central Market Web
4. 📝 Falls weitere Probleme: Check `ocr_log.txt` für Details

---

## Related Documentation

- `DUPLICATE_FIX_2025-10-13.md` - Detaillierte Duplikat-Prevention
- `MISSING_PURCHASES_FIX_2025-10-13.md` - Extended Burst-Scans Analyse
- `TRUNCATED_PRICE_FIX_2025-10-13.md` - Abgeschnittene Preise Detection
