# RELIST FIX PLAN - 2025-10-21

## Problem-Zusammenfassung

Nach dem Relist-Test wurden folgende Probleme identifiziert:

### ❌ Was NICHT funktioniert hat:
1. **Auto-Collect Transaction** wurde NICHT gespeichert (400x @ 61,600,000)
2. **Alte Preorder** wurde NICHT als 'collected' markiert
3. **Neue Preorder** wurde erstellt (5000x @ 770M), aber ohne Auto-Collect-Detection
4. **Rapid-Scans** wurden NICHT ausgeführt (1.4s Delay statt 0.05s)
5. **Input-Field-Extraktion** wurde NIE aufgerufen

## Root Causes (geordnet nach Priorität)

### 1. CRITICAL: Rapid-Scans werden nicht ausgeführt ⭐⭐⭐

**Problem**: Nach Baseline-Capture (19:32:50.833) kommt der nächste Scan erst 1.4s später (19:32:52.280)

**Erwartung**: 3 Rapid-Scans @ 0.05s Intervallen = Scans bei t=0.05s, t=0.10s, t=0.15s

**Mögliche Ursache**: 
- `_capture_frame()` blockiert oder returned `None` im Detail-Window
- Focus-Check schlägt fehl (Window-Title ändert sich?)
- Anderer blocking Code

**Fix**:
```python
# In single_scan(): Add extensive logging
while self._request_immediate_rescan > 0 and self.running:
    if self.debug:
        log_debug(f"[RAPID-SCAN] Starting rapid scan #{4 - self._request_immediate_rescan}")
    time.sleep(0.05)
    img2 = self._capture_frame()
    if img2 is None:
        if self.debug:
            log_debug(f"[RAPID-SCAN] Capture failed (img=None)")
        break
    if not self.running:
        if self.debug:
            log_debug(f"[RAPID-SCAN] Stopped (running=False)")
        break
    self._process_image(img2, context='quick', allow_debug=False)
    self._request_immediate_rescan -= 1
    if self.debug:
        log_debug(f"[RAPID-SCAN] Completed, remaining={self._request_immediate_rescan}")
```

### 2. CRITICAL: Input-Field-Extraktion wird nie aufgerufen ⭐⭐⭐

**Problem**: `_extract_preorder_input_fields()` wird nur bei Balance-Delta aufgerufen, aber das Delta wurde nie erkannt

**Root Cause**: Rapid-Scans wurden nicht ausgeführt → Kein zweiter Scan → Kein Delta

**Primary Fix**: Extrahiere Input-Fields **SOFORT** bei Baseline-Capture!

```python
# In _monitor_detail_window(), nach Baseline-Capture:
if not self._detail_window_active:
    # ... existing baseline capture code ...
    
    # ✅ NEW: Extract input fields immediately (proaktiv!)
    if window_type == 'buy_item' and img is not None and proc_img is not None:
        if self.debug:
            log_debug(f"[DETAIL] Extracting preorder input fields from baseline frame...")
        
        input_fields = self._extract_preorder_input_fields(
            img=img,
            proc_img=proc_img,
            window_type=window_type
        )
        
        if input_fields:
            # Cache for later use
            self._detail_cached_input_fields = input_fields
            self._detail_cached_input_timestamp = now
            
            if self.debug:
                log_debug(
                    f"[DETAIL] ✅ Input fields cached: "
                    f"{input_fields['quantity']:,}x @ {input_fields['price']:,} "
                    f"(total: {input_fields['price'] * input_fields['quantity']:,})"
                )
        else:
            self._detail_cached_input_fields = None
            if self.debug:
                log_debug(f"[DETAIL] ⚠️ Input field extraction failed")
```

**Secondary Fix**: Nutze gecachte Fields bei Delta-Detection:

