# Fix: Missing Purchases After Fast Buying (2025-10-13)

## Problem

Nach schnellen Käufen im buy_item Dialog wurden Transaktionen nicht erfasst:
- **2564x Maple Sap** (16:25) - ❌ NICHT erfasst
- **5000x Pure Powder Reagent** (16:26) - ❌ NICHT erfasst

## Ursachen-Analyse

### Was ist passiert?

1. **16:25** - User kauft 2564x Maple Sap im buy_item Dialog
2. **16:26** - User kauft 5000x Pure Powder Reagent im buy_item Dialog  
3. **16:26:04** - Tracker kehrt zu buy_overview zurück
   - **Burst-Scan startet:** 3 fast scans, 2 Sekunden Fenster
4. **16:26:06** - User ist schon wieder im nächsten buy_item Dialog
   - Transaction-Zeilen erscheinen JETZT erst im Log (zu spät!)
5. **Burst-Scan endet** bevor die Transaction-Zeilen erfasst wurden

### Root Cause

**Transaction-Zeilen erscheinen 1-3 Sekunden NACH dem Zurückkehren ins Overview!**

Das Timing ist kritisch:
- Bei **langsamen Käufen:** Burst-Scan fängt die Transaction-Zeile (funktioniert)
- Bei **schnellen Käufen:** User ist schon wieder im nächsten Dialog bevor die Transaction-Zeile erscheint (FEHLER!)

### Warum nicht im Log?

Der OCR-Text um 16:26:04 zeigt:
```
Maple Sap Orders 5000 Orders Completed 2564 Collect 17,295,600 Re-list
Pure Powder Reagent Orders 5000 Orders Completed 5000 Collect Re-list
```

**KEINE "Transaction of" oder "Purchased" Zeilen!**

Die Transaction-Zeilen waren entweder:
1. Noch nicht gerendert (Server-Lag)
2. Bereits rausgescrollt (sehr schnelle Käufe)
3. Vom OCR nicht erkannt (Render-Timing)

## Lösung

### 1. ❌ Falsche Annahme widerlegt

**FALSCH:** "Transaction-Zeilen waren im Log, aber wurden als 'listed' fehlinterpretiert"
- Fix war: Parser-Logik für "Re-list" Button verbessern
- Aber: Transaction-Zeilen waren GAR NICHT im OCR-Text!

**FALSCH:** "UI-Metriken sollten neue Transactions erstellen"
- Fix war: Vollständiger UI-Scan für `ordersCompleted > 0`
- Aber: User will dies NICHT - UI-Metriken nur für Preis-Fallback!

### 2. ✅ Korrekte Lösung: Längere Burst-Scans

**Erhöhe die Burst-Scan Dauer und Häufigkeit nach buy_item:**

**Vorher:**
```python
self._burst_fast_scans = 3
self._burst_until = now + timedelta(seconds=2)
self._request_immediate_rescan = 2
```

**Nachher:**
```python
self._burst_fast_scans = 8  # +167% mehr Scans
self._burst_until = now + timedelta(seconds=4.5)  # +125% längeres Fenster
self._request_immediate_rescan = 3  # +50% mehr immediate rescans
```

**Warum funktioniert das?**
- Mehr Zeit um auf Server-Response zu warten
- Mehr Scans um kurze Render-Fenster zu erwischen
- Fängt Transaction-Zeilen die erst 2-3 Sekunden später erscheinen

## Änderungen

**Datei:** `tracker.py`  
**Zeilen:** 660-670

**Datei:** `parsing.py`  
**Zeilen:** 234-247  
**Zweck:** Verhindert falsche "listed"-Erkennung bei Buy Overview UI-Buttons

**Datei:** `gui.py`  
**Zeilen:** 54-65  
**Zweck:** Auto-Track Start/Stop Logging für besseres Debugging

## Test-Szenarien

### Szenario 1: Langsamer Kauf (funktioniert bereits)
1. Buy item öffnen
2. Kaufen
3. 2-3 Sekunden warten
4. Zurück zu overview
5. ✅ Transaction-Zeile erscheint → wird erfasst

### Szenario 2: Schneller Kauf (VORHER FEHLER, JETZT FIX)
1. Buy item öffnen
2. Kaufen
3. SOFORT nächstes item öffnen
4. Transaction-Zeile erscheint im Hintergrund
5. ✅ Burst-Scan läuft 4.5s → erwischt die Transaction-Zeile

### Szenario 3: Sehr schnelle Käufe (Edge Case)
1. 3 Items in 5 Sekunden kaufen
2. Burst-Scans überlappen sich
3. ✅ Extended burst window fängt alle Transaktionen

## Limitationen

**Was passiert wenn Transaction-Zeilen KOMPLETT rauscrollen?**

Wenn User extrem schnell viele Items kauft (5+ Items in 10 Sekunden), können frühe Transaction-Zeilen aus dem sichtbaren Log scrollen bevor sie erfasst werden.

**Mögliche Lösungen (NICHT implementiert):**
1. UI-Metriken als Backup (User will dies nicht!)
2. Längere Burst-Fenster (würde Performance beeinträchtigen)
3. Transaction-History API (existiert nicht in BDO)

**Empfehlung für User:**
- Bei wichtigen Käufen: 1-2 Sekunden Pause zwischen Items
- Lässt dem Tracker Zeit die Transaction-Zeile zu erfassen
- Bei bulk-buying: Lieber 10-20 Sekunden Pause alle 5 Items

## Verwandte Fixes

- **Duplicate Prevention:** `DUPLICATE_FIX_2025-10-13.md`
- **OCR Logging:** Auto-Track Start/Stop jetzt im ocr_log.txt
- **Parser Improvements:** Bessere "listed" vs UI-Button Unterscheidung
