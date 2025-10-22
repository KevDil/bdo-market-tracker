# Pig Blood Test-Szenario: Root-Cause-Analyse & Fix-Plan

**Datum**: 2025-10-21  
**Test-Item**: Pig Blood  
**Szenario**: Preorder Auto-Collect + 2 Käufe + Neue Preorder  

---

## 🔍 Executive Summary

Der Pig Blood Test hat **4 kritische Fehler** offenbart:

1. ❌ **Alte Preorder (5000x @ 13,75M)** nicht als `collected` markiert
2. ❌ **Neue Preorder (5000x @ 14,45M)** nicht in Database gespeichert  
3. ❌ **Transaction #3** zeigt `15000x @ 45,95M` (merged 2 Käufe + 1 Preorder)
4. ❌ **Preorder Auto-Collect** nicht erkannt (Warehouse +10k statt +5k)

**Root Cause**: System hat **KEINE Preorder-Tracking-Logik** implementiert.

---

## 📊 Was wirklich passiert ist (Timeline)

### T=0: Ausgangszustand (vor Test)
```sql
-- Database State:
preorders: ID=1, Pig Blood 5000x @ 13,750,000, status='active', quantity_filled=0

-- Game State:
Warehouse: 0x Pig Blood
Balance: 193,283,209,550 Silver
Preorder 5000x: FULLY FILLED (bereit zum Collect)
```

### T=1: Detail-Window öffnen (18:01:10.043)
**User Action**: Click "Relist" auf Pig Blood Preorder

**OCR Detection**:
```
✅ BASELINE CAPTURED (single-sample, warehouse=None moment)
   Window: buy_item
   Item: Pig Blood 9,550
   Warehouse: 0
   Balance: 193,283,209,550
```

**System Status**: ✅ Perfekte Baseline erfasst!

---

### T=2: Erster Kauf + Auto-Collect (18:01:10.733)
**User Action**: Purchase 5000x @ 15,750,000 Silver

**Game Logic (unsichtbar für System)**:
```
1. Purchase: -15,750,000 Balance, +5,000 Warehouse
2. Auto-Collect Preorder: +5,000 Warehouse (kostenlos!)
→ Total: -15,750,000 Balance, +10,000 Warehouse
```

**OCR Detection**:
```
Balance: 193,283,209,550 → 193,267,459,550 (Δ -15,750,000)
Warehouse: 0 → 10,000 (Δ +10,000)
```

**Implied Price**: 15,750,000 / 10,000 = **1,575 Silver/item**

**Plausibilitätscheck**:
```python
base_price = 2,970  # BDO API
min_allowed = 2,970 * 0.85 = 2,524 Silver/item

if 1,575 < 2,524:
    ❌ PLAUSIBILITY FAIL!
    logger.debug("[DETAIL] Likely OCR error in balance - waiting for next scan...")
    return  # Transaction NICHT gespeichert!
```

**System Behavior**: ❌ **Wartet auf "korrekten" Balance-Wert** (der nie kommt)

**Expected Behavior**:
```python
# Sollte erkennen:
warehouse_surplus = 10,000 - 5,000 = +5,000
→ Auto-collected preorder detected!
→ Mark preorder ID=1 as collected
→ Save transaction: 10,000x @ 29,500,000 (15.75M + 13.75M)
```

---

### T=3: Zweiter Kauf (18:01:12.404)
**User Action**: Purchase 5000x @ 15,750,000 Silver

**OCR Detection**:
```
Balance: 193,283,209,550 → 193,251,709,550 (Δ -31,500,000)
Warehouse: 0 → 15,000 (Δ +15,000)
```

**Implied Price**: 31,500,000 / 15,000 = **2,100 Silver/item**

**Plausibilitätscheck**: ❌ **FAIL** (2,100 < 2,524)

**System Behavior**: ❌ Weiterhin wartend...

---

### T=4: Neue Preorder platzieren (18:01:14.801)
**User Action**: Place order 5000x @ 14,450,000 Silver

**OCR Detection**:
```
Balance: 193,283,209,550 → 193,237,259,550 (Δ -45,950,000)
Warehouse: 0 → 15,000 (Δ +15,000)
```

**Implied Price**: 45,950,000 / 15,000 = **3,063 Silver/item**

**Plausibilitätscheck**: ✅ **PASS** (3,063 > 2,524)