```python
# In _detect_preorder_placement():
# STRATEGY 1: Use cached input fields if available
if hasattr(self, '_detail_cached_input_fields') and self._detail_cached_input_fields:
    # Check if cache is still fresh (< 5 seconds old)
    if hasattr(self, '_detail_cached_input_timestamp'):
        age = (timestamp - self._detail_cached_input_timestamp).total_seconds()
        if age < 5.0:
            preorder_qty = self._detail_cached_input_fields['quantity']
            preorder_price = self._detail_cached_input_fields['price']
            extraction_method = "cached_input_fields"
            
            if self.debug:
                log_debug(
                    f"[PREORDER-DETECT] ✅ Using CACHED input fields: "
                    f"{preorder_qty:,}x @ {preorder_price:,} (age: {age:.1f}s)"
                )
```

### 3. HIGH: Relist-Pattern Detection fehlt ⭐⭐

**Problem**: System kann nicht zwischen "Neue Preorder" und "Relist mit Auto-Collect" unterscheiden

**Fix**: Erweiterte Relist-Detection mit gecachten Input-Fields:

```python
# In _monitor_detail_window(), bei Delta-Detection:
if balance_delta < 0 and warehouse_delta > 0:
    # RELIST PATTERN: Balance↓ (neue Preorder) + Warehouse↑ (Auto-Collect!)
    
    if self.debug:
        log_debug(
            f"[RELIST-DETECT] Pattern matched: "
            f"balance {balance_delta:+,}, warehouse {warehouse_delta:+}"
        )
    
    # 1. Save auto-collect transaction
    autocollect_qty = warehouse_delta
    autocollect_price = abs(balance_delta)  # Rough estimate
    
    # Try to find matching preorder for better price
    matching_preorder = self._preorder_manager.find_matching_preorder(
        item_name=self._detail_window_item,
        warehouse_delta=warehouse_delta,
        balance_delta=balance_delta,
        timestamp=now
    )
    
    if matching_preorder:
        autocollect_price = matching_preorder['price']
        if self.debug:
            log_debug(
                f"[RELIST] Found matching preorder: "
                f"ID={matching_preorder['id']}, price={autocollect_price:,}"
            )
    
    # Save auto-collect transaction
    self._save_transaction(
        item_name=self._detail_window_item,
        quantity=autocollect_qty,
        price=autocollect_price,
        transaction_type='buy',
        tx_case='buy_collect',
        timestamp=now
    )
    
    # Mark old preorder as collected
    if matching_preorder:
        self._preorder_manager.mark_collected(
            preorder_id=matching_preorder['id'],
            collected_at=now,
            tx_id=None  # Will be set by DB
        )
    
    # 2. Create new preorder from cached input fields
    if hasattr(self, '_detail_cached_input_fields') and self._detail_cached_input_fields:
        new_preorder_qty = self._detail_cached_input_fields['quantity']
        new_preorder_price = self._detail_cached_input_fields['price']
        
        self._preorder_manager.store_preorder(
            item_name=correct_item_name(self._detail_window_item),
            quantity=new_preorder_qty,
            price=new_preorder_price,
            timestamp=now
        )
        
        if self.debug:
            log_debug(
                f"[RELIST] ✅ New preorder created: "
                f"{new_preorder_qty:,}x @ {new_preorder_price:,}"
            )
```

### 4. MEDIUM: Transaction-Log Fallback ⭐

**Problem**: Wenn Detail-Window zu schnell schließt, gehen Transaktionen verloren

**Fix**: Scanne Overview-Log nach Detail-Window-Exit:

```python
# In _monitor_detail_window(), bei Window-Exit:
if wtype not in ("buy_item", "sell_item"):
    if self._detail_window_active:
        # Check for missed transactions in overview log
        if hasattr(self, '_detail_window_entry_item') and self._detail_window_entry_item:
            # Scan full_text for "Transaction of {item}"
            pattern = rf"Transaction\s+of\s+{re.escape(self._detail_window_entry_item)}\s+[xX]?(\d+)\s+.*?(\d[\d,]+)\s+Silver"
            match = re.search(pattern, full_text, re.IGNORECASE)
            
            if match:
                missed_qty = int(match.group(1))
                missed_price = normalize_numeric_str(match.group(2))
                
                if self.debug:
                    log_debug(
                        f"[DETAIL-FALLBACK] Found transaction in overview log: "
                        f"{self._detail_window_entry_item} x{missed_qty} @ {missed_price:,}"
                    )
                
                # Check if not already saved
                # ... save transaction ...
        
        # Reset state
        self._reset_detail_window_state()
```

