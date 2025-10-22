# Fix: OCR-Fehler mit fehlenden führenden Ziffern

**Datum:** 2025-10-12  
**Status:** ✅ FIXED

## Problem

Bei einem Auto-Track-Lauf um 04:04 Uhr wurde eine **200x Magical Shard** Transaktion mit dem **falschen Preis von 126,184 Silver** gespeichert. Der korrekte Preis sollte **585,585,000 Silver** gewesen sein.

### Root Cause

OCR-Fehler mit **fehlenden führenden Ziffern**:
- Korrekter OCR-Text (04:04:08): `"Transaction of Magical Shard x200 worth 585,585,000 Silver"`
- Fehlerhafter OCR-Text (04:04:13): `"Transaction of Magical Shard x200 worth 126,184 Silver"`

Die führenden Ziffern "5855" gingen verloren, nur "85000" blieb übrig. Nach Normalisierung wurde daraus "126184".

## Solution

### 1. Plausibilitätsprüfung in parsing.py (Lines 623-630)

```python
# Plausibility check for suspiciously low prices in transactions with high quantities
# OCR can lose leading digits (e.g., "585,585,000" → "126,184")
# Heuristic: transaction/purchased with qty >= 10 and price < 1,000,000 is likely missing digits
if typ in ('transaction', 'purchased') and price is not None and qty is not None:
    if qty >= 10 and price < 1_000_000:
        # Price too low for high quantity - likely OCR error with missing leading digits
        # Mark as invalid price to trigger UI fallback in tracker.py
        price = None
```

**Logik:**
- Bei `transaction` oder `purchased` Events
- Mit `qty >= 10` (hohe Menge)
- Und `price < 1,000,000` (unrealistisch niedriger Preis)
- → Setze `price = None` (ungültig)

### 2. Erweiterte UI-Fallback-Logik in tracker.py (Lines 1131-1141)

```python
# UI-Fallback für fehlende/ungültige Preise
# Zusätzlich: Prüfe auf unrealistisch niedrige Preise bei hohen Mengen
needs_fallback = (price is None or price <= 0)
if not needs_fallback and quantity is not None and quantity >= 10 and price < 1_000_000:
    # Unrealistisch niedriger Preis bei hoher Menge → wahrscheinlich OCR-Fehler
    log_debug(f"[PRICE] Suspiciously low price {price} for qty={quantity} '{ent.get('item')}' - attempting UI fallback")
    needs_fallback = True
```

**Erweitert bestehende UI-Fallback-Logik:**
- Prüft zusätzlich auf unrealistisch niedrige Preise (nicht nur `None` oder `<= 0`)
- Aktiviert UI-Metriken-basierte Preis-Rekonstruktion
- **Limitation:** Funktioniert NUR bei `collect`/`relist_full`/`relist_partial` Cases auf dem passenden Overview-Tab

### 3. Strikte Price-Validierung in tracker.py (Lines 1258-1263)

```python
# CRITICAL: Verwerfe Transaktionen ohne gültigen Preis
# Verhindert dass OCR-Fehler mit fehlenden führenden Ziffern falsche Preise speichern
if price is None or price <= 0:
    if self.debug:
        log_debug(f"drop candidate: invalid/missing price ({price}) for item='{ent.get('item')}' qty={quantity}")
    continue
```

**Last Line of Defense:**
- Verhindert Speicherung von Transaktionen mit ungültigem Preis
- Besser **keine** Transaktion als eine **falsche** Transaktion

## Testing

### Test 1: Parsing-Plausibilitätsprüfung (scripts/test_price_plausibility.py)

```
✅ Korrekter Preis (585M) → price=585585000 (akzeptiert)
✅ OCR-Fehler (126K bei qty=200) → price=None (abgelehnt)
✅ Legitim niedriger Preis (23.5K bei qty=5) → price=23500 (akzeptiert)
✅ Hoher Preis (765M bei qty=5000) → price=765000000 (akzeptiert)
```

### Test 2: Direct Parsing Test (test_parsing_direct.py)

```
Input: "Transaction of Magical Shard x200 worth 126,184 Silver"
Result: price=None
✅ SUCCESS: Plausibility check worked
```

## Database Correction

```python
# fix_db.py - Manuelle Korrektur der fehlerhaften Zeile
Vorher:  ID: 7 | 2025-10-12 04:04:00 | sell | 200x Magical Shard | Price: 126,184 | Case: sell_relist_full
Nachher: ID: 7 | 2025-10-12 04:04:00 | sell | 200x Magical Shard | Price: 585,585,000 | Case: sell_relist_full
✅ Preis korrigiert!
```

## Known Limitations

1. **Historische Sell-Transaktionen auf buy_overview:**
   - UI-Fallback NICHT verfügbar (ui_sell nur auf sell_overview verfügbar)
   - Solche Transaktionen werden verworfen wenn Preis ungültig ist
   - Trade-off: Lieber keine Transaktion als eine falsche

2. **UI-Fallback nur für collect/relist Cases:**
   - Nicht für alle Transaction-Types verfügbar
   - Nur wenn passende UI-Metriken vorhanden sind

## Impact

✅ **Verhindert zukünftige Speicherung falscher Preise** bei OCR-Fehlern mit fehlenden führenden Ziffern
✅ **Dreistufige Absicherung:** Parsing-Check → UI-Fallback → Strikte Validierung
✅ **Balance:** Erlaubt legitim niedrige Preise bei kleinen Mengen (z.B. 5x für 23.5K)
⚠️ **Trade-off:** Einige Transaktionen werden verworfen statt mit falschem Preis gespeichert

## Files Modified

- `parsing.py` - Plausibilitätsprüfung für unrealistische Preise
- `tracker.py` - Erweiterte UI-Fallback-Logik + Strikte Price-Validierung
- `instructions.md` - Dokumentation der Änderungen

## Files Created

- `scripts/test_price_plausibility.py` - Test Suite
- `test_parsing_direct.py` - Direct Parsing Test
- `check_db.py` - Database Query Tool
- `fix_db.py` - Database Correction Script
- `docs/OCR_PRICE_ERROR_FIX_2025-10-12.md` - Diese Dokumentation
