# Pig Blood Test - Analyse & Fix-Plan (2025-10-20 22:18)

## Test-Szenario

**Ausgangssituation:** 0x Pig Blood im Warehouse

1. Click "Relist" auf 5000x Pig Blood Preorder
2. Detail-Fenster öffnet **OHNE** dass Preorder collected ist
3. **Kauf #1:** 5000x @ 13,981,680 → Preorder automatisch mit collected (5000x @ 14,200,000)
   - **Erwartet:** 10,000x total für 28,181,680 Silver
4. **Kauf #2:** 5000x @ 14,137,210
5. **Neue Preorder:** 5000x @ 13,800,000 gesetzt
6. Detail-Fenster geschlossen

## Was tatsächlich gespeichert wurde

### Database-Einträge (3 Transaktionen)
```
timestamp           | type | qty  | price      | content_hash     | source
--------------------|------|------|------------|------------------|------------------
2025-10-20 22:18:00 | buy  | 5000 | 13,981,680 | e003a2f72326140a | Log-based (buy_collect)
2025-10-20 22:18:00 | buy  | 5000 | 14,200,000 | aa57e7a48e834121 | Log-based (buy_relist_full)
2025-10-20 22:18:36 | buy  | 5000 | 14,137,210 | c0ef77831a682757 | Detail-Window (ui_inferred)
```

### Timeline-Rekonstruktion

#### Phase 1: Detail-Window Opening (22:18:33)
```
22:18:33.385681 [DETAIL] Entered buy_item window
   Balance baseline:   178,904,126,325
   Warehouse baseline: 10,000           ← Preorder BEREITS collected!
```

**Problem erkannt:** Baseline = 10,000 statt 0  
→ Preorder (5000x) + alte Items (5000x) wurden VOR Baseline-Setting collected

#### Phase 2: Kauf #1 (22:18:36)
```
22:18:36.009288 Balance:   178,889,989,115  (Δ -14,137,210)
22:18:36.009288 Warehouse: 15,000           (Δ +5,000)
22:18:36.025742 ✅ DB SAVE: 5000x @ 14,137,210 (buy_collect_ui_inferred)
```

**Detail-Window erfasste:**
- Menge: 5000x ✅ (warehouse 10000 → 15000)
- Preis: 14,137,210 ✅ (balance delta)
- **ABER:** Preorder (5000x @ 14,200,000) fehlt!

#### Phase 3: Kauf #2 erkannt (22:18:38)
```
22:18:38.766757 Balance:   178,876,189,115  (Δ -13,800,000)
22:18:38.766962 Warehouse: 15,000           (Δ 0) ← Neue Preorder!
22:18:38.769177 ⚠️ warehouse_delta=0 but balance negative
22:18:38.769410 Buy-Transaction incomplete (waiting 0.00s/3.0s)
```

**Balance-Only Timeout aktiviert:** 3 Sekunden warten...

```
22:18:41.603334 Balance: None     ← Detail-Window geschlossen!
22:18:41.603605 Warehouse: None
```

**Problem:** Balance-Only Timeout abgebrochen weil Detail-Window geschlossen wurde  
→ Kauf #2 NICHT von Detail-Window gespeichert

#### Phase 4: Log-based Parsing (22:18:43)
```
22:18:43.117366 structured: placed item='Pig Blood' qty=5000 price=13800000
22:18:43.117565 structured: purchased item='Pig Blood' qty=5000 price=14137210
22:18:43.117762 structured: purchased item='Pig Blood' qty=5000 price=13981680
22:18:43.117933 structured: transaction item='Pig Blood' qty=5000 price=14200000
```

**Log-based Parsing fand:**
- ✅ Placed: 5000x @ 13,800,000 (neue Preorder)
- ✅ Purchased #1: 5000x @ 14,137,210 (Kauf #2)
- ✅ Purchased #2: 5000x @ 13,981,680 (Kauf #1)
- ✅ Transaction: 5000x @ 14,200,000 (ursprüngliche Preorder collected)

**Clustering-Ergebnisse:**
```
22:18:43.131723 ✅ DB SAVE: 5000x @ 14,200,000 (buy_relist_full) - Preorder
22:18:43.137940 ✅ DB SAVE: 5000x @ 13,981,680 (buy_collect) - Kauf #1
22:18:43.132781 ❌ DEDUPE-LOG: Skip - 14,137,210 already in Detail-Window
```

**Dedupe hat funktioniert:**
- Kauf #2 (14,137,210) wurde NICHT doppelt gespeichert
- Detail-Window-Version (22:18:36) bleibt erhalten

## Problem-Analyse

### ✅ Was funktioniert hat

1. **Detail-Window Baseline:** Korrekt gesetzt (10,000 statt 0-Forcing)
2. **Kauf #1 erfasst:** 5000x @ 14,137,210 via Delta (warehouse 10k→15k)
3. **Dedupe funktioniert:** Log-based hat Detail-Window-TX nicht überschrieben
4. **Log-based Fallback:** Preorder (14,200,000) und Kauf #1 Alt-Preis (13,981,680) erfasst