**System Behavior**:
```python
✅ Inferred transaction: buy 15000x Pig Blood @ 45,950,000 Silver (total)
DB SAVE: buy 15000x Pig Blood price=45950000 case=buy_collect_ui_inferred
🔄 Rolling baseline updated: Balance=193,237,259,550, Warehouse=15,000
```

**Problem**: 
- Balance-Delta -45,95M enthält:
  * Kauf #1: -15,75M
  * Kauf #2: -15,75M
  * **Neue Preorder**: -14,45M ← **als Kauf fehlinterpretiert!**
- Warehouse-Delta +15,000x enthält:
  * Kauf #1: +5,000x
  * **Auto-Collect**: +5,000x ← **nicht erkannt!**
  * Kauf #2: +5,000x

---

### T=5: Transaction-Log sichtbar (18:01:17.955)
**OCR Detection** (beim Window-Close zu buy_overview):
```
Transaction-Log Text:
"Placed order of Pig Blood x5,000 for 14,450,000 Silver 2025.10.21 18.01
 Purchased Pig Blood x5,000 for 15,750,000 Silver 2025.10.21 18.01
 Purchased Pig Blood x5,000 for 15,750,000 Silver 2025.10.21 18.01
 Transaction of Pig Blood x5,000 worth 13,750,000 Silver has been completed. 2025.10.21 18.01"
```

**Parsing**:
```python
Line 50: [CLUSTER] Building cluster for 'Pig Blood' @ 2025-10-21 18:01:00 (type=placed)
Line 55: skip placed-only entry for item='Pig Blood'  ← ❌ NEUE PREORDER ÜBERSPRUNGEN!
```

**Expected Behavior**:
```python
# Sollte speichern:
INSERT INTO preorders (item_name, quantity, price, timestamp, status)
VALUES ('Pig Blood', 5000, 14450000, '2025-10-21 18:01:00', 'active')
```

---

## 🐛 Root-Cause-Analyse

### **Bug #1: Plausibilitätscheck verhindert Auto-Collect-Detection**

**Location**: `tracker.py` (Detail-Window-Logik)

**Code**:
```python
implied_price_per_item = abs(balance_delta) / warehouse_delta
if implied_price_per_item < (base_price * 0.85):
    logger.debug(f"[DETAIL] Likely OCR error in balance - waiting for next scan...")
    return  # ❌ VERWIRFT gültige Auto-Collect-Daten!
```

**Problem**:
- Wenn Preorder @ 2,750 Silver/item + Kauf @ 3,150 Silver/item:
  → Durchschnitt: **2,950 Silver/item** (könnte unter 85% Threshold liegen!)
- Auto-Collect verursacht **Warehouse-Surplus** (10k statt 5k)
  → Implizierter Preis sinkt unter Minimum
  → System verwirft Daten als "OCR-Fehler"

**Impact**: ❌ Preorder Auto-Collect wird NIEMALS erkannt!

---

### **Bug #2: Preorder-Platzierung wird im Detail-Window NICHT erkannt**

**Location**: `tracker.py` → `_detect_preorder_placement()`

**Problem**:
- Preorder-Detection erfordert `balance_delta < 0` UND `warehouse_delta == 0`
- ABER: Im Pig Blood Fall passierte:
  1. Kauf #1 + Auto-Collect → Balance -15.75M, Warehouse +10k
  2. Plausibilitätscheck REJECTED → System wartet
  3. Kauf #2 → Balance -31.5M kumuliert, Warehouse +15k
  4. Neue Preorder → Balance -45.95M kumuliert, Warehouse BLEIBT +15k
  5. Plausibilitätscheck ACCEPTED → Transaction gespeichert
- **Die neue Preorder-Platzierung passierte NACH den Käufen**, aber der Balance-Delta war BEREITS kumuliert!
- Detection-Methode sieht: `balance_delta = -45.95M`, `warehouse_delta = +15k` → **KEIN** Match für Preorder-Pattern!

**Expected Pattern**:
```python
if balance_delta < 0 and warehouse_delta == 0:  # Preorder-Muster
    # Aber tatsächlich: balance_delta = -45.95M, warehouse_delta = +15k
    # → Pattern-Match FAILED!
```

**Impact**: ❌ Preorders werden nur erkannt wenn sie ISOLIERT platziert werden (keine vorherigen Käufe in derselben Detail-Window-Session)!

