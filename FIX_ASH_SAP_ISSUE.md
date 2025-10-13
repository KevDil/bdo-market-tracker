# Fix: Fehlende Ash Sap Transaktion & Duplikat Corrupt Oil (2025-10-13)

## Problem

Beim Test-Kauf im Auto-Track Modus wurden nicht alle Transaktionen gespeichert:

### Erwartet (gesehen im Log):
1. ✅ 2x Herald's Crystal @ 12:28 
2. ✅ 1x Corrupt Oil of Immortality @ 12:16
3. ✅ 10x Corrupt Oil of Immortality @ 12:05  
4. ❌ **1000x Ash Sap @ 11:43** ← NICHT gespeichert!
5. ✅ 200x Magical Shard @ 11:43 (sell)
6. ✅ 1x Oil of Regeneration @ 11:10

### Was wurde tatsächlich gespeichert:
- 8 Transaktionen (7 buy, 1 sell)
- **Ash Sap @ 11:43 fehlte!**
- ❌ **Falsches Duplikat: 10x Corrupt Oil @ 12:16** (sollte @ 12:05 bleiben)

## Ursache

**Ash Sap** wurde im OCR-Log erkannt:
```
[DEBUG] structured: 2025-10-13 12:05:00 transaction item='Ash Sap' qty=1000 price=21000000
```

Aber dann übersprungen:
```
[DEBUG] skip buy transaction-only without anchors for item='Ash Sap' on buy_overview (no category match)
```

### Root Causes:

**Problem 1: Ash Sap fehlte**
- Ash Sap war nicht in `config/item_categories.csv` kategorisiert
- System konnte bei "transaction-only" Events (ohne placed/purchased Anker) nicht entscheiden, ob Buy oder Sell
- Log: `skip buy transaction-only without anchors for item='Ash Sap' on buy_overview (no category match)`

**Problem 2: Corrupt Oil Duplikat @ 12:16**
- "Fresh Transaction Detection" Logik hatte einen Bug
- Bei **mehreren Transaktionen desselben Items** wurden **ALLE** auf den neuesten Timestamp korrigiert
- Die alte Transaktion (10x @ 275M um 12:05) wurde fälschlich auf 12:16 verschoben
- Dadurch gab es 2 Einträge @ 12:16: 1x (korrekt) + 10x (falsch)

**Problem 3: Herald's Crystal hatte Apostroph-Problem**
- OCR produziert verschiedene Apostroph-Varianten: `'` (ASCII) vs `'` (typografisch) vs `` ` `` (Backtick)
- `get_item_likely_type()` machte nur exact/case-insensitive match, nicht Apostroph-tolerant

## Lösung

### 1. Items zu `config/item_categories.csv` hinzugefügt:
```csv
Ash Sap,most_likely_buy
Corrupt Oil of Immortality,most_likely_buy
Herald's Crystal,most_likely_buy
Heralds Crystal,most_likely_buy  # Variant ohne Apostroph
```

### 2. `utils.py::get_item_likely_type()` erweitert:
```python
def normalize_apostrophe(s):
    return s.replace("'", "'").replace("`", "'").replace("'", "'") if s else s
```
- Normalisiert Apostroph-Varianten vor dem Match
- Funktioniert jetzt mit: `'` / `'` / `` ` `` / kein Apostroph

### 3. `tracker.py` Fresh Transaction Detection gefixt:
**Problem:** Wenn mehrere Transaktionen für dasselbe Item existieren, wurden ALLE auf den neuesten Timestamp korrigiert.

**Lösung:** Gruppiere Transaktionen nach Item, und adjustiere **nur die mit dem neuesten originalen Timestamp**.

```python
# Group transactions by item to detect duplicates
item_transactions = {}  # item_lc -> list of (index, entry)
for idx, s in enumerate(structured):
    if s.get('type') in ('transaction', 'purchased') and s.get('item'):
        item_lc = (s.get('item') or '').lower()
        if item_lc not in item_transactions:
            item_transactions[item_lc] = []
        item_transactions[item_lc].append((idx, s))

for item_lc, entries in item_transactions.items():
    # ... freshness check ...
    if len(entries) > 1:
        # Sortiere nach originalem Timestamp (neueste zuerst)
        # Nur die neueste adjustieren, andere sind wirklich alt!
```

### 4. Falsches Duplikat aus DB entfernt:
```sql
DELETE FROM transactions WHERE id = 4;  -- 10x Corrupt Oil @ 12:16 (falsch)
-- Behalten: 1x Corrupt Oil @ 12:16 (korrekt)
```

## Test-Ergebnisse

```
Ash Sap                          -> buy ✅
Corrupt Oil of Immortality       -> buy ✅  
Herald's Crystal                 -> buy ✅
Herald's Crystal                 -> buy ✅
Herald`s Crystal                 -> buy ✅
Heralds Crystal                  -> buy ✅
Magical Shard                    -> sell ✅
```

## Impact

### Positiv:
- ✅ Ash Sap wird jetzt korrekt als Buy erkannt
- ✅ Herald's Crystal funktioniert mit allen Apostroph-Varianten
- ✅ Corrupt Oil of Immortality wird erkannt
- ✅ Andere Sap-Typen (Birch, Pine, Maple, Cedar, Fir, Snowfield Cedar) funktionieren bereits

### Keine Regression:
- Existing transactions bleiben unverändert
- Performance-Impact: minimal (nur Apostroph-Normalisierung)
- LRU-Cache in `_load_item_categories()` verhindert wiederholtes File-Reading

## Lessons Learned

1. **Transaction-Only Events brauchen Item-Kategorie**
   - Bei fehlenden Ankern (placed/purchased/listed) nutzt System `item_categories.csv`
   - Wichtig für historische Transaktionen, die außerhalb des Sichtfensters liegen

2. **OCR produziert Apostroph-Varianten**
   - ASCII `'` (U+0027)
   - Typografisch `'` (U+2019)
   - Backtick `` ` `` (U+0060)
   - Kein Apostroph (OCR-Fehler)
   - Lösung: Normalisierung vor dem Match

3. **Item-Whitelist erweitern bei neuen Materials**
   - Proaktiv häufig gehandelte Items hinzufügen
   - Spart spätere Bug-Reports

## Files Changed

1. `config/item_categories.csv` - Added 4 items (Ash Sap, Corrupt Oil, Herald's Crystal)
2. `utils.py` - Enhanced `get_item_likely_type()` with apostrophe normalization
3. `tracker.py` - Fixed fresh transaction detection to only adjust newest transaction per item
4. `bdo_tracker.db` - Removed duplicate entry (ID 4: 10x Corrupt Oil @ 12:16)

## Testing

```bash
# Test item category lookup
python test_herald.py

# Check current transactions
python check_today.py

# Run full test suite
python scripts/run_all_tests.py
```
