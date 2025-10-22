# Fix: Duplicate Transaction Prevention (2025-10-13)

## Problem

Beim Testen wurde festgestellt, dass Transaktionen aus dem alten Log **doppelt gespeichert** wurden:
- **Beispiel:** 953x Special Hump Mushroom wurde zweimal gespeichert:
  - ✅ 14:37:00 (korrekt, ursprünglicher Timestamp)
  - ❌ 14:55:00 (falsch, Duplikat mit neuem Timestamp)

## Ursache

Die **Fresh Transaction Detection** Logik (Zeilen 826-891 in `tracker.py`) hatte einen kritischen Fehler:

1. Sie prüfte nur ob ein **Item** im Baseline-Text vorkommt
2. Aber sie prüfte NICHT ob die **spezifische Transaktion** (item/qty/price) bereits in der DB existiert
3. Resultat: Alte Log-Einträge wurden als "frisch" erkannt und mit neuem Timestamp dupliziert

### Problematischer Ablauf:

```
Scan 1 (14:37):
- Log: "Transaction of Special Hump Mushroom x953 worth 28,590,000"
- Transaktion wird gespeichert: ID=5, Timestamp=14:37

Scan 2 (14:55):
- Log enthält IMMER NOCH: "Transaction of Special Hump Mushroom x953..."
- Fresh Detection: "Mushroom ist frisch!" (falsch! ist alt)
- Timestamp wird adjustiert: 14:37 → 14:55
- Neue Transaktion wird gespeichert: ID=3, Timestamp=14:55 (DUPLIKAT!)
```

## Lösung

**Vor dem Fix:**
```python
# Prüfte nur: Ist Item im Baseline-Text?
is_fresh = True
for search_pat in [
    fr'\btransaction\s+of\s+{re.escape(item_lc)}',
    # ...
]:
    if re.search(search_pat, baseline_lower, re.IGNORECASE):
        is_fresh = False
        break
```

**Nach dem Fix:**
```python
# Prüft: Existiert diese SPEZIFISCHE Transaktion bereits in DB?
existing = find_existing_tx_by_values(item_name, qty, int(price), 'buy', None, None)
if existing:
    if self.debug:
        log_debug(f"[DUPLICATE PREVENTION] '{item_name}' {qty}x @ {price} already in DB (ID={existing[0]}) - skipping timestamp adjustment")
    continue  # Diese Transaktion ist bereits in der DB, nicht duplizieren!
```

## Änderungen

**Datei:** `tracker.py`  
**Zeilen:** 826-918

**Key Changes:**
1. ✅ Prüfung gegen DB statt nur gegen Baseline-Text
2. ✅ Verwendet `find_existing_tx_by_values()` um exakte Duplikate zu finden
3. ✅ Verhindert Timestamp-Adjustierung wenn Transaktion bereits existiert
4. ✅ Detailliertes Debug-Logging für bessere Nachvollziehbarkeit

## Test

### Cleanup
```bash
python fix_mushroom_duplicate.py
```

**Ergebnis:**
- ✅ Duplikat (ID=3, 14:55) wurde entfernt
- ✅ Originale Transaktion (ID=5, 14:37) bleibt erhalten

### Verifikation
Nach dem Fix sollten:
1. ❌ Keine alten Log-Einträge mehr dupliziert werden
2. ✅ Neue Transaktionen (nach Collect/Relist) korrekt mit aktuellem Timestamp gespeichert werden
3. ✅ Historische Transaktionen im Log ignoriert werden wenn bereits in DB

## Related Issues

- **Missing Purchases:** Separate Bug - neue Käufe während Auto-Track werden nicht erfasst
  - Muss noch analysiert werden (welche Items fehlen?)
  - Möglicherweise Problem mit Burst-Scan Timing oder Window Detection

## Prevention

Der Fix fügt einen zusätzlichen **Sicherheits-Check** hinzu:
- Jede Transaktion wird gegen DB geprüft BEVOR Timestamp adjustiert wird
- Verhindert dass alte Log-Zeilen mit neuen Timestamps re-importiert werden
- Bewahrt die historische Integrität der Datenbank