---

**NOTE zu "placed-only" Einträgen:**
Diese Einträge **SOLLEN** übersprungen werden! Die Preorder-Erfassung erfolgt durch `_detect_preorder_placement()` im Detail-Window (via UI-Metriken), NICHT durch Transaction-Log-Parsing. Das Log-Parsing ist nur für **OVERVIEW-Fenster** relevant (collect/relist Fälle).

---

### **Bug #3: Balance-Delta wird nicht zwischen Käufen und Preorders getrennt**

**Location**: `tracker.py` (Detail-Window-Logik)

**Code**:
```python
# Balance-Delta von -45,95M wird NICHT aufgeteilt in:
# - Käufe: -31,5M (2x 15,75M)
# - Neue Preorder: -14,45M

# Stattdessen: Alles als "15000x Kauf" behandelt
total_spent = abs(balance_delta)  # -45,950,000
warehouse_delta = 15000
→ Speichert: 15000x @ 45,950,000 (FALSCH!)
```

**Problem**:
- Preorder-Platzierung kostet Balance (wird reserviert), erhöht aber NICHT Warehouse
- System hat keine Logik, um Preorder-Balance-Deltas zu separieren

**Impact**: ❌ Preorder-Kosten werden als Käufe fehlinterpretiert!

---

### **Bug #4: Alte Preorder wird nicht als "collected" markiert**

**Location**: Fehlende Implementierung

**Current Database State**:
```sql
SELECT * FROM preorders WHERE id=1;
-- Result:
-- id=1, item_name='Pig Blood', quantity=5000, price=13750000,
-- status='active', quantity_filled=0, collected_at=NULL
```

**Problem**:
- Keine Detection-Logik für Auto-Collect
- Keine UPDATE-Logik, um Preorder als `collected` zu markieren
- Keine Verknüpfung zwischen Preorder und Transaction

**Impact**: ❌ Alte Preorders bleiben ewig `active`, werden nie als `collected` markiert!

---

## 🛠️ Fix-Plan: "Rolling Baseline + Preorder Detection"

### **Strategie**: Preorder-Detection NACH jeder Transaction

Statt zu warten bis Detail-Window schließt und GESAMTEN Balance-Delta zu akkumulieren, sollte das System:

1. **Nach JEDER erkannten Transaction**: Rolling Baseline updaten
2. **Zwischen Transactions**: Prüfen ob neuer Balance-Delta ohne Warehouse-Delta existiert → Preorder!
3. **Auto-Collect Detection**: Warehouse-Surplus erkennen und alte Preorder markieren

---

### **Phase 1: Rolling Baseline für Multiple Transactions** (2-3h)

**Problem**: Aktuell wird Baseline NUR am Window-Eintritt gesetzt und bleibt fix bis Window-Close.

**Lösung**: Nach jeder gespeicherten Transaction → Update Baseline auf neue Werte.

**Implementation**:

```python
# File: tracker.py (in _monitor_detail_window(), AFTER transaction saved)

# EXISTING CODE:
tx_result = self._process_detail_window_delta(...)
if tx_result:
    # Transaction wurde gespeichert
    
    # NEW: Update rolling baseline
    self._detail_baseline_balance = current_balance
    self._detail_baseline_warehouse = current_warehouse
    self._detail_last_metrics = current_metrics.copy()
    
    # Reset delta accumulators
    self._detail_partial_balance_delta = 0
    self._detail_partial_warehouse_delta = 0
    self._detail_balance_changed_once = False
    self._detail_warehouse_changed_once = False
    
    if self.debug:
        log_debug(
            f"[DETAIL] 🔄 Rolling baseline updated: "
            f"Balance={current_balance:,}, Warehouse={current_warehouse}"
        )
```

**Test**: Nach Kauf #1 sollte Baseline auf `(Balance=193.267M, Warehouse=10k)` gesetzt werden.

---

### **Phase 2: Preorder-Detection NACH Transaction** (2h)

**Problem**: Preorder-Detection läuft NUR bei `warehouse_delta == 0`, aber nach einem Kauf ist `warehouse_delta > 0`!

**Lösung**: Nach jeder Transaction → Prüfe ob neuer Balance-Delta existiert (ohne Warehouse-Änderung).

**Implementation**:

