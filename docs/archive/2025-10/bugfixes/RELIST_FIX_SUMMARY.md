# 🎯 RELIST DETECTION FIX - FINAL IMPLEMENTATION

**Date**: 2025-10-21 20:30  
**Status**: ✅ READY FOR TESTING

---

## 🚨 CRITICAL INSIGHT

⚠️ **Transaction-Log ist NUR im Overview sichtbar!**

- Detail-Window zeigt **KEINEN** Transaction-Log
- Nach Relist wird das Window oft **sofort geschlossen**
- Overview wird möglicherweise **nicht mehr gescannt** (User navigiert weg)
- **→ Wir KÖNNEN NICHT auf Log-Parsing verlassen!**

**Lösung**: Alles SOFORT im Detail-Window speichern (während Relist-Detection)

---

## 📊 TEST-SZENARIO

### Ausgangssituation
```
Warehouse: 14,548 Trace of Nature
Preorder: 5000x @ 770,000,000 Silver (komplett gefüllt)
```

### User-Aktion
**Klickt "Relist" Button**

### Was passiert im Spiel
1. **Auto-Collect**: 5000x @ 770M werden ins Warehouse übertragen
2. **Instant Buy**: 21x @ 3,234,000 werden direkt vom Markt gekauft
3. **Neuer Preorder**: 4979x @ 766,766,000 wird platziert (5000 - 21 = 4979)

### Erwartete Ergebnisse
```
PREORDERS:
✅ ALT: ID=6, 5000x @ 770M, status='collected'
✅ NEU: ID=7, 4979x @ 766,766,000, status='active'

TRANSACTIONS:
✅ Auto-Collect: 5000x @ 770,000,000
✅ Instant Buy: 21x @ 3,234,000

WAREHOUSE: 14548 + 5000 + 21 = 19,569 ✓
```

---

## ✅ IMPLEMENTIERUNG

### 1. Relist-Erkennung (tracker.py L3834-3972)

```python
if is_relist_with_autocollect:
    # Pattern: balance↓ (neuer Preorder) + warehouse↑ (Auto-Collect + Instant Buy)
    
    # 1️⃣ Finde alten Preorder
    matching_preorder = find_matching_preorder(...)
    expected_autocollect_qty = matching_preorder['quantity']  # 5000
    
    # 2️⃣ Erkenne Instant Buy
    instant_buy_qty = warehouse_delta - expected_autocollect_qty
    # warehouse_delta = 5021, expected = 5000 → instant_buy = 21
    
    # 3️⃣ Speichere Auto-Collect Transaction
    preorder_unit_price = matching_preorder['price'] / matching_preorder['quantity']
    autocollect_total = preorder_unit_price * expected_autocollect_qty
    store_transaction_db(qty=5000, price=770,000,000)
    mark_collected(preorder_id=6)
    
    # 4️⃣ Speichere Instant Buy (falls vorhanden)
    if instant_buy_qty > 0:
        instant_buy_total = total_balance_decrease - new_preorder_total
        store_transaction_db(qty=21, price=3,234,000)
    
    # 5️⃣ Speichere neuen Preorder (angepasst für Instant Buy)
    new_qty = input_qty - instant_buy_qty  # 5000 - 21 = 4979
    new_price = input_price * new_qty
    store_preorder(qty=4979, price=766,766,000)
    
    return  # Fertig!
```

### 2. Fallback (tracker.py L4463-4513)

**Rolle**: NUR als BACKUP für Edge-Cases

- Läuft nur wenn Overview sichtbar ist (`wtype='buy_overview'`)
- Parst nur "Transaction of" Einträge (als Backup)
- Parsed NICHT "Purchased" oder "Placed order" (schon in Detail-Window erledigt)

**Backup-Szenarien**:
- Detail-Window schloss zu schnell (vor Delta-Detection)
- Balance/Warehouse Deltas nicht erkannt (Timing-Problem)

---

## 🧪 TESTING

### Test-Prozedur

```powershell
# 1. DB zurücksetzen
python scripts/utils/reset_db.py

# 2. GUI starten (Debug Mode aktivieren!)
python gui.py

# 3. Im Spiel:
#    - Preorder platzieren: 5000x Trace of Nature @ 770M
#    - Warten bis komplett gefüllt
#    - "Relist" Button klicken
#    - Warten 2-3 Sekunden

# 4. Status prüfen
python check_relist_state.py

# 5. Vollständige Verification
python verify_relist_fallback_fix.py
```

### Erwartete Logs

```
[RELIST-DETECT] ✅ Pattern matched: balance -770,000,000, warehouse +5021
[RELIST] Instant buy detected: 21x (warehouse 5021 > expected 5000)
[RELIST] Auto-collect: 5,000x @ 154,000 = 770,000,000 Silver
[RELIST] ✅ Auto-collect saved: 5,000x @ 770,000,000
[RELIST] ✅ Old preorder ID=6 marked collected
[RELIST] ✅ Instant buy saved: 21x @ 154,000 = 3,234,000
[RELIST] ✅ New preorder saved: 4,979x @ 154,000 = 766,766,000
```

---

## 🎯 VORTEILE

✅ **Timing-unabhängig**: Funktioniert auch wenn Window sofort schließt  
✅ **Kein Log-Parsing nötig**: Alles aus Detail-Window Deltas berechnet  
✅ **Trennt Instant Buy**: Keine kombinierten Transactions mehr  
✅ **Korrekte Preorder-Qty**: Automatisch angepasst (5000 - 21 = 4979)  
✅ **Nutzt Preorder-Preis**: Genaueste Auto-Collect Berechnung  
✅ **Keine Duplikate**: Alle Saves mit Duplikatsprüfung

---

## 🔍 EDGE CASES

### Fall 1: Relist OHNE Instant Buy
```
Warehouse: +5000 (nur Auto-Collect)
→ instant_buy_qty = 5000 - 5000 = 0
→ Kein Instant Buy gespeichert ✓
→ Neuer Preorder: 5000x (Original-Qty) ✓
```

### Fall 2: Instant Buy füllt KOMPLETTEN neuen Preorder
```
Warehouse: +5500 (5000 Auto-Collect + 500 Instant Buy)
Input: 500x @ 150,000
→ instant_buy_qty = 5500 - 5000 = 500
→ new_qty = 500 - 500 = 0
→ Kein neuer Preorder gespeichert ✓
```

### Fall 3: Window schließt zu schnell
```
Detail-Window schließt VOR Delta-Detection
→ Fallback greift (parst "Transaction of" im Overview)
→ Backup-Transaction gespeichert ✓
```

---

## 📝 WICHTIGE HINWEISE

1. **Debug Mode aktivieren** beim Testen (für detaillierte Logs)
2. **Cached Input Fields** müssen vorhanden sein (werden bei Baseline gespeichert)
3. **Preorder muss existieren** (find_matching_preorder muss erfolgreich sein)
4. **Balance-Delta muss negativ sein** (Geld ausgegeben für neuen Preorder)
5. **Warehouse-Delta muss positiv sein** (Items erhalten)

---

## 🚀 NÄCHSTE SCHRITTE

1. ✅ Code implementiert
2. ⏳ **JETZT: Testing mit echtem Relist**
3. ⏳ Logs analysieren
4. ⏳ DB-State verifizieren
5. ⏳ Edge-Cases testen

**Bitte teste und gib Feedback!** 🎯