## Implementation Order

### Phase 1: CRITICAL Fixes (Must-Have für Relist)

1. ✅ **Add extensive logging to single_scan()**
   - Log every step of rapid-scan execution
   - Identify why rapid-scans don't fire

2. ✅ **Fix rapid-scan execution**
   - Ensure `_capture_frame()` works in Detail-Window
   - Remove any blocking code
   - Verify focus-check doesn't interfere

3. ✅ **Implement proactive Input-Field extraction**
   - Extract at Baseline-Capture (first frame)
   - Cache results for Delta-Detection
   - Add fallback to ROI-extraction at Delta-Detection

### Phase 2: HIGH Priority (Relist-Specific)

4. ✅ **Implement Relist-Pattern Detection**
   - Detect balance↓ + warehouse↑ pattern
   - Save auto-collect transaction
   - Mark old preorder as collected
   - Create new preorder from cached fields

5. ✅ **Add better OCR for Input-Fields**
   - Test with real screenshots
   - Optimize patterns for "Desired Price"/"Desired Amount"
   - Handle OCR variations

### Phase 3: MEDIUM Priority (Robustness)

6. ⚠️ **Add Transaction-Log Fallback**
   - Scan overview log after Detail-Window exit
   - Catch missed transactions
   - Prevent data loss

7. ⚠️ **Add comprehensive testing**
   - Unit tests for Relist-Pattern
   - Integration tests with mock data
   - Live test protocol

## Testing Protocol

### Test 1: Rapid-Scan Execution
```python
# Enable debug logging
# Open Detail-Window
# Expected logs:
[DETAIL] ⚡ Baseline capture scheduled with IMMEDIATE rescan (3x rapid)
[RAPID-SCAN] Starting rapid scan #1
[RAPID-SCAN] Completed, remaining=2
[RAPID-SCAN] Starting rapid scan #2
[RAPID-SCAN] Completed, remaining=1
[RAPID-SCAN] Starting rapid scan #3
[RAPID-SCAN] Completed, remaining=0
```

### Test 2: Input-Field Extraction
```python
# Expected logs:
[DETAIL] Extracting preorder input fields from baseline frame...
[PREORDER-INPUT] OCR (X.Xms): Desired Price: 154,000 Desired Amount: 5000
[PREORDER-INPUT] ✅ SUCCESS: 5,000x @ 154,000 (total: 770,000,000)
[DETAIL] ✅ Input fields cached: 5,000x @ 154,000 (total: 770,000,000)
```

### Test 3: Relist Detection
```python
# Scenario: Relist preorder with 400x filled
# Expected outcome:
1. Auto-Collect Transaction: 400x @ 61,600,000
2. Old Preorder: status='collected'
3. New Preorder: 5000x @ 770,000,000 (from input fields)

# Expected logs:
[RELIST-DETECT] Pattern matched: balance -770000000, warehouse +400
[RELIST] Found matching preorder: ID=X, price=61600000
[RELIST] ✅ Auto-collect saved: 400x @ 61,600,000
[RELIST] ✅ Old preorder marked collected (ID=X)
[RELIST] ✅ New preorder created: 5,000x @ 770,000,000 (ID=Y)
```

## Success Criteria

✅ **Must-Have**:
- [ ] Rapid-scans execute within 0.05-0.08s intervals
- [ ] Input-Fields extracted at Baseline-Capture
- [ ] Relist-Pattern detected correctly
- [ ] Auto-Collect transaction saved
- [ ] Old preorder marked as collected
- [ ] New preorder created with correct values

✅ **Nice-to-Have**:
- [ ] Transaction-Log fallback works
- [ ] No false-positive relist detections
- [ ] Comprehensive error handling
- [ ] Performance impact < 50ms per scan

## Next Action

**START HERE**: Add logging to `single_scan()` and test rapid-scan execution!
