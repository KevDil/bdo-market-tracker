# Fix: Abgeschnittene Preise bei langen Itemnamen (2025-10-13)

## Problem

Bei Items mit langen Namen wird der Preis in der Transaction-Zeile abgeschnitten:

**Beispiel:**
```
Transaction of Very Long Item Name With Many Words x100 worth 1,234,567...
```

**Geparster Preis:** `1,234,567` (unvollständig!)  
**Echter Preis:** `1,234,567,890`

Das führt zu **massiv falschen Preisen** in der Datenbank.

## Root Cause

### OCR-Text Limitierung

Die Transaction-Zeile im BDO Central Market hat eine **feste Breite**. Bei langen Itemnamen wird der Preis am Ende abgeschnitten:

```
Normal:     "Transaction of Lion Blood x5000 worth 70,500,000 Silver"
Lang:       "Transaction of [Manor] Olvian Bookshelf x1 worth 15,500..."
Sehr lang:  "Transaction of Spirit's Leaf Extract x100 worth 1,234..."
```

Der OCR kann nur lesen was sichtbar ist → unvollständiger Preis!

### Warum wurde das nicht erkannt?

Die bisherige Preis-Validierung prüfte nur:
1. `price is None` (komplett fehlend)
2. API-basierte Plausibilitäts-Prüfung (zu hoch/niedrig vs. Market min/max)

Aber ein **abgeschnittener** Preis wie `1,234,567` für 100 Items:
- Ist NICHT `None` ✓
- Kann innerhalb der API min/max range liegen (z.B. wenn Range 10k-10M ist) ✓
→ Der abgeschnittene Preis sah **valide** aus und wurde gespeichert!

## Lösung

### Erkennungsmethode

Vergleiche den **geparsten Unit-Preis** mit dem **erwarteten Unit-Preis aus UI-Metriken**:

```python
parsed_unit = parsed_price / quantity
expected_unit = remainingPrice / (orders - ordersCompleted)

if expected_unit > parsed_unit * 10:
    # Abgeschnitten! parsed ist mindestens 10x zu klein
    needs_fallback = True
```

**Beispiel:**
- Geparst: `1,234,567` für 100 Items → Unit = `12,345`
- UI: `remainingPrice = 123,456,780` für 100 verbleibende Orders
- Expected Unit: `1,234,567` 
- **Faktor:** 1,234,567 / 12,345 = **100x** → ABGESCHNITTEN!

### UI-Metriken Fallback

Wenn abgeschnittener Preis erkannt wird, berechne den korrekten Preis aus UI:

```python
# remainingPrice = unit_price * (orders - ordersCompleted)
unit_price = remainingPrice / (orders - ordersCompleted)
total_price = unit_price * quantity_from_transaction
```

**Wichtig:** Verwende `quantity` aus der **Transaction-Zeile**, NICHT `ordersCompleted` aus UI!
- Transaction: Tatsächlich gekaufte Menge
- ordersCompleted: Gesamte abgeschlossene Orders (kann mehr sein bei Relist)

## Implementierung

**Datei:** `tracker.py`  
**Zeilen:** 1560-1583

### Code

```python
# CRITICAL: Erkenne ABGESCHNITTENE Preise (lange Itemnamen)
if not needs_fallback and price and quantity and quantity > 0 and wtype == 'buy_overview' and final_type == 'buy':
    item_lc_check = (ent.get('item') or '').lower()
    if item_lc_check in ui_buy:
        m = ui_buy[item_lc_check]
        orders = m.get('orders') or 0
        oc = m.get('ordersCompleted') or 0
        rem = m.get('remainingPrice') or 0
        denom = max(0, orders - oc)
        
        # Berechne erwarteten Unit-Preis aus UI
        if rem > 0 and denom > 0:
            expected_unit = rem / denom
            parsed_unit = price / quantity
            
            # Wenn geparster Unit-Preis viel kleiner ist als UI Unit-Preis → abgeschnitten!
            if expected_unit > parsed_unit * 10:  # Mindestens 10x Unterschied
                needs_fallback = True
```

## Test-Fälle

### Test 1: Kurzer Itemname (funktioniert bereits)
```
Item: "Lion Blood"
Transaction: "Transaction of Lion Blood x5000 worth 70,500,000 Silver"
Parsed: 70,500,000 ✅
Expected: 70,500,000 ✅
Result: Kein Fallback nötig
```

### Test 2: Langer Itemname (VORHER FEHLER, JETZT FIX)
```
Item: "[Manor] Olvian Bookshelf"
Transaction: "Transaction of [Manor] Olvian Bookshelf x1 worth 15,500..."
Parsed: 15,500 ❌ (abgeschnitten!)
UI: remainingPrice=155,000,000 für 10 verbleibende Orders
Expected Unit: 15,500,000
Parsed Unit: 15,500
Faktor: 1000x → ERKANNT!
Result: UI-Fallback → 15,500,000 ✅
```

### Test 3: Sehr langer Itemname
```
Item: "Spirit's Leaf Extract"
Transaction: "Transaction of Spirit's Leaf Extract x100 worth 1,234..."
Parsed: 1,234 ❌
Expected: 1,234,567
Faktor: 1000x → ERKANNT!
Result: UI-Fallback → korrekter Preis ✅
```

## Edge Cases

### Was wenn UI-Metriken nicht verfügbar sind?

Wenn das Item NICHT in `ui_buy` ist (z.B. bereits gesamte Order abgeschlossen):
- Kein UI-Fallback möglich
- Geparster Preis wird verwendet (potentiell falsch!)

**Mitigation:** 
- Plausibility-Check validiert gegen BDO Market API
- Sehr unrealistische Preise werden abgelehnt
- User sieht Warnung in Console

### Was bei Sell-Transaktionen?

Sell-Transaktionen verwenden **"worth X Silver"** (Netto nach Steuern).
Diese sind meist vollständig sichtbar, da:
1. Sell-Übersicht hat mehr Platz
2. "worth" kommt früher als "for" (wird nicht abgeschnitten)

**Lösung für Sells:**
- Ähnliche Logik in `ui_sell` Metriken (bereits vorhanden)
- Verwendet `salesCompleted` und `price` (Brutto)
- Berechnet: `quantity * price * 0.88725` (Netto)

## Verwandte Fixes

- **Duplicate Prevention:** `DUPLICATE_FIX_2025-10-13.md`
- **Missing Purchases:** `MISSING_PURCHASES_FIX_2025-10-13.md`
- **Parser Improvements:** Bessere "listed" Erkennung

## Limitationen

- Funktioniert nur für **buy_overview** (weil UI-Metriken benötigt)
- Benötigt `remainingPrice > 0` (mindestens 1 offene Order)
- Bei komplett abgeschlossenen Orders kein UI-Fallback möglich

## Empfehlung

Bei Items mit sehr langen Namen:
1. ✅ Auto-Track erfasst jetzt korrekt (mit UI-Fallback)
2. ⚠️ Bei Zweifeln: Prüfe Preis in GUI gegen BDO Market
3. 💡 Wenn möglich: Vermeide gleichzeitige Käufe (bessere Erfassung)