```python
# File: tracker.py (in _monitor_detail_window())

# AFTER transaction saved AND baseline updated:
if tx_result:
    # ... baseline update (see Phase 1) ...
    
    # NEW: Check for subsequent preorder placement
    # Wait 1-2 scans, then check if balance decreased again without warehouse change
    self._detail_await_preorder_check = True
    self._detail_preorder_check_baseline = {
        'balance': current_balance,
        'warehouse': current_warehouse,
        'timestamp': datetime.datetime.now()
    }

# LATER (in next scan):
if self._detail_await_preorder_check:
    check_baseline = self._detail_preorder_check_baseline
    time_since_baseline = (datetime.datetime.now() - check_baseline['timestamp']).total_seconds()
    
    # Wait at least 0.5s for UI to settle
    if time_since_baseline < 0.5:
        return
    
    # Check if balance decreased without warehouse change
    balance_delta_new = current_balance - check_baseline['balance']
    warehouse_delta_new = current_warehouse - check_baseline['warehouse']
    
    if balance_delta_new < 0 and warehouse_delta_new == 0:
        # Preorder detected!
        preorder_detected = self._detect_preorder_placement(
            item_name=self._detail_window_item,
            balance_delta=balance_delta_new,
            current_metrics=current_metrics,
            timestamp=datetime.datetime.now()
        )
        
        if preorder_detected:
            # Reset preorder check
            self._detail_await_preorder_check = False
            
            # Update baseline AGAIN
            self._detail_baseline_balance = current_balance
            self._detail_last_metrics = current_metrics.copy()
```

**Test**: Nach Kauf #2 sollte neue Preorder (balance -14.45M, warehouse +0) erkannt werden.

---

### **Phase 3: Auto-Collect Detection + Plausibilitätscheck-Fix** (3-4h)

**Problem**: 
1. Warehouse-Surplus (10k statt 5k) wird als "zu billiger Preis" rejected
2. Alte Preorder wird nicht als `collected` markiert
3. Transaction-Preis fehlt Preorder-Anteil (13,75M)

**Lösung**: Warehouse-Surplus-Check VOR Plausibilitätscheck + Preorder-Korrektur.

**Implementation**:

#### **Step 3.1: PreorderManager Integration**

```python
# File: preorder_manager.py (NEW FILE)

class PreorderManager:
    def __init__(self, db_conn):
        self.db = db_conn
        self.cache = {}  # {item_name: [preorder_objects]}
        self.cache_timestamp = None
        self.cache_ttl = 60  # seconds
    
    def find_matching_preorder(self, item_name, max_qty):
        """Find oldest active preorder that could be auto-collected."""
        query = """
            SELECT * FROM preorders 
            WHERE item_name = ? AND status = 'active'
            ORDER BY timestamp ASC
            LIMIT 1
        """
        result = self.db.execute(query, (item_name,)).fetchone()
        
        if result:
            return {
                'id': result[0],
                'item_name': result[1],
                'quantity': result[2],
                'price': result[4],
                'timestamp': result[5]
            }
        return None
    
    def mark_collected(self, preorder_id, tx_id, collected_at):
        """Mark preorder as collected and link to transaction."""
        query = """
            UPDATE preorders 
            SET status = 'collected',
                collected_at = ?,
                collected_tx_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """
        self.db.execute(query, (collected_at, tx_id, preorder_id))
        self.db.commit()
        
        # Clear cache
        self.cache_timestamp = None
    
    def store_preorder(self, item_name, quantity, price, timestamp):
        """Store new preorder and auto-collect old one if exists."""
        # Check for existing active preorder
        old_preorder = self.find_matching_preorder(item_name, quantity)
        
        if old_preorder:
            # Auto-collect old preorder (no transaction, just mark as collected)
            log_debug(
                f"[PREORDER] Auto-collecting old preorder ID={old_preorder['id']} "
                f"before placing new one"
            )
            self.mark_collected(
                old_preorder['id'],
                tx_id=None,  # No transaction for this collection
                collected_at=timestamp
            )
        
        # Insert new preorder
        query = """
            INSERT INTO preorders (
                item_name, quantity, quantity_filled, price, 
                timestamp, status, created_at, updated_at
            )
            VALUES (?, ?, 0, ?, ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """
        cursor = self.db.execute(query, (item_name, quantity, price, timestamp))
        self.db.commit()
        
        # Clear cache
        self.cache_timestamp = None
        
        return cursor.lastrowid
```

