# CRITICAL: Fix #1 WAS NEEDED - Fox Blood Analysis
**Datum**: 2025-10-21 00:15 UTC  
**Branch**: feature/detail-window-capture  
**Status**: 🔴 KRITISCHER FEHLER - FIX #1 MUSS ZURÜCK!

---

## Meine falsche Annahme war FALSCH!

### Was ich dachte (FALSCH):
❌ "Nur 'Relist' öffnet Detail-Fenster"
❌ "Preorder wird MIT erstem Kauf collected"
❌ "Baseline enthält NIEMALS bereits-collected Preorders"

### Die Realität (Fox Blood Beweis):
✅ User klickt "Relist" → **BDO collected Preorder SOFORT**
✅ Detail-Fenster öffnet **NACH** auto-collect
✅ Warehouse-Baseline **ENTHÄLT bereits-collected Preorder**
✅ Erster Kauf zeigt nur +5000 Delta, nicht +10000

---

## Fox Blood Test - Was wirklich passiert ist

### Erwartete Sequenz (User-Beschreibung)
1. Warehouse: 0 Fox Blood
2. Relist auf 5000x Preorder @ 115.5M
3. Kauf #1: 5000x @ 119M → Preorder mit collected (Total: 10,000x)
4. Kauf #2: 5000x @ 119M
5. Kauf #3: 5000x @ 119M
6. Kauf #4: 2247x @ 53,478,600
7. Neue Preorder: 2753x @ 65,521,400
8. Fenster geschlossen

### Was TATSÄCHLICH passiert ist (Logs)

#### 22:59:42 - Detail-Fenster öffnet
```
[DETAIL] Entered buy_item window
   Item: Fox Blood
   Balance baseline: 178,468,604,170
   Warehouse baseline: 10,000  ← PREORDER BEREITS COLLECTED!
```

**KRITISCH**: Warehouse = 10,000 bedeutet:
- 5,000x Preorder wurden **VOR** Detail-Window collected
- +5,000x alter Bestand (?) ODER
- +5,000x unbekannt

**Problem**: Baseline enthält Preorder, aber Balance-Delta wird sie nicht zeigen!

#### 22:59:44 - Kauf #1 (PREORDER VERLOREN!)
```
[DETAIL] Change detected
   Balance: 178,468,604,170 → 178,349,604,170 (Δ -119,000,000)
   Warehouse: 10,000 → 15,000 (Δ +5,000)

DB SAVE: buy 5000x Fox Blood price=119000000 case=buy_collect_ui_inferred
```

**Analyse**:
- Balance-Delta: **-119M** (nur 1× Kauf, NICHT Preorder!)
- Warehouse-Delta: **+5,000** (nur Kauf, Preorder war schon drin)
- **Gespeichert**: 5,000x @ 119M ❌ FALSCH!
- **Sollte sein**: 10,000x @ 234.5M (5000 @ 115.5M + 5000 @ 119M)

**Root Cause**: Preorder-Collect passiert **AUSSERHALB** des Detail-Windows, daher:
- Balance-Delta zeigt nur -119M (Kauf)
- Balance-Delta zeigt NICHT -115.5M (Preorder)
- Warehouse-Baseline bereits +5000 höher

#### 22:59:46 - Kauf #2
```
[DETAIL] Change detected
   Balance: 178,349,604,170 → 178,230,604,170 (Δ -119,000,000)
   Warehouse: 15,000 → 20,000 (Δ +5,000)

DB SAVE: buy 5000x Fox Blood price=119000000 case=buy_collect_ui_inferred
```

**Analyse**: Korrekt ✅

#### 22:59:48 - Kauf #3 (FALSCHE MENGE!)
```
[DETAIL] Change detected
   Balance: 178,230,604,170 → ??? (Δ -119,000,000)
   Warehouse: 20,000 → 22,247 (Δ +2,247)

DB SAVE: buy 2247x Fox Blood price=119000000 case=buy_collect_ui_inferred
```

**Analyse**:
- Balance-Delta: -119M (für 5000x Kauf)
- Warehouse-Delta: **+2,247** (nur Partial!)
- **Gespeichert**: 2,247x @ 119M ❌ FALSCH!
- **Sollte sein**: 5,000x @ 119M

**Root Cause**: Warehouse wurde **nicht korrekt aktualisiert**!
- Sollte: 20,000 → 25,000 (full +5000)
- Tatsächlich: 20,000 → 22,247 (nur +2,247)

**WAIT**: Das sieht aus wie **Partial-Update**! BDO zeigt nur Teil-Menge an!

#### 22:59:52 - Log-based Parsing (Rescue)
```
DB SAVE: buy 2247x Fox Blood price=53478600 case=buy_collect
```