### ❌ Was NICHT funktioniert hat

#### Problem #1: Preorder-Collect fehlt in Detail-Window
**Symptom:**  
- Warehouse baseline = 10,000 (Preorder bereits collected)
- Erster Delta: 10,000 → 15,000 = +5,000 (nur neuer Kauf)
- **Preorder (5000x @ 14,200,000) NICHT erfasst**

**Root Cause:**  
Warehouse-Only Delta Filter (Fix #3) verwirft Preorder-Collect:
```python
if warehouse_delta > 0 and balance_delta == 0:
    log_debug("Preorder-Collect detected, waiting for actual purchase")
    return None  # ← Preorder wird verworfen!
```

**Impact:**  
Bei kombinierten Scenarios (Preorder + Kauf):
- Nur der neue Kauf wird erfasst
- Preorder geht verloren (muss vom Log-Parser gerettet werden)

#### Problem #2: Balance-Only Timeout abgebrochen
**Symptom:**  
- Kauf #2: Balance -13,800,000, Warehouse 0 (neue Preorder)
- Balance-Only Timer gestartet: 0.00s/3.0s
- Detail-Window nach ~3s geschlossen
- **Kauf #2 NICHT gespeichert** (Balance-Only Timeout unvollständig)

**Root Cause:**  
Balance-Only Fallback wird abgebrochen wenn:
```python
if current_balance is None or current_warehouse is None:
    return  # ← Detail-Window geschlossen, Timeout abgebrochen!
```

**Impact:**  
Bei schnellem Schließen des Detail-Windows (<3s):
- Balance-Only Transaktionen gehen verloren
- Nur Log-based Parsing rettet sie

#### Problem #3: Falsche Preise im Log-based Parsing
**Symptom:**  
Log-based parsed ZWEI unterschiedliche Preise für Kauf #1:
- Detail-Window: 14,137,210 ✅ (korrekt, Balance-Delta)
- Log-based: 13,981,680 ❌ (falsch, OCR-Fehler?)

**Analyse:**  
```
structured: purchased item='Pig Blood' qty=5000 price=14137210  ← Korrekt
structured: purchased item='Pig Blood' qty=5000 price=13981680  ← Falsch
```

**Root Cause:**  
OCR las zwei verschiedene Preise aus dem Log-ROI:
- Möglicherweise zwei Zeilen für gleichen Kauf
- Oder OCR-Variationen bei wiederholten Scans

**Impact:**  
Falsche Transaktion (13,981,680) wird zusätzlich gespeichert  
→ **4 Käufe statt 2 tatsächlicher Käufe!**

## Zusammenfassung: Was SOLLTE gespeichert werden

### Erwartete Transaktionen (3)
1. **Preorder-Collect:** 5000x @ 14,200,000 (bei Kauf #1 auto-collected)
2. **Kauf #1:** 5000x @ 13,981,680 (oder 14,137,210 - unklar welcher Preis stimmt)
3. **Kauf #2:** 5000x @ 14,137,210

### Tatsächlich gespeichert (3)
1. ✅ **Preorder:** 5000x @ 14,200,000 (Log-based)
2. ✅/❌ **Kauf #1 (Version A):** 5000x @ 13,981,680 (Log-based, möglicherweise OCR-Fehler)
3. ✅ **Kauf #2:** 5000x @ 14,137,210 (Detail-Window)

**Problem:** Kauf #1 hat ZWEI verschiedene Preise in den Logs!
- Detail-Window sagt: 14,137,210
- Log-based sagt: 13,981,680

**Frage:** Welcher Preis ist korrekt?  
→ Vermutlich Detail-Window (14,137,210), da Balance-Delta = -14,137,210

## Fix-Plan

### 🔴 CRITICAL: Fix #1 - Preorder-Collect Handling

**Problem:** Warehouse-Only Delta wird verworfen  
→ Preorder geht verloren bei kombinierten Szenarien

**Lösung:** Implementiere `_detail_pending_collect_qty` Feature

**Logik:**
```python
# Bei Warehouse-Only Delta (Preorder-Collect ohne Kauf):
if warehouse_delta > 0 and balance_delta == 0:
    # Speichere Preorder-Menge für späteren Kauf
    self._detail_pending_collect_qty = warehouse_delta
    log_debug(f"[DETAIL] Preorder-Collect pending: {warehouse_delta}x")
    return None  # Warte auf echten Kauf

# Bei echtem Kauf mit pending Preorder:
if balance_delta < 0 and self._detail_pending_collect_qty > 0:
    # Kombiniere Preorder + Kauf
    total_qty = self._detail_pending_collect_qty + warehouse_delta
    log_debug(f"[DETAIL] Combined: {total_qty}x (preorder {self._detail_pending_collect_qty} + purchase {warehouse_delta})")
    
    # Erstelle ZWEI Transaktionen:
    # 1. Preorder-Collect (qty=pending, price=0 oder market price)
    # 2. Neuer Kauf (qty=warehouse_delta, price=balance_delta)
    
    self._detail_pending_collect_qty = 0  # Reset
```

**Änderungen:**
- Neues Feld: `self._detail_pending_collect_qty = 0`
- Reset in `_reset_detail_window_state()`
- Logik in `_infer_transaction_from_deltas()` erweitern

---

### 🟠 HIGH: Fix #2 - Balance-Only bei Detail-Window-Close

**Problem:** Balance-Only Timeout wird abgebrochen wenn Detail-Window geschlossen wird  
→ Kauf #2 geht verloren

**Lösung:** Speichere Balance-Only sofort beim Detail-Window-Close

**Logik:**
```python
def _monitor_detail_window(...):
    # Bei Detail-Window-Exit:
    if current_balance is None or current_warehouse is None:
        # Detail-Window wurde geschlossen
        
        # Prüfe ob incomplete Balance-Only Transaction pending ist
        if self._detail_partial_balance_delta < 0 and self._detail_partial_warehouse_delta == 0:
            log_debug("[DETAIL] Window closed with pending balance-only transaction")
            
            # Force Balance-Only Transaction NOW (skip Timeout)
            transaction = self._infer_balance_only_transaction(...)
            if transaction:
                self.store_transaction_db(transaction)
        
        self._reset_detail_window_state()
        return
```

**Neue Funktion:**
```python
def _infer_balance_only_transaction(self, window_type, current_metrics, last_metrics):
    """Force Balance-Only Transaction (Detail-Window closed prematurely)"""
    if window_type == 'buy_item' and self._detail_partial_balance_delta < 0:
        desired_price = current_metrics.get('desired_price') or last_metrics.get('desired_price')
        if desired_price:
            estimated_qty = abs(self._detail_partial_balance_delta) // desired_price
            if 1 <= estimated_qty <= 5000:
                return {
                    'quantity': estimated_qty,
                    'price': abs(self._detail_partial_balance_delta),
                    'transaction_type': 'buy',
                    'tx_case': 'buy_collect_balance_only_forced',
                    ...
                }
    return None
```

---

### 🟡 MEDIUM: Fix #3 - OCR-Duplikate verhindern

**Problem:** Log-based Parsing liest gleichen Kauf mit zwei verschiedenen Preisen  
→ Falsche Transaktion gespeichert

**Analyse benötigt:**
- Warum zwei Preise für Kauf #1?
- OCR-Fehler oder echte zwei Zeilen?
- Prüfe `ocr_log.txt` für 22:18:43 Log-ROI-Text

**Mögliche Lösungen:**
1. Dedupe innerhalb Log-based Parsing (gleiche Menge + ähnlicher Timestamp)
2. Preis-Plausibilitäts-Check gegen Detail-Window-Preis
3. OCR-Verbesserung für Log-ROI

**Action:** Weitere Analyse erforderlich

---

## Test-Requirements nach Fixes

### Test #1: Preorder-Collect Combo
**Szenario:**
- 5000x Preorder
- Relist → Detail-Window öffnet (warehouse=0)
- Kauf 5000x
- → Warehouse: 0 → 5000 → 10000

**Erwartung:**
- Transaction #1: 5000x @ Preorder-Preis (Preorder-Collect)
- Transaction #2: 5000x @ Kauf-Preis (neuer Kauf)
- **ODER:** 1× 10000x kombiniert @ gewichtetem Durchschnittspreis

### Test #2: Balance-Only Window-Close
**Szenario:**
- Kauf 5000x + neue Preorder 5000x setzen
- Warehouse-Delta = 0
- Detail-Window SOFORT schließen (<3s)

**Erwartung:**
- Transaction gespeichert trotz Window-Close
- tx_case = 'buy_collect_balance_only_forced'
- Menge geschätzt aus desired_price

### Test #3: Log-based Dedupe
**Szenario:**
- Detail-Window erfasst Kauf
- Log-based parsed gleichen Kauf mit leicht anderem Preis (OCR-Fehler)

**Erwartung:**
- Nur Detail-Window-Version gespeichert
- Log-based-Duplikat abgelehnt

---

## Nächste Schritte

### 1. Preise verifizieren 🔍
**Frage an User:** Welcher Preis war korrekt für Kauf #1?
- Detail-Window: 14,137,210
- Log-based: 13,981,680

Prüfe BDO-Screenshot oder Market-History!

### 2. Fix #1 implementieren ⚠️
Preorder-Collect Feature (`_detail_pending_collect_qty`)

### 3. Fix #2 implementieren ⚠️
Balance-Only Force bei Window-Close

### 4. Test wiederholen 🧪
Pig Blood Szenario nochmal mit Fixes

---

**Status:** Analyse complete, 3 Fixes identifiziert  
**Priorität:** CRITICAL (Preorder geht verloren)  
**Branch:** feature/detail-window-capture