#### **Step 3.2: Auto-Collect Detection in Detail-Window**

```python
# File: tracker.py (in __init__)

from preorder_manager import PreorderManager

self._preorder_manager = PreorderManager(get_connection())

# ---

# File: tracker.py (in _monitor_detail_window(), BEFORE plausibility check)

# Calculate expected purchase quantity from balance delta
expected_qty = self._calculate_expected_qty(
    balance_delta=abs(balance_delta),
    item_name=self._detail_window_item
)

warehouse_surplus = warehouse_delta - expected_qty

# Check for preorder auto-collect
preorder_correction = None
if warehouse_surplus > 0:
    preorder = self._preorder_manager.find_matching_preorder(
        item_name=self._detail_window_item,
        max_qty=warehouse_surplus
    )
    
    if preorder and preorder['quantity'] == warehouse_surplus:
        if self.debug:
            log_debug(
                f"[PREORDER] Auto-collect detected: {warehouse_surplus}x "
                f"@ {preorder['price']:,.0f} Silver (ID={preorder['id']})"
            )
        
        # Will be used to adjust transaction price later
        preorder_correction = {
            'id': preorder['id'],
            'quantity': preorder['quantity'],
            'price': preorder['price']
        }
        
        # Adjust expected_qty for plausibility check
        expected_qty += warehouse_surplus

# NOW run plausibility check with ADJUSTED expected_qty
implied_price_per_item = abs(balance_delta) / expected_qty  # NOT warehouse_delta!

base_price = self._get_base_price(self._detail_window_item)
if base_price is not None:
    min_price = base_price * 0.85
    
    if implied_price_per_item < min_price:
        # STILL too low? Then it's OCR error
        if self.debug:
            log_debug(
                f"[DETAIL] ⚠️ PLAUSIBILITY FAIL even after preorder correction: "
                f"Implied price {implied_price_per_item:,.0f} < {min_price:,.0f} Silver/item"
            )
        return

# PASS plausibility → Save transaction
tx_result = self._process_detail_window_delta(
    window_type=window_type,
    balance_delta=balance_delta,
    warehouse_delta=warehouse_delta,
    current_metrics=current_metrics,
    last_metrics=self._detail_last_metrics,
    preorder_correction=preorder_correction  # Pass to transaction builder
)

if tx_result and preorder_correction:
    # Mark preorder as collected
    self._preorder_manager.mark_collected(
        preorder_id=preorder_correction['id'],
        tx_id=tx_result['id'],
        collected_at=tx_result['timestamp']
    )
```

#### **Step 3.3: Calculate Expected Quantity Helper**

```python
# File: tracker.py

def _calculate_expected_qty(self, balance_delta: float, item_name: str) -> int:
    """
    Calculate expected purchase quantity from balance delta.
    Uses base price to estimate quantity.
    
    Returns:
        Expected quantity (0 if cannot determine)
    """
    if balance_delta <= 0:
        return 0
    
    base_price = self._get_base_price(item_name)
    if base_price is None:
        return 0
    
    # Use middle of price range (92.5% of base price)
    estimated_unit_price = base_price * 0.925
    
    # Calculate quantity
    estimated_qty = balance_delta / estimated_unit_price
    
    # Round to nearest 1000 (most purchases are in 1k increments)
    estimated_qty_rounded = round(estimated_qty / 1000) * 1000
    
    # If < 1000, round to nearest 100
    if estimated_qty_rounded < 1000:
        estimated_qty_rounded = round(estimated_qty / 100) * 100
    
    # If < 100, use raw value
    if estimated_qty_rounded < 100:
        estimated_qty_rounded = int(estimated_qty)
    
    return max(1, estimated_qty_rounded)
```

**Test**: 
- First scan (warehouse +10k, balance -15.75M) should detect:
  * Expected qty: ~5000 (15.75M / 2970 = 5303 → rounded to 5000)
  * Warehouse surplus: 10000 - 5000 = +5000
  * Preorder found: 5000x @ 13.75M
  * Adjusted price: 15.75M + 13.75M = 29.5M
  * Plausibility: 29.5M / 10k = 2,950 Silver/item ✅ PASS

---

### **Phase 4: Testing & Validation** (2h)