**Analyse**: Log-based hat letzte Transaktion aus Transaction-Log geparst:
- 2247x @ 53,478,600 (der TEILKAUF #4!)
- Das ist RICHTIG, aber Detail-Window hatte ihn falsch erfasst

---

## Root Causes

### Problem #1: Preorder-Collect AUSSERHALB Detail-Window
**Timing**:
```
User klickt "Relist"
  ↓
BDO collected Preorder (Balance -115.5M, Warehouse +5000)
  ↓
Detail-Fenster öffnet (Baseline: Warehouse = 10,000)
  ↓
Kauf #1 (Balance -119M, Warehouse +5000)
  ↓
Detail-Window sieht: Δ Balance = -119M, Δ Warehouse = +5000
  ↓
Speichert: 5000x @ 119M ❌ (Preorder verloren!)
```

**Fix**: **BRAUCHE FIX #1 ZURÜCK!**
- Erkenne dass Baseline > 0 beim ersten Fenster-Öffnen
- Setze `_detail_pending_collect_qty` = Baseline-Warehouse
- Kombiniere mit erstem Kauf

### Problem #2: Warehouse Partial-Update
**Szenario**: Kauf #3 war 5000x @ 119M, aber:
- Balance-Delta: -119M (korrekt)
- Warehouse-Delta: +2,247 (nur partial!)

**Possible Reasons**:
1. BDO aktualisiert Warehouse **asynchron** über mehrere Frames
2. Kauf #4 (2247x) passierte **gleichzeitig** mit Kauf #3
3. OCR hat nur Zwischenzustand erfasst

**Fix**: Balance-Only Fallback sollte hier greifen!
- Balance -119M / desired_price = qty
- Aber Warehouse kam mit +2247 → beide Deltas vorhanden
- System dachte: "Komplett!" → Speicherte 2247x

**EIGENTLICHES PROBLEM**: 
- Warehouse +2247 ist **ZU KLEIN** für Balance -119M
- Plausibility-Check sollte dies erkennen!

---

## Korrigierter Fix-Plan

### 🔴 FIX #1: RE-IMPLEMENT Preorder-Collect Tracking (mit Verbesserungen)

#### Strategie A: Baseline-Warehouse als pending_collect
```python
# Bei Fenster-Öffnung
if not self._detail_window_active:
    # Baseline setzen
    self._detail_baseline_warehouse = current_warehouse
    
    # Wenn Warehouse > 0 beim Öffnen → Preorder bereits collected
    if current_warehouse > 0:
        self._detail_pending_collect_qty = current_warehouse
        if self.debug:
            log_debug(f"[DETAIL] 🔵 Warehouse baseline > 0: {current_warehouse}")
            log_debug(f"[DETAIL] 🔵 Assuming preorder already collected, will merge with first purchase")
```

**Problem**: Was wenn alter Bestand im Warehouse?
- User hatte 5000x Fox Blood von gestern
- Klickt Relist auf 5000x Preorder
- Warehouse = 10,000 (5000 alt + 5000 preorder)
- **Wir wissen nicht, wieviel davon Preorder ist!**

#### Strategie B: Log-based Preorder Detection
```python
#Parse OCR-Text für "Placed order" beim ersten Scan
if not self._detail_window_active:
    # Suche nach "Placed order of Fox Blood x5,000" im letzten Log
    preorder_match = re.search(r'Placed order.*?x\s*(\d+(?:,\d+)*)', ocr_text)
    if preorder_match:
        preorder_qty = int(preorder_match.group(1).replace(',', ''))
        self._detail_pending_collect_qty = preorder_qty
```

**Problem**: "Placed order" erscheint NACH dem Kauf, nicht vorher!

#### Strategie C: Balance-Delta Anomalie Detection (BEST!)
```python
# Bei erstem Purchase mit Warehouse-Delta
if self._detail_first_purchase and warehouse_delta > 0:
    # Prüfe ob Balance-Delta zu klein ist für die Menge
    expected_balance = desired_price * warehouse_delta
    if abs(balance_delta) < expected_balance * 0.8:  # 20% Toleranz
        # Balance-Delta zeigt NICHT die volle Menge!
        # → Preorder wurde außerhalb gecollected
        missing_qty = (expected_balance - abs(balance_delta)) // desired_price
        
        if self.debug:
            log_debug(f"[DETAIL] 🔵 Balance anomaly detected!")
            log_debug(f"[DETAIL] 🔵 Expected balance: -{expected_balance:,} for {warehouse_delta}x")
            log_debug(f"[DETAIL] 🔵 Actual balance: {balance_delta:,}")
            log_debug(f"[DETAIL] 🔵 Missing qty (preorder?): {missing_qty}x")
        
        # Füge fehlende Menge hinzu
        total_qty = warehouse_delta + missing_qty
```

**Vorteile**:
- Erkennt automatisch wenn Preorder außerhalb collected
- Kein Raten über Warehouse-Baseline nötig
- Funktioniert auch bei älterem Bestand

---

### 🟠 FIX #2: Plausibility-Check für Warehouse-Delta

**Problem**: Kauf #3 hatte Balance -119M, aber Warehouse +2247
- 119M / 2247 = 52,980 Silver/item
- Desired Price war ~119M / 5000 = 23,800 Silver/item
- **Ratio falsch!** 52,980 >> 23,800

**Lösung**: Plausibility-Check
```python
if warehouse_delta > 0 and balance_delta < 0:
    calculated_price_per_item = abs(balance_delta) / warehouse_delta
    
    if desired_price and abs(calculated_price_per_item - desired_price) / desired_price > 0.5:
        # Price-per-item weicht >50% ab → Warehouse-Delta unvollständig!
        if self.debug:
            log_debug(f"[DETAIL] ⚠️ Warehouse delta inconsistent!")
            log_debug(f"[DETAIL] ⚠️ Balance: {balance_delta:,}, Warehouse: {warehouse_delta}")
            log_debug(f"[DETAIL] ⚠️ Calculated: {calculated_price_per_item:.0f} Silver/item")
            log_debug(f"[DETAIL] ⚠️ Expected: {desired_price:,} Silver/item")
        
        # Fallback: Schätze Menge aus Balance
        estimated_qty = abs(balance_delta) // desired_price
        if 1 <= estimated_qty <= 5000:
            warehouse_delta = estimated_qty
            if self.debug:
                log_debug(f"[DETAIL] 🔧 Corrected qty: {estimated_qty}x (from balance/price)")
```

---

### 🟡 FIX #3: First-Purchase Flag

**Needed für Strategy C (Balance Anomaly Detection)**

```python
# In __init__
self._detail_first_purchase = True

# In _reset_detail_window_state
self._detail_first_purchase = True

# In _infer_transaction_from_deltas
if transaction and self._detail_first_purchase:
    self._detail_first_purchase = False
```

---

## Implementation-Plan (Revidiert)

### Phase 1: Re-Implement Fix #1 (mit Strategy C)
1. ✅ Re-Add `_detail_pending_collect_qty` State-Variable
2. ✅ Add `_detail_first_purchase` Flag
3. ✅ Implement Balance-Anomaly Detection (erste Purchase)
4. ✅ Kombiniere mit nachfolgenden Käufen
5. ✅ Test: Fox Blood Szenario

### Phase 2: Add Plausibility-Check (Fix #2)
1. ✅ Calculate price-per-item from deltas
2. ✅ Compare with desired_price (50% tolerance)
3. ✅ Fallback auf Balance-Only wenn inconsistent
4. ✅ Test: Partial-Warehouse-Update Szenario

### Phase 3: Keep Force-Save (Already Implemented)
1. ✅ Window-Close Force-Save bleibt
2. ✅ Kombiniert mit pending_collect_qty

---

## Test-Erwartungen (Fox Blood Wiederholung)

**Setup**: Wie Original-Test

**Erwartete DB-Einträge**:
```
buy | 10000x Fox Blood @ 234,500,000  | buy_collect_ui_inferred  ← Preorder + Kauf #1
buy | 5000x Fox Blood @ 119,000,000   | buy_collect_ui_inferred  ← Kauf #2
buy | 5000x Fox Blood @ 119,000,000   | buy_collect_ui_inferred  ← Kauf #3 (korrigiert!)
buy | 2247x Fox Blood @ 53,478,600    | buy_collect_ui_inferred  ← Kauf #4
```

**Erwartete Logs**:
```
🔵 Balance anomaly detected!
🔵 Expected balance: -234,500,000 for 5000x (preorder collected outside)
🔵 Actual balance: -119,000,000
🔵 Missing qty (preorder?): 5000x
🔵 Total quantity: 10000x (5000 warehouse + 5000 preorder)

⚠️ Warehouse delta inconsistent! (Kauf #3)
⚠️ Balance: -119,000,000, Warehouse: +2,247
⚠️ Calculated: 52,980 Silver/item, Expected: 23,800 Silver/item
🔧 Corrected qty: 5000x (from balance/price)
```

---

## Zusammenfassung

### Mein Fehler
❌ Ich habe Fix #1 entfernt basierend auf falscher Annahme
❌ Lion Blood Test war **nicht repräsentativ** (alter Bestand)
❌ Fox Blood Test zeigt die Realität: **Preorder wird VOR Detail-Window collected**

### Die Wahrheit
✅ BDO collected Preorders **BEIM RELIST-CLICK** (nicht beim Kauf)
✅ Detail-Window öffnet **NACH** auto-collect
✅ Warehouse-Baseline **ENTHÄLT** bereits-collected Preorder
✅ Balance-Delta zeigt **NICHT** die Preorder-Collect (war außerhalb)

### Fix-Plan
1. 🔴 **Re-Implement Fix #1** mit Balance-Anomaly Detection
2. 🟠 **Add Plausibility-Check** für Warehouse-Delta
3. 🟡 **Add First-Purchase Flag** für Anomaly-Detection
4. ✅ **Keep Force-Save** (bereits implementiert)

---

**Status**: 🔴 KRITISCHER FIX NÖTIG  
**Priority**: CRITICAL - Preorders gehen verloren bei jedem Relist-Flow

---

**Ende der Analyse**