#### **Test Case 1: Simple Auto-Collect**
```
Initial: 1 active preorder (5000x @ 13.75M)
Action: Buy 5000x @ 15.75M
Expected:
  - Preorder marked 'collected'
  - Transaction: 10000x @ 29.5M
  - Warehouse: +10,000
```

#### **Test Case 2: Auto-Collect + New Preorder**
```
Initial: 1 active preorder (5000x @ 13.75M)
Actions:
  1. Buy 5000x @ 15.75M (auto-collect preorder)
  2. Buy 5000x @ 15.75M
  3. Place preorder 5000x @ 14.45M
Expected:
  - Old preorder marked 'collected'
  - Transaction #1: 10000x @ 29.5M
  - Transaction #2: 5000x @ 15.75M
  - New preorder: 5000x @ 14.45M (active)
```

#### **Test Case 3: Pig Blood Replay**
```
Repeat exact user scenario from 2025-10-21 18:01
Expected database state:
  1. preorders: 2 entries
     - ID=1: Pig Blood 5000x @ 13.75M, status='collected', collected_at='2025-10-21 18:01:10'
     - ID=2: Pig Blood 5000x @ 14.45M, status='active'
  2. transactions: 2 entries (NOT 1!)
     - ID=X: 10000x @ 29,500,000 (buy #1 + auto-collect)
     - ID=Y: 5000x @ 15,750,000 (buy #2)
```

---

## 📊 Expected Outcomes

### **After Phase 0** (Quick-Fix):
- ✅ Neue Preorders erscheinen in Database
- ❌ Alte Preorders noch nicht als `collected` markiert
- ❌ Transactions noch falsch (merged)

### **After Phase 1** (Auto-Collect):
- ✅ Alte Preorders werden als `collected` markiert
- ✅ Transaction-Preise korrekt (inkludieren Preorder-Auto-Collect)
- ❌ Neue Preorder-Kosten noch in Transaction-Total inkludiert

### **After Phase 2** (Plausibility):
- ✅ Auto-Collect wird sofort erkannt (nicht erst nach Timeout)
- ✅ Keine false-positives durch OCR-Fehler-Detection

### **After Phase 3** (Balance-Separation):
- ✅ Transaction-Quantities korrekt (nicht mehr merged)
- ✅ Neue Preorders nicht in Transaction-Total inkludiert
- ✅ **VOLLSTÄNDIGE LÖSUNG für alle Szenarien!**

---

## 🎯 Implementation Priority

**Week 1**: Phase 0 + Phase 1 (Auto-Collect Detection)
- Kritischster Bug: Alte Preorders nicht collected
- Größter Impact: Korrekte Preis-Berechnung

**Week 2**: Phase 2 (Plausibility) + Phase 3 (Balance-Separation)
- Performance-Improvement: Sofortige Detection
- Data Integrity: Saubere Transaction-Separation

**Week 3**: Phase 4 (Testing) + Regression Tests
- Alle 9 Test Cases aus Implementation Plan
- Edge Cases validieren

---

## 📝 Lessons Learned

1. **OCR ist nicht die Quelle aller Wahrheit**
   - Transaction-Log hat alle Details (placed/purchased/collected)
   - Detail-Window zeigt nur Aggregat-Werte

2. **Plausibilitätschecks können zu strikt sein**
   - Auto-Collect verursacht "unmögliche" Preis-Deltas
   - Warehouse-Surplus ist der Schlüssel zur Detection

3. **Balance-Deltas sind mehrdeutig**
   - Preorder-Platzierung kostet Balance (aber kein Purchase!)
   - Auto-Collect kostet KEINE Balance (aber erhöht Warehouse!)

4. **Real-World-Tests sind unverzichtbar**
   - 100-Seiten-Plan kann nicht alle Edge Cases antizipieren
   - Pig Blood Test hat 4 kritische Bugs offenbart

---

## 🔗 References

- **Implementation Plan**: `PREORDER_TRACKING_IMPLEMENTATION_PLAN.md` (v2.0 Final)
- **Database Schema**: `preorders` table (see `database.py`)
- **OCR Logs**: `ocr_log.txt` (2025-10-21 18:01:07 - 18:01:17)
- **Test Database**: `bdo_tracker.db` (snapshot from 2025-10-21 18:02)

---

**Next Step**: Implement Phase 0 (Quick-Fix) and test mit neuem Pig Blood scenario.
