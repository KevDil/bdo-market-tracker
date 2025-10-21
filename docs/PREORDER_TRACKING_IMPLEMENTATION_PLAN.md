# Preorder-Tracking Feature: Detailed Implementation Plan

**Document Version**: 2.0 Final + UI  
**Date**: 2025-01-21  
**Status**: Planning Phase  
**Last Updated**: 2025-01-21 (UI Management added)

## 🔴 CRITICAL UPDATES (v2.0 Final + UI)

### Game Behavior Clarifications
1. **ONE Active Preorder Per Item**: Database enforces unique constraint
2. **Preorder Replacement**: Setting new preorder auto-collects old one
3. **No Expiration**: Preorders remain active indefinitely
4. **Cancellation via Log**: "Withdrew order" always visible in transaction log
5. **Two Entry Points**: Relist button → can purchase OR set new preorder OR both
6. **Partial Preorder Fills**: Preorder can be partially filled (e.g., 3k of 5k ordered)
7. **Auto-Preorder on Shortage**: Last purchase auto-creates preorder if insufficient stock

### Architecture Changes
- Database unique index: `idx_preorders_one_active_per_item`
- `store_preorder()`: Auto-collects old preorder before inserting new
- `find_matching_preorder()`: No time tolerance (simplified)
- `cancel_preorder()`: Match by item + quantity + price
- **NEW**: Track `quantity_filled` for partial fills
- **NEW**: Detect auto-preorder creation when purchase fails due to low stock
- **NEW**: Preorder Management UI (Add/Edit/Delete/Mark Collected)
- Removed: `expire_old_preorders()`, `mark_expired()`

### Time Estimate Update (v2.0 Final + UI)
- Original: 12-16 hours
- After simplifications: 11-15 hours
- With partial fills + auto-preorder: 12-17 hours
- **Current (+ UI Management): 15-21 hours**
- **Recommended MVP (with UI): 10-14 hours**

### Added Complexity (v2.0 Final + UI)
- **Partial Preorder Fills**: Track `quantity_filled`, calculate proportional price contribution
- **Auto-Preorder Creation**: Detect insufficient stock, split transaction into purchase + new preorder
- **Preorder Management UI**: Manual Add/Edit/Delete/Collect for offline gaps and corrections
- **Enhanced Test Coverage**: 3 additional test cases (partial fill, auto-preorder, partial + replacement)
- **Enhanced Test Coverage**: 3 additional test cases (partial fill, auto-preorder, partial + replacement)

---

## 1. Executive Summary

### Problem Statement
When a user sets a **preorder** (buy order placed in advance):
1. **Balance is IMMEDIATELY reduced** by the preorder price (payment happens NOW)
2. **Warehouse remains unchanged** (items not collected yet)
3. Preorder sits in market waiting to be filled

When the preorder is **filled** and user opens Detail-Window to make additional purchases:
1. First purchase **auto-collects the preorder** (without user action)
2. **Balance reduces by ONLY the purchase price** (preorder already paid!)
3. **Warehouse increases by purchase quantity + preorder quantity**

**Current Behavior (BUG)**:
- Detail-window calculates: `implied_price = balance_delta / warehouse_delta`
- This gives: `implied_price = purchase_price / (purchase_qty + preorder_qty)`
- Result: **WRONG price** - missing the preorder price component

**Example (Birch Sap Test)**:
```
Before test: User sets preorder 5000x @ 58M
   Balance: X → X - 58M (paid now)
   Warehouse: 0 (not collected yet)

In Detail-Window:
   Baseline: Balance = 158,959,294,080, Warehouse = 0
   
   Purchase #1: 5000x @ 62,250,900
   → Balance: 158,959,294,080 → 158,897,043,180 (Δ -62,250,900) ← Only purchase!
   → Warehouse: 0 → 10,000 (Δ +10,000) ← Purchase + Preorder!
   
   Current calculation:
   implied_price = 62,250,900 / 10,000 = 6,225 Silver/item
   
   Correct total: 62,250,900 + 58,000,000 = 120,250,900 Silver
   Correct price: 120,250,900 / 10,000 = 12,025 Silver/item
```

### Solution Overview
Implement **Preorder-Tracking System** that:
1. **Captures preorder details** when user places order 
2. **Stores preorder data** persistently (survives app restart)
3. **Detects auto-collect scenario** in detail-window (warehouse_delta > expected from balance_delta)
4. **Matches and applies preorder price** to correct the transaction total
5. **Marks preorder as collected** to prevent double-counting

---

## 2. Requirements Analysis

### 2.1 Functional Requirements

#### FR-1: Preorder Detection
- **MUST** detect preorder placement **in Detail-Window** (balance↓, warehouse unchanged)
- **MUST** extract: item_name, quantity, price from detail-window metrics
- **MUST NOT** break existing delta-inference logic for regular purchases/sells
- **SHOULD** also detect "Placed order" events in transaction log (fallback/validation)

#### FR-2: Preorder Storage
- **MUST** store preorder data persistently (database table)
- **MUST** enforce ONE active preorder per item (replace on new placement)
- **MUST** track status: active, collected, cancelled (NO expiration!)

#### FR-3: Auto-Collect Detection
- **MUST** detect when warehouse_delta exceeds balance_delta expectation
- **MUST** match against stored preorders by item_name
- **MUST** verify quantity alignment (warehouse_delta = purchase_qty + preorder_qty)

#### FR-4: Price Correction
- **MUST** add preorder price to calculated transaction total
- **MUST** recalculate correct per-item price
- **MUST** apply plausibility check AFTER correction
- **MUST** mark preorder as collected after successful save
- **MUST** handle "auto-collect on new preorder placement" (old preorder collected when new one placed)
- **MUST** handle partial preorder fills (update quantity_filled, collect remaining on replacement)

#### FR-5: Preorder Replacement (New Preorder on Same Item)
- **MUST** detect when new preorder is placed while old one still active
- **MUST** auto-collect old preorder INCLUDING any partially filled quantity
- **MUST** replace old preorder with new one (only ONE active per item)

#### FR-6: Partial Preorder Fill Detection
- **MUST** detect when warehouse increase includes partial preorder fill
- **MUST** calculate: `filled_qty = warehouse_delta - purchase_qty`
- **MUST** update `quantity_filled` in preorder record
- **MUST** collect entire preorder (including partial) when replaced or fully filled

#### FR-7: Auto-Preorder Creation Detection
- **MUST** detect when last purchase creates automatic preorder (insufficient stock)
- **MUST** identify by: warehouse_delta < expected_from_balance (partial purchase)
- **MUST** calculate remaining quantity that became preorder
- **MUST** store new preorder automatically

#### FR-8: Preorder Cancellation
- **MUST** detect "Withdrew order" events in transaction log
- **MUST** mark preorder as cancelled (status='cancelled')
- **MUST** extract item_name, quantity, price from withdraw log entry
- **MUST** match against active preorder by item + quantity + price

#### FR-9: No Expiration
- **MUST NOT** expire preorders automatically (they remain active indefinitely)
- Only ways to deactivate: collected or cancelled

### 2.2 Non-Functional Requirements

#### NFR-1: Performance
- Preorder lookup MUST NOT slow down scan loop (< 5ms per lookup)
- Use in-memory cache for active preorders
- Lazy-load from database only when needed

#### NFR-2: Reliability
- MUST survive application restarts (persistent storage)
- MUST handle database errors gracefully
- MUST NOT lose preorder data on unexpected shutdown

#### NFR-3: Maintainability
- Clear separation of concerns (dedicated preorder module)
- Comprehensive logging for debugging
- Unit tests for all core logic

#### NFR-4: Backward Compatibility
- MUST NOT break existing transaction tracking
- MUST NOT affect detail-window logic for non-preorder cases
- Database migration MUST be reversible

---

## 3. System Architecture

### 3.1 Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     MarketTracker                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Transaction Log Parsing                      │  │
│  │  (process_ocr_text → extract_details_from_entry)   │  │
│  └────────────┬─────────────────────────────────────────┘  │
│               │                                             │
│               ▼                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Preorder Detection                           │  │
│  │  - Detect "Placed order" events                     │  │
│  │  - Extract preorder details                         │  │
│  └────────────┬─────────────────────────────────────────┘  │
│               │                                             │
│               ▼                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Preorder Manager (NEW)                       │  │
│  │  - Store/retrieve preorder data                     │  │
│  │  - Match preorders to auto-collect events           │  │
│  │  - Mark preorders as collected                      │  │
│  └────────────┬─────────────────────────────────────────┘  │
│               │                                             │
│               ▼                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Detail-Window Monitoring                     │  │
│  │  - Detect auto-collect scenario                     │  │
│  │  - Query PreorderManager for matching preorder      │  │
│  │  - Apply price correction                           │  │
│  └────────────┬─────────────────────────────────────────┘  │
│               │                                             │
│               ▼                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         Transaction Storage                          │  │
│  │  - Save corrected transaction to database           │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                Database Layer (database.py)                  │
│                                                             │
│  ┌────────────────┐        ┌──────────────────────────┐    │
│  │  transactions  │        │  preorders (NEW)         │    │
│  ├────────────────┤        ├──────────────────────────┤    │
│  │ id             │        │ id                       │    │
│  │ item_name      │        │ item_name                │    │
│  │ quantity       │        │ quantity                 │    │
│  │ price          │        │ price                    │    │
│  │ tx_type        │        │ timestamp                │    │
│  │ timestamp      │        │ status                   │    │
│  │ tx_case        │        │ collected_at             │    │
│  │ occurrence_idx │        │ collected_tx_id          │    │
│  │ content_hash   │        │ created_at               │    │
│  └────────────────┘        └──────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 Data Flow

#### Scenario 1: User Places Preorder (Detail-Window Detection - PRIMARY)
```
1. User opens Detail-Window (buy_item) for Birch Sap
2. Baseline captured: balance=158959294080, warehouse=0
3. User sets preorder: 5000x @ 58,000,000
4. Game updates: balance=158901294080 (Δ -58M), warehouse=0 (Δ 0)
5. _monitor_detail_window() detects: balance changed, warehouse UNCHANGED
6. NEW: _detect_preorder_placement() called
   - Condition: balance_delta < 0 AND warehouse_delta == 0
   - Calculate: price = abs(balance_delta) = 58M
   - Extract quantity from UI metrics (Orders field)
   - CHECK: Is there already an active preorder for this item?
     - YES: Mark old preorder as 'collected' (auto-collected on replacement)
     - NO: Continue normally
7. PreorderManager.store_preorder() saves NEW preorder
8. Rolling baseline updated (critical for next purchase!)
9. Delta state reset for next transaction
```

#### Scenario 1b: Preorder Cancelled (Transaction Log Detection)
```
1. User cancels preorder in game (Cancel button)
2. Transaction log shows:
   "2025.10.21 16.07 Withdrew order of Birch Sap x5,000 for 58,000,000 Silver"
3. process_ocr_text() parses log entry (type='withdrew')
4. NEW: _handle_preorder_cancellation() called
5. PreorderManager.cancel_preorder() finds matching active preorder
6. Update status to 'cancelled'
```

#### Scenario 2: Partial Preorder Fill + Purchase
```
1. User has active preorder: Birch Sap 5000x @ 58M, quantity_filled=0
2. Market fills 3000x (partial) → quantity_filled=3000
3. User opens detail-window, purchases 2000x @ 62M
4. Game auto-collects partial preorder (3000x)
5. Metrics: balance_delta=-62M, warehouse_delta=+5000 (2k purchase + 3k preorder)
6. _check_for_preorder_autocollect():
   - Preorder matched: 5000x @ 58M, filled=3000
   - Calculate filled_in_this_tx = 3000 (from preorder)
   - Price correction: 62M + (58M × 3000/5000) = 96.8M
7. Transaction saved: 5000x @ 96.8M
8. Update preorder: status='collected'
```

#### Scenario 3: Auto-Preorder Creation (Insufficient Stock)
```
1. User tries to buy 5000x Pine Sap @ 40M
2. Only 2000x available → Game buys 2k, auto-creates preorder for 3k
3. Metrics: balance_delta=-40M (FULL), warehouse_delta=+2000 (PARTIAL)
4. _detect_auto_preorder_creation():
   - Expected: 40M / base_price ≈ 5000x
   - Received: only 2000x
   - Auto-preorder: 3000x @ 24M (3/5 of price)
5. Store purchase (2000x @ 16M) + preorder (3000x @ 24M)
```

#### Scenario 4: Partial Fill + New Preorder (Replacement)
```
1. Active: Maple Sap 5000x @ 50M, filled=2000
2. User sets NEW preorder: 8000x @ 55M
3. Old preorder auto-collected (including 2000 filled)
4. New preorder stored: 8000x @ 55M
```

#### Scenario 5: Partial Fill + Auto-Preorder on Shortage (EDGE CASE)
```
CRITICAL SCENARIO: Combines two complex features!

1. Active preorder: Pine Sap 5000x @ 50M, filled=3000 (partially filled)
2. User tries to buy 4000x @ 40M
3. Only 2000x available in market
4. Game actions:
   a) Auto-collects 3000x from existing preorder
   b) Buys 2000x from market
   c) Auto-creates NEW preorder for remaining 2000x (4000 attempted - 2000 received)
   
5. Metrics after transaction:
   - balance_delta = -40M (purchase price only, preorder already paid)
   - warehouse_delta = +5000 (3k preorder + 2k purchase)
   
6. Detection logic (_monitor_detail_window):
   a) First check: Is there a matching preorder?
      → YES: Pine Sap 5000x, filled=3000
      → Warehouse surplus: 5000 - (40M/base_price) ≈ 5000 - 4000 = 1000
      → Wait, that doesn't match filled=3000!
      
   b) CORRECT detection:
      - Expected purchase from balance: 40M / base_price ≈ 4000x
      - Received in warehouse: 5000x
      - Surplus: 5000 - 4000 = 1000x (WRONG - this doesn't match preorder!)
      
   c) PROPER logic chain:
      Step 1: Check for preorder auto-collect
        → find_matching_preorder('Pine Sap', warehouse_delta=5000)
        → Match found: qty=5000, filled=3000
        → Preorder contributed: 3000x
        
      Step 2: Calculate purchase from balance
        → balance_delta = 40M
        → Implied purchase qty: 40M / base_price = 4000x
        
      Step 3: Reconcile warehouse_delta
        → warehouse_delta = 5000
        → preorder_contribution = 3000
        → actual_purchase = 5000 - 3000 = 2000
        
      Step 4: Detect shortage (auto-preorder)
        → intended_purchase = 4000 (from balance)
        → actual_purchase = 2000 (from warehouse reconciliation)
        → shortage = 4000 - 2000 = 2000x
        → Auto-preorder created: 2000x @ 20M (40M × 2000/4000)
        
7. Price correction calculation:
   - Preorder contribution: 50M × (3000/5000) = 30M
   - Purchase price: 40M × (2000/4000) = 20M
   - Total transaction: 30M + 20M = 50M for 5000x
   
8. Database operations:
   - Mark old preorder as collected (Pine Sap 5000x @ 50M, filled=3000)
   - Store transaction: 5000x @ 50M (corrected total)
   - Store NEW preorder: Pine Sap 2000x @ 20M (status=active)
   
9. Final state:
   - Transaction: Pine Sap 5000x @ 50M (collected 3k preorder + purchased 2k)
   - New Preorder: Pine Sap 2000x @ 20M (active, unfilled)

COMPLEXITY WARNING:
This scenario requires BOTH preorder auto-collect AND auto-preorder detection
in the SAME transaction. The detection order is critical:
  1. Check preorder auto-collect FIRST
  2. Subtract preorder qty from warehouse_delta
  3. THEN check if remaining purchase matches balance_delta
  4. If mismatch → auto-preorder created
```
5. PreorderManager.cancel_preorder() finds matching active preorder
   - Match by: item_name + quantity + price
6. Update status to 'cancelled'
7. Log cancellation event
```

#### Scenario 2: Preorder Auto-Collected in Detail-Window
```
1. User opens Detail-Window (buy_item) for Birch Sap
2. Baseline captured: balance=158959294080, warehouse=0
3. User purchases 5000x @ 62,250,900
4. Auto-collect triggers (preorder collected silently)
5. New metrics: balance=158897043180, warehouse=10000
6. Deltas: balance_delta=-62250900, warehouse_delta=+10000
7. _monitor_detail_window() calculates implied_price=6225 (WRONG)
8. NEW: _check_for_preorder_autocollect() called
   - Detects warehouse_delta (10000) > expected (5000)
   - Queries PreorderManager.find_matching_preorder('Birch Sap')
   - Match found: 5000x @ 58M
9. NEW: _apply_preorder_correction()
   - Corrected total: 62,250,900 + 58,000,000 = 120,250,900
   - Corrected price: 120,250,900 / 10,000 = 12,025 Silver/item
10. Plausibility check passes (12,025 within base_price ±15%)
11. Transaction saved with corrected price
12. PreorderManager.mark_collected(preorder_id)
```

---

## 3.3 Critical Design Decisions

### Decision 1: Detail-Window Detection vs. Log Parsing

**DECISION**: Primary detection in detail-window, log parsing as fallback only.

**Rationale**:
- User may NOT return to overview after placing preorder (closes detail-window directly)
- Transaction log only visible in overview windows
- Detail-window provides real-time detection (no delay)
- Balance/warehouse metrics are reliable indicators

**Implementation**:
1. **Detail-Window Detection** (PRIMARY):
   - Condition: `balance_delta < 0 AND warehouse_delta == 0`
   - Extract quantity from UI metrics (`orders` field)
   - Store immediately, update rolling baseline
   
2. **Log Parsing Detection** (FALLBACK):
   - Parse "Placed order" events after returning to overview
   - Check for duplicates (by item, qty, price, timestamp ±10s)
   - Only store if NOT already detected in detail-window

### Decision 2: Rolling Baseline Update After Preorder

**DECISION**: Update rolling baseline immediately after preorder placement.

**Rationale**:
- Next purchase (auto-collect) must calculate deltas from POST-PREORDER baseline
- If we keep old baseline, auto-collect will show: `balance_delta = -(preorder + purchase)`
- This would make auto-collect detection impossible

**Critical Flow**:
```
1. Initial baseline: balance=1000M, warehouse=0
2. Preorder placed: balance=942M (-58M), warehouse=0
   → DETECT PREORDER, STORE IT
   → UPDATE BASELINE: balance=942M, warehouse=0
3. Purchase+collect: balance=879.75M (-62.25M), warehouse=10k (+10k)
   → DETECT AUTO-COLLECT (warehouse surplus)
   → MATCH PREORDER, ADD 58M TO PRICE
   → SAVE TX: 10k @ 120.25M
   → UPDATE BASELINE: balance=879.75M, warehouse=10k
4. Next purchase: deltas calculated from step 3 baseline
```

**Alternative (REJECTED)**:
- Keep original baseline, accumulate all deltas
- Problem: Cannot distinguish preorder from purchase in accumulated deltas
- Problem: Violates existing rolling baseline architecture

### Decision 3: Quantity Extraction from UI Metrics

**DECISION**: Use `orders` field from current_metrics for preorder quantity.

**Rationale**:
- When preorder is placed, `orders` field shows pending order count
- No quantity visible in balance change (only price)
- UI metrics parsing already exists and is reliable

**Edge Cases**:
- Multiple orders: `orders` shows total pending (may include other items)
- Mitigation: Only trust `orders` when exactly 1 item window open
- Future: Add per-item order tracking if needed

### Decision 4: No Interference with Existing Delta Logic

**DECISION**: Early return after preorder detection, before any transaction inference.

**Rationale**:
- Preorder placement is NOT a transaction (no warehouse change)
- Existing plausibility checks expect warehouse change
- Keeping them separate avoids complex conditional logic

**Implementation Pattern**:
```python
# Step 1: Check for preorder placement
if balance_delta < 0 and warehouse_delta == 0:
    if self._detect_preorder_placement(...):
        # Update baseline, reset state
        return  # EARLY EXIT - no transaction to infer
    # else: might be network lag, wait for warehouse update

# Step 2: Check for auto-collect (existing logic continues)
if balance_delta < 0 and warehouse_delta > 0:
    preorder_correction = self._check_for_preorder_autocollect(...)
    # Continue with existing inference...
```

---

## 4. Detailed Design

### 4.1 Database Schema

#### New Table: `preorders`

```sql
CREATE TABLE preorders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,              -- Total quantity ordered
    quantity_filled INTEGER DEFAULT 0,      -- How much has been filled (partial fills)
    price REAL NOT NULL,                    -- Total price paid for the FULL order
    timestamp DATETIME NOT NULL,            -- When the preorder was placed (game time)
    status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'collected', 'cancelled'
    collected_at DATETIME,                  -- When the preorder was collected
    collected_tx_id INTEGER,                -- Foreign key to transactions.id
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for fast lookup
CREATE INDEX idx_preorders_item_status ON preorders(item_name, status);
CREATE INDEX idx_preorders_timestamp ON preorders(timestamp DESC);
CREATE INDEX idx_preorders_status ON preorders(status);

-- CRITICAL: Unique constraint to enforce ONE active preorder per item
CREATE UNIQUE INDEX idx_preorders_one_active_per_item 
ON preorders(item_name) 
WHERE status = 'active';
```

#### Schema Migration
```python
# In database.py, after existing table creation:
_base_cur.execute("""
CREATE TABLE IF NOT EXISTS preorders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_name TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    quantity_filled INTEGER DEFAULT 0,
    price REAL NOT NULL,
    timestamp DATETIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    collected_at DATETIME,
    collected_tx_id INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")

# Migration: Add quantity_filled column if missing
try:
    _base_cur.execute("PRAGMA table_info(preorders)")
    cols = [r[1] for r in _base_cur.fetchall()]
    if 'quantity_filled' not in cols:
        _base_cur.execute("ALTER TABLE preorders ADD COLUMN quantity_filled INTEGER DEFAULT 0")
except Exception:
    pass

_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_preorders_item_status 
ON preorders(item_name, status)
""")

_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_preorders_timestamp 
ON preorders(timestamp DESC)
""")

_base_cur.execute("""
CREATE INDEX IF NOT EXISTS idx_preorders_status 
ON preorders(status)
""")

# CRITICAL: Enforce ONE active preorder per item
_base_cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS idx_preorders_one_active_per_item
ON preorders(item_name)
WHERE status = 'active'
""")

_base_conn.commit()
```

### 4.2 Preorder Manager Module

#### New File: `preorder_manager.py`

```python
"""
Preorder Manager Module
Handles storage, retrieval, and matching of preorder data.
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from database import get_cursor, get_connection
from utils import log_debug

class PreorderManager:
    """
    Manages preorder lifecycle:
    1. Store preorder when user places order
    2. Retrieve matching preorders for auto-collect detection
    3. Mark preorders as collected after successful transaction
    4. Clean up expired/cancelled preorders
    """
    
    def __init__(self, debug: bool = False):
        self.debug = debug
        # In-memory cache of active preorders (refreshed on demand)
        self._active_preorders_cache: Optional[List[Dict]] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = timedelta(seconds=60)  # Refresh cache every 60s
    
    # === Storage Operations ===
    
    def store_preorder(
        self,
        item_name: str,
        quantity: int,
        price: float,
        timestamp: datetime
    ) -> int:
        """
        Store a new preorder in the database.
        
        CRITICAL: Only ONE active preorder per item allowed!
        If an active preorder already exists for this item:
        1. Mark old preorder as 'collected' (auto-collected on replacement)
        2. Store new preorder
        
        Args:
            item_name: Corrected item name (after market_json_manager)
            quantity: Quantity of the preorder
            price: Total price paid for the preorder
            timestamp: Game timestamp when order was placed
            
        Returns:
            Preorder ID (database primary key)
        """
        try:
            cur = get_cursor()
            
            # Check for existing active preorder for this item
            cur.execute(
                """
                SELECT id, quantity, quantity_filled, price
                FROM preorders
                WHERE item_name = ? AND status = 'active'
                """,
                (item_name,)
            )
            existing = cur.fetchone()
            
            if existing:
                old_id, old_qty, old_filled, old_price = existing
                # Mark old preorder as collected (auto-collected on replacement)
                # This includes any partial fills
                cur.execute(
                    """
                    UPDATE preorders
                    SET status = 'collected',
                        collected_at = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (timestamp, old_id)
                )
                
                if self.debug:
                    fill_info = f", filled={old_filled}" if old_filled > 0 else ""
                    log_debug(
                        f"[PREORDER] Auto-collected old preorder on replacement: "
                        f"{item_name} x{old_qty}{fill_info} @ {old_price:,.0f} (ID: {old_id})"
                    )
            
            # Store new preorder
            cur.execute(
                """
                INSERT INTO preorders 
                (item_name, quantity, price, timestamp, status)
                VALUES (?, ?, ?, ?, 'active')
                """,
                (item_name, quantity, price, timestamp)
            )
            get_connection().commit()
            preorder_id = cur.lastrowid
            
            # Invalidate cache
            self._active_preorders_cache = None
            
            if self.debug:
                log_debug(
                    f"[PREORDER] Stored: {item_name} x{quantity} @ "
                    f"{price:,.0f} Silver (ID: {preorder_id}, TS: {timestamp})"
                )
            
            return preorder_id
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR storing preorder: {e}")
            return -1
    
    # === Retrieval Operations ===
    
    def find_matching_preorder(
        self,
        item_name: str,
        warehouse_delta: int,
        balance_delta: float,
        timestamp: datetime
    ) -> Optional[Dict]:
        """
        Find a matching active preorder for auto-collect detection.
        
        Matching Logic:
        1. Item name must match (exact, case-insensitive)
        2. Status must be 'active'
        3. Quantity consistent with warehouse_delta surplus
        
        NOTE: No time tolerance needed - preorders never expire!
              Only ONE active preorder per item possible.
        
        Args:
            item_name: Item being purchased
            warehouse_delta: Warehouse increase (may include preorder qty)
            balance_delta: Balance decrease (purchase price only)
            timestamp: Current transaction timestamp (for logging only)
            
        Returns:
            Dict with preorder data, or None if no match found
            Keys: id, item_name, quantity, quantity_filled, price, timestamp
        """
        try:
            # Refresh cache if stale
            self._refresh_cache_if_needed()
            
            if not self._active_preorders_cache:
                return None
            
            # Filter by item name (case-insensitive)
            item_lower = item_name.lower()
            candidates = [
                po for po in self._active_preorders_cache
                if po['item_name'].lower() == item_lower
            ]
            
            if not candidates:
                return None
            
            # With ONE active preorder per item, we should have at most 1 candidate
            if len(candidates) > 1:
                if self.debug:
                    log_debug(
                        f"[PREORDER] WARNING: Multiple active preorders for '{item_name}' "
                        f"(should not happen with unique constraint!)"
                    )
            
            # Take the first (and should be only) candidate
            candidate = candidates[0]
            
            # Check if there's any filled quantity to collect
            quantity_filled = candidate.get('quantity_filled', 0)
            
            # Validate quantity alignment
            # For partial fills: we collect the filled portion
            if quantity_filled > 0 and quantity_filled <= warehouse_delta:
                if self.debug:
                    log_debug(
                        f"[PREORDER] Match found (partial fill): {candidate['item_name']} "
                        f"x{candidate['quantity']} (filled={quantity_filled}) @ {candidate['price']:,.0f} "
                        f"(ID: {candidate['id']})"
                    )
                return candidate
            # For non-filled preorders: standard check
            elif quantity_filled == 0 and candidate['quantity'] <= warehouse_delta:
                if self.debug:
                    log_debug(
                        f"[PREORDER] Match found: {candidate['item_name']} "
                        f"x{candidate['quantity']} @ {candidate['price']:,.0f} "
                        f"(ID: {candidate['id']})"
                    )
                return candidate
            else:
                if self.debug:
                    log_debug(
                        f"[PREORDER] No quantity match for '{item_name}' "
                        f"(preorder_qty={candidate['quantity']}, filled={quantity_filled}, "
                        f"warehouse_delta={warehouse_delta})"
                    )
                return None
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR finding match: {e}")
            return None
    
    def get_active_preorders(
        self,
        item_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve all active preorders, optionally filtered by item name.
        
        Args:
            item_name: Optional item name filter
            
        Returns:
            List of preorder dicts
        """
        try:
            # Refresh cache if needed
            self._refresh_cache_if_needed()
            
            if self._active_preorders_cache is None:
                return []
            
            if item_name is None:
                return self._active_preorders_cache.copy()
            
            item_lower = item_name.lower()
            return [
                po for po in self._active_preorders_cache
                if po['item_name'].lower() == item_lower
            ]
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR retrieving active preorders: {e}")
            return []
    
    # === Update Operations ===
    
    def mark_collected(
        self,
        preorder_id: int,
        collected_at: datetime,
        transaction_id: Optional[int] = None
    ) -> bool:
        """
        Mark a preorder as collected after successful transaction storage.
        
        Args:
            preorder_id: ID of the preorder to mark
            collected_at: Timestamp when collection occurred
            transaction_id: Optional foreign key to transactions table
            
        Returns:
            True if update successful, False otherwise
        """
        try:
            cur = get_cursor()
            cur.execute(
                """
                UPDATE preorders
                SET status = 'collected',
                    collected_at = ?,
                    collected_tx_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'active'
                """,
                (collected_at, transaction_id, preorder_id)
            )
            get_connection().commit()
            
            if cur.rowcount > 0:
                # Invalidate cache
                self._active_preorders_cache = None
                
                if self.debug:
                    log_debug(
                        f"[PREORDER] Marked collected: ID={preorder_id}, "
                        f"collected_at={collected_at}, tx_id={transaction_id}"
                    )
                return True
            else:
                if self.debug:
                    log_debug(
                        f"[PREORDER] Failed to mark collected: ID={preorder_id} "
                        "(not found or already collected)"
                    )
                return False
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR marking collected: {e}")
            return False
    
    def cancel_preorder(
        self,
        item_name: str,
        quantity: int,
        price: float
    ) -> bool:
        """
        Mark a preorder as cancelled (triggered by "Withdrew order" log entry).
        
        Match by item_name + quantity + price (all must match).
        
        Args:
            item_name: Item name (corrected)
            quantity: Order quantity
            price: Order price (total)
            
        Returns:
            True if preorder found and cancelled, False otherwise
        """
        try:
            cur = get_cursor()
            
            # Find matching active preorder
            cur.execute(
                """
                SELECT id
                FROM preorders
                WHERE item_name = ? 
                  AND quantity = ? 
                  AND price = ?
                  AND status = 'active'
                """,
                (item_name, quantity, price)
            )
            
            row = cur.fetchone()
            if not row:
                if self.debug:
                    log_debug(
                        f"[PREORDER] No active preorder to cancel: "
                        f"{item_name} x{quantity} @ {price:,.0f}"
                    )
                return False
            
            preorder_id = row[0]
            
            # Mark as cancelled
            cur.execute(
                """
                UPDATE preorders
                SET status = 'cancelled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (preorder_id,)
            )
            get_connection().commit()
            
            # Invalidate cache
            self._active_preorders_cache = None
            
            if self.debug:
                log_debug(
                    f"[PREORDER] Cancelled: {item_name} x{quantity} @ {price:,.0f} "
                    f"(ID: {preorder_id})"
                )
            
            return True
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR cancelling preorder: {e}")
            return False
    
    # REMOVED: mark_expired() - Preorders never expire!
    # REMOVED: expire_old_preorders() - Not needed
    
    # === Cache Management ===
    
    def _refresh_cache_if_needed(self):
        """
        Refresh the active preorders cache if stale or empty.
        """
        now = datetime.now()
        
        # Check if cache needs refresh
        if (
            self._active_preorders_cache is None
            or self._cache_timestamp is None
            or (now - self._cache_timestamp) > self._cache_ttl
        ):
            self._refresh_cache()
    
    def _refresh_cache(self):
        """
        Load all active preorders from database into memory cache.
        """
        try:
            cur = get_cursor()
            cur.execute(
                """
                SELECT id, item_name, quantity, quantity_filled, price, timestamp
                FROM preorders
                WHERE status = 'active'
                ORDER BY timestamp ASC
                """
            )
            
            rows = cur.fetchall()
            self._active_preorders_cache = [
                {
                    'id': row[0],
                    'item_name': row[1],
                    'quantity': row[2],
                    'quantity_filled': row[3],
                    'price': row[4],
                    'timestamp': row[5]
                }
                for row in rows
            ]
            
            self._cache_timestamp = datetime.now()
            
            if self.debug:
                log_debug(
                    f"[PREORDER] Cache refreshed: {len(self._active_preorders_cache)} "
                    "active preorder(s)"
                )
        
        except Exception as e:
            if self.debug:
                log_debug(f"[PREORDER] ERROR refreshing cache: {e}")
            self._active_preorders_cache = []
            self._cache_timestamp = datetime.now()
    
    def invalidate_cache(self):
        """
        Force cache invalidation (useful for testing or manual refresh).
        """
        self._active_preorders_cache = None
        self._cache_timestamp = None
        
        if self.debug:
            log_debug("[PREORDER] Cache invalidated")
```

### 4.3 Integration with MarketTracker

#### Changes to `tracker.py`

##### 4.3.1 State Variables (Lines 102-280)

Add new state variables in `__init__`:

```python
# Preorder Tracking (NEW)
from preorder_manager import PreorderManager
self._preorder_manager = PreorderManager(debug=self.debug)
```

##### 4.3.2 Transaction Log Processing (Lines 3000-3200)

Add preorder cancellation detection after structured entries are built:

```python
# After building structured entries (around line 3130):
# NEW: Detect and handle preorder cancellations
for s in structured:
    if s.get('type') == 'withdrew' and s.get('item') and s.get('qty') and s.get('price'):
        self._handle_preorder_cancellation(
            item_name=s['item'],
            quantity=s['qty'],
            price=s['price']
        )
```

Add new method:

```python
def _handle_preorder_cancellation(
    self,
    item_name: str,
    quantity: int,
    price: float
):
    """
    Handle detection of preorder cancellation from transaction log.
    
    Called when transaction log shows "Withdrew order" event.
    Marks matching active preorder as cancelled.
    
    Args:
        item_name: Item name (raw from OCR)
        quantity: Order quantity
        price: Total price
    """
    try:
        # Correct item name using market_json_manager
        from market_json_manager import correct_item_name
        corrected_name = correct_item_name(item_name)
        
        # Cancel preorder
        cancelled = self._preorder_manager.cancel_preorder(
            item_name=corrected_name,
            quantity=quantity,
            price=price
        )
        
        if cancelled and self.debug:
            log_debug(
                f"[PREORDER-CANCELLED] Detected: {corrected_name} x{quantity} "
                f"@ {price:,.0f} Silver"
            )
    
    except Exception as e:
        if self.debug:
            log_debug(f"[PREORDER-CANCELLED] ERROR: {e}")
```

##### 4.3.3 Detail-Window Monitoring (Lines 2700-2900)

Modify `_monitor_detail_window` to add **TWO** preorder detections:

**CRITICAL NEW LOGIC**: Add preorder placement detection BEFORE existing logic:

**Location**: After sync-check passes (around line 2743), BEFORE any transaction inference

```python
# After sync-check passes (both values changed):

# ===== NEW: PREORDER PLACEMENT DETECTION =====
# CRITICAL: Detect preorder when balance↓ but warehouse unchanged
# This MUST happen BEFORE plausibility check to avoid false rejections
if balance_delta < 0 and warehouse_delta == 0:
    # Preorder placement detected!
    preorder_detected = self._detect_preorder_placement(
        item_name=self._detail_window_item,
        balance_delta=balance_delta,
        current_metrics=current_metrics,
        timestamp=datetime.datetime.now()
    )
    
    if preorder_detected:
        # IMPORTANT: Update rolling baseline for next transaction
        self._detail_baseline_balance = current_metrics.get('balance')
        self._detail_baseline_warehouse = current_metrics.get('warehouse')
        self._detail_last_metrics = current_metrics.copy()
        
        # Reset delta accumulators
        self._detail_partial_balance_delta = 0
        self._detail_partial_warehouse_delta = 0
        self._detail_balance_changed_once = False
        self._detail_warehouse_changed_once = False
        
        if self.debug:
            log_debug(
                f"[PREORDER-PLACED] Rolling baseline updated after preorder placement "
                f"(balance={current_metrics.get('balance'):,.0f})"
            )
        
        # CRITICAL: Return early - no transaction to infer yet
        return
# ===== END PREORDER PLACEMENT DETECTION =====

# Now continue with existing logic for purchases/sells:

# NEW: Check for preorder auto-collect scenario
preorder_correction = self._check_for_preorder_autocollect(
    item_name=self._detail_window_item,  # Use baseline item name
    warehouse_delta=warehouse_delta,
    balance_delta=balance_delta,
    timestamp=datetime.datetime.now()
)

# Apply preorder correction if detected
if preorder_correction:
    corrected_balance_delta = balance_delta - preorder_correction['price']
    if self.debug:
        log_debug(
            f"[PREORDER-AUTOCOLLECT] Detected: {self._detail_window_item} "
            f"x{preorder_correction['quantity']} @ {preorder_correction['price']:,.0f} Silver"
        )
        log_debug(
            f"[PREORDER-AUTOCOLLECT] Original balance_delta: {balance_delta:,.0f}, "
            f"Corrected: {corrected_balance_delta:,.0f}"
        )
else:
    corrected_balance_delta = balance_delta

# Continue with plausibility check using corrected_balance_delta
```

Add two new methods:

```python
def _detect_preorder_placement(
    self,
    item_name: str,
    balance_delta: float,
    current_metrics: dict,
    timestamp: datetime.datetime
) -> bool:
    """
    Detect when user places a preorder in detail-window.
    
    Detection Logic:
    1. balance_delta < 0 (silver spent)
    2. warehouse_delta == 0 (no items received yet)
    3. Extract quantity from UI metrics (Orders field)
    
    CRITICAL: This must NOT interfere with existing delta logic!
    We return early after storing preorder and updating baseline.
    
    Args:
        item_name: Item name (from baseline)
        balance_delta: Balance decrease (negative)
        current_metrics: Current UI metrics dict
        timestamp: Current timestamp
        
    Returns:
        True if preorder detected and stored, False otherwise
    """
    try:
        # Calculate preorder price
        preorder_price = abs(balance_delta)
        
        # Extract quantity from UI metrics
        # In buy_item window: "Orders" field shows pending order quantity
        orders = current_metrics.get('orders', 0)
        
        if orders <= 0:
            if self.debug:
                log_debug(
                    f"[PREORDER-DETECT] Cannot determine quantity: "
                    f"orders={orders}"
                )
            return False
        
        preorder_qty = orders
        
        # Sanity check: price must be plausible
        implied_unit_price = preorder_price / preorder_qty
        base_price = self._get_base_price(item_name)
        
        if base_price is not None:
            min_price = base_price * 0.85
            max_price = base_price * 1.15
            
            if not (min_price <= implied_unit_price <= max_price):
                if self.debug:
                    log_debug(
                        f"[PREORDER-DETECT] Price implausible: "
                        f"{implied_unit_price:,.0f} not in range "
                        f"[{min_price:,.0f}, {max_price:,.0f}]"
                    )
                return False
        
        # Store preorder
        from market_json_manager import correct_item_name
        corrected_name = correct_item_name(item_name)
        
        preorder_id = self._preorder_manager.store_preorder(
            item_name=corrected_name,
            quantity=preorder_qty,
            price=preorder_price,
            timestamp=timestamp
        )
        
        if preorder_id > 0:
            if self.debug:
                log_debug(
                    f"[PREORDER-PLACED] ✅ Detected: {corrected_name} "
                    f"x{preorder_qty:,} @ {preorder_price:,.0f} Silver "
                    f"(unit: {implied_unit_price:,.0f}, ID: {preorder_id})"
                )
            return True
        else:
            return False
    
    except Exception as e:
        if self.debug:
            log_debug(f"[PREORDER-DETECT] ERROR: {e}")
        return False

def _check_for_preorder_autocollect(
    self,
    item_name: str,
    warehouse_delta: int,
    balance_delta: float,
    timestamp: datetime.datetime
) -> Optional[Dict]:
    """
    Check if warehouse increase indicates preorder auto-collect.
    
    Auto-collect detection logic:
    1. warehouse_delta > expected purchase quantity
    2. Matching active preorder exists for this item
    3. Quantity alignment: warehouse_delta ≈ purchase_qty + preorder_qty
    
    Args:
        item_name: Item being purchased (from baseline)
        warehouse_delta: Warehouse increase
        balance_delta: Balance decrease (negative)
        timestamp: Current transaction timestamp
        
    Returns:
        Dict with preorder data if match found:
            {'id': int, 'quantity': int, 'price': float}
        None if no preorder auto-collect detected
    """
    try:
        # Sanity check: warehouse_delta must be positive
        if warehouse_delta <= 0:
            return None
        
        # Get base price for estimation
        base_price = self._get_base_price(item_name)
        if base_price is None:
            if self.debug:
                log_debug(
                    f"[PREORDER-CHECK] Cannot estimate purchase qty: "
                    f"no base_price for '{item_name}'"
                )
            return None
        
        # Estimate purchase quantity from balance change
        # balance_delta is negative, so abs() it
        estimated_purchase_qty = abs(balance_delta) / base_price
        
        # Check if warehouse increase is significantly larger than purchase
        # Allow 10% tolerance for price variations
        if warehouse_delta <= estimated_purchase_qty * 1.1:
            # Warehouse increase matches purchase - no auto-collect
            return None
        
        if self.debug:
            log_debug(
                f"[PREORDER-CHECK] Potential auto-collect: warehouse_delta={warehouse_delta}, "
                f"estimated_purchase_qty={estimated_purchase_qty:.1f} "
                f"(base_price={base_price:,.0f})"
            )
        
        # Query PreorderManager for matching preorder
        matching_preorder = self._preorder_manager.find_matching_preorder(
            item_name=item_name,
            warehouse_delta=warehouse_delta,
            balance_delta=balance_delta,
            timestamp=datetime.datetime.now()
        )
        
        return matching_preorder
    
    except Exception as e:
        if self.debug:
            log_debug(f"[PREORDER-CHECK] ERROR: {e}")
        return None

def _check_for_auto_preorder_creation(
    self,
    item_name: str,
    warehouse_delta: int,
    balance_delta: float,
    timestamp: datetime.datetime
) -> Optional[Tuple[int, float, int, float]]:
    """
    Check if insufficient stock caused auto-preorder creation.
    
    Detection logic:
    1. balance_delta (price paid) suggests quantity X
    2. warehouse_delta (received) shows quantity Y < X
    3. Difference (X - Y) = auto-preorder quantity
    
    Example:
        Attempt to buy 5000x @ 40M
        Only 2000x available
        Game buys 2k and creates 3k preorder
    
    Args:
        item_name: Item name
        warehouse_delta: Actual warehouse increase (2000)
        balance_delta: Total price paid (-40M)
        timestamp: Transaction timestamp
        
    Returns:
        Tuple (purchase_qty, purchase_price, preorder_qty, preorder_price)
        or None if no auto-preorder detected
    """
    try:
        # Sanity checks
        if warehouse_delta <= 0 or balance_delta >= 0:
            return None
        
        # Get base price for estimation
        base_price = self._get_base_price(item_name)
        if base_price is None:
            return None
        
        # Estimate total quantity user attempted to buy
        total_price = abs(balance_delta)
        estimated_total_qty = total_price / base_price
        
        # Check if warehouse received LESS than expected
        # Allow 5% tolerance for rounding
        if warehouse_delta >= estimated_total_qty * 0.95:
            # Received full amount - no auto-preorder
            return None
        
        # Calculate quantities
        purchase_qty = warehouse_delta
        preorder_qty = int(round(estimated_total_qty - purchase_qty))
        
        # Sanity check: preorder must be significant (at least 10% of total)
        if preorder_qty < estimated_total_qty * 0.1:
            return None
        
        # Split price proportionally
        purchase_price = total_price * (purchase_qty / estimated_total_qty)
        preorder_price = total_price * (preorder_qty / estimated_total_qty)
        
        if self.debug:
            log_debug(
                f"[AUTO-PREORDER] Detected: {item_name} "
                f"(attempted={estimated_total_qty:.0f}, received={purchase_qty}, "
                f"preorder={preorder_qty}) "
                f"purchase_price={purchase_price:,.0f}, preorder_price={preorder_price:,.0f}"
            )
        
        return (purchase_qty, purchase_price, preorder_qty, preorder_price)
    
    except Exception as e:
        if self.debug:
            log_debug(f"[AUTO-PREORDER] ERROR: {e}")
        return None
```

##### 4.3.4 Transaction Inference (Lines 2860-2900)

Modify `_infer_transaction_from_deltas` signature to accept preorder data:

**Current signature (line ~2860)**:
```python
def _infer_transaction_from_deltas(
    self,
    balance_delta: float,
    warehouse_delta: int,
    item_name: str,
    window_type: str,
    ocr_text: str
) -> Optional[dict]:
```

**New signature**:
```python
def _infer_transaction_from_deltas(
    self,
    balance_delta: float,
    warehouse_delta: int,
    item_name: str,
    window_type: str,
    ocr_text: str,
    preorder_correction: Optional[Dict] = None  # NEW parameter
) -> Optional[dict]:
```

**Modify calculation logic (around line 2879)**:

```python
# Original calculation
total_price = abs(balance_delta)  # OLD: Missing preorder price!

# NEW: Apply preorder correction if provided
if preorder_correction:
    preorder_price = preorder_correction['price']
    total_price = abs(balance_delta) + preorder_price
    
    if self.debug:
        log_debug(
            f"[PREORDER-CORRECTION] Total price adjusted: "
            f"{abs(balance_delta):,.0f} (balance) + {preorder_price:,.0f} (preorder) "
            f"= {total_price:,.0f} Silver"
        )
else:
    total_price = abs(balance_delta)

# Continue with per-item price calculation
unit_price = total_price / abs(warehouse_delta) if warehouse_delta != 0 else 0
```

##### 4.3.5 Update Call Sites

**In `_monitor_detail_window` (around line 2885)**:

```python
# OLD:
tx = self._infer_transaction_from_deltas(
    balance_delta,
    warehouse_delta,
    self._detail_window_item,
    self._detail_window_type,
    ocr_text
)

# NEW:
tx = self._infer_transaction_from_deltas(
    balance_delta,
    warehouse_delta,
    self._detail_window_item,
    self._detail_window_type,
    ocr_text,
    preorder_correction=preorder_correction  # Pass correction data
)
```

##### 4.3.6 Mark Preorder as Collected (After Transaction Storage)

**In `_monitor_detail_window`, after `store_transaction_db` succeeds (around line 2875)**:

```python
# After successful transaction storage:
if store_success and preorder_correction:
    # Mark preorder as collected
    self._preorder_manager.mark_collected(
        preorder_id=preorder_correction['id'],
        collected_at=datetime.datetime.now(),
        transaction_id=None  # TODO: Get transaction ID from store_transaction_db
    )
    
    if self.debug:
        log_debug(
            f"[PREORDER-COLLECTED] Marked preorder ID={preorder_correction['id']} "
            "as collected"
        )
```

**Note**: `store_transaction_db` currently doesn't return transaction ID. Consider modifying it:

```python
# In database.py, modify store_transaction_db to return ID:
def store_transaction_db(...) -> int:
    """
    ...
    Returns:
        Transaction ID (primary key) if successful, -1 if failed/duplicate
    """
    # After INSERT:
    tx_id = cur.lastrowid
    # At end:
    return tx_id  # Instead of just True
```

##### 4.3.7 Periodic Cleanup

**REMOVED**: No periodic cleanup needed - preorders never expire!

Only cleanup needed: Remove obsolete `expire_old_preorders()` call if it exists.

---

## 5. Implementation Phases

### Phase 1: Database & Core Module (2-3 hours)
**Priority**: HIGH  
**Dependencies**: None

**Tasks**:
1. ✅ Create database migration for `preorders` table
2. ✅ Implement `PreorderManager` class with core methods:
   - `store_preorder()`
   - `find_matching_preorder()`
   - `mark_collected()`
   - `get_active_preorders()`
3. ✅ Add cache management logic
4. ✅ Write unit tests for PreorderManager

**Deliverables**:
- `preorder_manager.py` (fully implemented)
- Database migration code in `database.py`
- Unit tests in `tests/unit/test_preorder_manager.py`

**Acceptance Criteria**:
- Preorders can be stored and retrieved from database
- Cache invalidation works correctly
- No performance regressions (< 5ms per lookup)

---

### Phase 2: Detail-Window Preorder Detection (2-3 hours)
**Priority**: HIGH  
**Dependencies**: Phase 1

**Tasks**:
1. ✅ Implement `_detect_preorder_placement()` method
2. ✅ Integrate detection in `_monitor_detail_window()` (BEFORE existing logic)
3. ✅ Ensure rolling baseline update after preorder placement
4. ✅ Test that delta logic continues to work for subsequent purchases
5. ✅ Add unit tests for preorder detection scenarios

**Deliverables**:
- Modified `tracker.py` (detail-window section)
- New tests in `tests/unit/test_preorder_detection.py`

**Acceptance Criteria**:
- Preorder placement detected: balance↓, warehouse=0
- Preorder stored with correct item, qty, price
- Rolling baseline updated correctly
- Subsequent purchase detection still works (no interference)

---

### Phase 2b: Log Parsing for Cancellation (1 hour)
**Priority**: HIGH  
**Dependencies**: Phase 1

**Tasks**:
1. ✅ Add `_handle_preorder_cancellation()` method to MarketTracker
2. ✅ Integrate cancellation detection in `process_ocr_text()`
3. ✅ Test with withdrew log entries
4. ✅ Add cancellation-specific tests

**Deliverables**:
- Modified `tracker.py` (log parsing section)
- New tests in `tests/unit/test_preorder_cancellation.py`

**Acceptance Criteria**:
- "Withdrew order" events mark preorder as cancelled
- Item names corrected via market_json_manager
- Match by item + quantity + price works correctly

---

### Phase 3: Auto-Collect Detection & Correction (3-4 hours)
**Priority**: HIGH  
**Dependencies**: Phase 1, Phase 2

**Tasks**:
1. ✅ Implement `_check_for_preorder_autocollect()` method
2. ✅ Implement `_check_for_auto_preorder_creation()` method
3. ✅ **CRITICAL**: Implement detection chain for combined scenarios (partial fill + auto-preorder)
4. ✅ Modify `_monitor_detail_window()` to call preorder check (AFTER placement detection)
5. ✅ Update `_infer_transaction_from_deltas()` signature and logic
6. ✅ Update all call sites
7. ✅ Implement preorder marking after transaction storage
8. ✅ Test with Birch Sap scenario (manual test)
9. ✅ Test combined scenario (partial fill + auto-preorder)

**Detection Chain Logic (CRITICAL for combined scenarios)**:
```python
# In _monitor_detail_window(), after delta calculation:

# Step 1: Check for preorder auto-collect FIRST
preorder_match = self._check_for_preorder_autocollect(
    item_name=item_name,
    warehouse_delta=warehouse_delta,
    balance_delta=balance_delta
)

if preorder_match:
    # Calculate preorder contribution
    preorder_qty = preorder_match.get('quantity_filled', preorder_match['quantity'])
    preorder_contribution = preorder_match['price'] * (preorder_qty / preorder_match['quantity'])
    
    # Subtract preorder quantity from warehouse_delta
    actual_purchase_qty = warehouse_delta - preorder_qty
else:
    preorder_contribution = 0
    actual_purchase_qty = warehouse_delta

# Step 2: Calculate expected purchase from balance_delta
base_price = self._get_base_price(item_name)
expected_purchase_qty = abs(balance_delta) / base_price

# Step 3: Check if auto-preorder created (shortage detected)
if actual_purchase_qty < expected_purchase_qty * 0.95:
    # Shortage detected! Game created auto-preorder
    auto_preorder_result = self._check_for_auto_preorder_creation(
        item_name=item_name,
        warehouse_delta=actual_purchase_qty,  # Use ADJUSTED qty (after preorder)
        balance_delta=balance_delta,
        timestamp=datetime.now()
    )
    
    if auto_preorder_result:
        purchase_qty, purchase_price, new_preorder_qty, new_preorder_price = auto_preorder_result
        
        # Store new preorder
        self._preorder_manager.store_preorder(
            item_name=item_name,
            quantity=new_preorder_qty,
            price=new_preorder_price,
            timestamp=datetime.now()
        )

# Step 4: Calculate corrected transaction total
corrected_total = abs(balance_delta) + preorder_contribution
```

**Deliverables**:
- Modified `tracker.py` (detail-window section)
- Manual test report with screenshots

**Acceptance Criteria**:
- Preorder placement: balance↓, warehouse=0 → stored correctly
- Subsequent purchase: balance↓, warehouse↑ → auto-collect detected
- Birch Sap test shows correct total: 120,250,900 Silver
- Preorder marked as collected after transaction
- No false positives (regular purchases not flagged as auto-collect)
- **COMPLEX**: Partial fill + auto-preorder in SAME transaction handled correctly

---

### Phase 4: Transaction Storage Enhancement (1 hour)
**Priority**: MEDIUM  
**Dependencies**: Phase 3

**Tasks**:
1. ✅ Modify `store_transaction_db()` to return transaction ID
2. ✅ Update call sites to use returned ID
3. ✅ Link preorder to transaction via `collected_tx_id`
4. ✅ Add database query helper to retrieve transaction by preorder

**Deliverables**:
- Modified `database.py`
- Updated `tracker.py` call sites

**Acceptance Criteria**:
- Transactions and preorders correctly linked via foreign key
- Database queries work correctly

---

### Phase 5: Edge Cases & Robustness (1-2 hours)
**Priority**: MEDIUM  
**Dependencies**: Phase 3

**Tasks**:
1. ⚠️ Test preorder replacement scenario (new preorder while old active)
2. ⚠️ Test auto-collect on replacement (old collected when new placed)
3. ⚠️ Add comprehensive error handling
4. ⚠️ Test edge cases (rapid preorder changes, etc.)

**Deliverables**:
- Enhanced PreorderManager methods
- Edge case tests in `tests/unit/test_preorder_edge_cases.py`

**Acceptance Criteria**:
- Preorder replacement works (ONE active per item enforced)
- Auto-collect on replacement tracked correctly
- No crashes on edge cases

**IMPORTANT: Partial Fill Support**:
- Partial preorder fills ARE supported by game (e.g., 3k of 5k filled)
- `quantity_filled` column tracks partial fill progress
- Price correction must account for partial fills (see detailed algorithm below)
- Test cases must cover partial fill + purchase scenarios

---

#### 5.1 Price Correction Algorithm

**Overview**:
When auto-collecting a preorder (full or partial), the transaction price must include both the current purchase and the preorder amount.

**Case 1: Full Preorder Auto-Collect** (Birch Sap scenario)
```python
# User placed: 5000x @ 58M (preorder, fully filled)
# User bought: 5000x @ 62.25M (regular purchase)
# Auto-collect triggered: preorder collected

purchase_price = 62_250_900  # From balance_delta
preorder_price = 58_000_000  # From database

corrected_price = purchase_price + preorder_price
# = 62.25M + 58M = 120.25M

# Store transaction:
# item: Birch Sap
# quantity: 10000
# price: 120.25M
```

**Case 2: Partial Preorder Auto-Collect**
```python
# User placed: 5000x @ 58M (preorder)
# Market filled: 3000x (partial)
# User bought: 2000x @ 62M (regular purchase)
# Auto-collect triggered: 3000x from preorder collected

purchase_price = 62_000_000  # From balance_delta
preorder_total = 58_000_000  # From database
preorder_qty = 5000           # Total ordered
filled_qty = 3000             # Actually filled

# Calculate preorder contribution (proportional)
preorder_contribution = preorder_total * (filled_qty / preorder_qty)
# = 58M × (3000 / 5000) = 34.8M

corrected_price = purchase_price + preorder_contribution
# = 62M + 34.8M = 96.8M

# Store transaction:
# item: Birch Sap
# quantity: 5000 (2k purchase + 3k preorder)
# price: 96.8M
```

**Case 3: Auto-Preorder Creation** (Insufficient Stock)
```python
# User attempts: Buy 5000x @ 40M
# Market has: Only 2000x available
# Game action: Buy 2k, auto-create 3k preorder

balance_delta = -40_000_000  # Full price paid
warehouse_delta = 2000        # Partial received
requested_qty = 5000          # From user action

# Calculate split
purchase_qty = warehouse_delta  # 2000
preorder_qty = requested_qty - purchase_qty  # 3000

# Price splitting (proportional)
purchase_price = abs(balance_delta) * (purchase_qty / requested_qty)
# = 40M × (2000 / 5000) = 16M

preorder_price = abs(balance_delta) * (preorder_qty / requested_qty)
# = 40M × (3000 / 5000) = 24M

# Store TWO entries:
# 1. Transaction: 2000x @ 16M
# 2. Preorder: 3000x @ 24M (active)
```

**Case 4: Partial Fill + Auto-Preorder (MOST COMPLEX)**
```python
# Active preorder: 5000x @ 50M, filled=3000
# User attempts: Buy 4000x @ 40M
# Market has: Only 2000x available
# Game action: Collect 3k preorder + buy 2k + create 2k new preorder

balance_delta = -40_000_000  # Purchase price only (preorder already paid)
warehouse_delta = 5000        # 3k (preorder) + 2k (purchase)

# Step 1: Detect preorder auto-collect
preorder_match = find_matching_preorder('Pine Sap', warehouse_delta=5000)
# Match found: qty=5000, filled=3000, price=50M

preorder_qty_collected = 3000
preorder_contribution = 50_000_000 * (3000 / 5000)
# = 50M × 0.6 = 30M

# Step 2: Calculate actual purchase
actual_purchase_qty = warehouse_delta - preorder_qty_collected
# = 5000 - 3000 = 2000

# Step 3: Detect auto-preorder (shortage)
base_price = get_base_price('Pine Sap')  # e.g., 10,000
expected_purchase_qty = abs(balance_delta) / base_price
# = 40M / 10k = 4000

shortage_qty = expected_purchase_qty - actual_purchase_qty
# = 4000 - 2000 = 2000

# Step 4: Split balance_delta for purchase vs. new preorder
purchase_portion = actual_purchase_qty / expected_purchase_qty
# = 2000 / 4000 = 0.5

purchase_price = abs(balance_delta) * purchase_portion
# = 40M × 0.5 = 20M

new_preorder_price = abs(balance_delta) * (1 - purchase_portion)
# = 40M × 0.5 = 20M

# Step 5: Calculate final transaction total
transaction_total = preorder_contribution + purchase_price
# = 30M + 20M = 50M

# Store THREE entries:
# 1. Mark old preorder collected: 5000x @ 50M (filled=3000)
# 2. Transaction: 5000x @ 50M (3k preorder + 2k purchase)
# 3. New preorder: 2000x @ 20M (active, unfilled)
```

**Implementation in `_infer_transaction_from_deltas()`**:
```python
# Step 1: Check for preorder auto-collect FIRST
preorder_match = self.preorder_mgr.find_matching_preorder(
    item_name=item_name,
    warehouse_delta=warehouse_delta
)

preorder_contribution = 0
preorder_qty_collected = 0

if preorder_match:
    # Determine how much of preorder was collected
    preorder_qty = preorder_match['quantity']
    filled_qty = preorder_match.get('quantity_filled', preorder_qty)
    
    # Calculate contribution
    preorder_price = preorder_match['price']
    preorder_contribution = preorder_price * (filled_qty / preorder_qty)
    preorder_qty_collected = filled_qty
    
    log_debug(
        f"[PREORDER] Auto-collect detected: {item_name} "
        f"(preorder_filled={filled_qty}/{preorder_qty}, "
        f"contribution={preorder_contribution:,.0f})"
    )

# Step 2: Calculate actual purchase quantity (after preorder)
actual_purchase_qty = warehouse_delta - preorder_qty_collected

# Step 3: Check for auto-preorder creation (shortage detection)
base_price = self._get_base_price(item_name)
expected_purchase_qty = abs(balance_delta) / base_price if base_price else actual_purchase_qty

if actual_purchase_qty < expected_purchase_qty * 0.95:
    # Shortage detected! Auto-preorder was created
    shortage_qty = int(round(expected_purchase_qty - actual_purchase_qty))
    
    # Split balance_delta proportionally
    purchase_portion = actual_purchase_qty / expected_purchase_qty
    purchase_price = abs(balance_delta) * purchase_portion
    new_preorder_price = abs(balance_delta) * (1 - purchase_portion)
    
    # Store new preorder
    self._preorder_manager.store_preorder(
        item_name=item_name,
        quantity=shortage_qty,
        price=new_preorder_price,
        timestamp=datetime.now()
    )
    
    log_debug(
        f"[AUTO-PREORDER] Created: {item_name} x{shortage_qty} @ {new_preorder_price:,.0f} "
        f"(shortage from attempted {expected_purchase_qty:.0f})"
    )
else:
    # No shortage - use full balance_delta for purchase
    purchase_price = abs(balance_delta)

# Step 4: Calculate final transaction total
corrected_total = purchase_price + preorder_contribution

log_debug(
    f"[TRANSACTION] Total: {corrected_total:,.0f} "
    f"(purchase={purchase_price:,.0f} + preorder={preorder_contribution:,.0f})"
)
```

---

### Phase 6: Testing & Documentation (2-3 hours)
**Priority**: HIGH  
**Dependencies**: All previous phases

**Tasks**:
1. ⚠️ Write comprehensive unit tests (target: 90% coverage)
2. ⚠️ Write integration tests (end-to-end scenarios)
3. ⚠️ Manual testing with real game data
4. ⚠️ Update AGENTS.md with new feature
5. ⚠️ Write user documentation (README section)
6. ⚠️ Add troubleshooting guide

**Deliverables**:
- Full test suite in `tests/unit/test_preorder_*.py`
- Integration tests in `tests/integration/test_preorder_flow.py`
- Updated documentation in `docs/`
- User guide in `README.md`

**Acceptance Criteria**:
- All tests passing (0 failures)
- Code coverage ≥ 90% for preorder module
- Documentation complete and accurate

**REMOVED**: Periodic cleanup tasks - not needed

---

## 6. Testing Strategy

### 6.1 Unit Tests

#### test_preorder_manager.py
```python
def test_store_preorder():
    """Test storing a new preorder"""
    
def test_find_matching_preorder():
    """Test finding matching preorder by item/qty"""
    
def test_mark_collected():
    """Test marking preorder as collected"""
    
def test_expire_old_preorders():
    """Test automatic expiration"""
    
def test_cache_refresh():
    """Test cache invalidation and refresh"""
```

#### test_preorder_parsing.py
```python
def test_placed_order_detection():
    """Test 'Placed order' event parsing"""
    
def test_preorder_vs_regular_listing():
    """Test distinguishing preorders from regular listings"""
```

#### test_preorder_autocollect.py
```python
def test_autocollect_detection():
    """Test detecting auto-collect from deltas"""
    
def test_price_correction():
    """Test price correction calculation"""
    
def test_plausibility_check_after_correction():
    """Test that plausibility check works with corrected price"""
```

### 6.2 Integration Tests

#### test_preorder_flow.py
```python
def test_birch_sap_scenario():
    """
    Test complete flow:
    1. Parse 'Placed order' from log
    2. Store preorder
    3. Detect auto-collect in detail window
    4. Apply correction
    5. Save transaction
    6. Mark preorder collected
    """
    
def test_multiple_preorders():
    """Test handling multiple stacked preorders (FIFO)"""
    
def test_expired_preorder():
    """Test that expired preorders don't affect matching"""
```

### 6.3 Manual Test Cases

#### Test Case 1: Single Preorder Auto-Collect (PRIMARY TEST)
```
Setup:
1. Reset database (clean slate)
2. Start tracker, enable debug mode

Execute:
1. Open Buy Overview for Birch Sap
2. Click "Relist" → Detail-window opens
3. BASELINE CAPTURED: balance=158,959,294,080, warehouse=0
4. Set preorder: 5000x @ 58,000,000 Silver
5. PREORDER PLACEMENT DETECTED:
   - balance_delta = -58,000,000
   - warehouse_delta = 0
   - Preorder stored: Birch Sap x5,000 @ 58M (ID: 1)
   - Rolling baseline updated: balance=158,901,294,080, warehouse=0
6. Wait for preorder to fill (game shows "Filled")
7. Purchase 5000x @ 62,250,900 Silver
8. AUTO-COLLECT TRIGGERED:
   - balance_delta = -62,250,900 (vs. updated baseline!)
   - warehouse_delta = +10,000
   - Preorder matched: ID=1

Verify:
- Preorder stored: Birch Sap x5,000 @ 58M (status=active)
- Transaction saved: 10,000x @ 120,250,900 Silver
- Per-item price: 12,025 Silver/item
- Preorder updated: status=collected, collected_at=[timestamp]
- Rolling baseline: balance=158,838,793,180, warehouse=10,000
```

#### Test Case 2: Multiple Purchases After Preorder
```
Setup:
1. Reset database
2. Start tracker

Execute:
1. Open Buy Overview for Birch Sap
2. Click "Relist" → Detail-window opens
3. BASELINE: balance=X, warehouse=0
4. Set preorder: 5000x @ 58M
   - DETECTED: balance_delta=-58M, warehouse_delta=0
   - Rolling baseline: balance=X-58M, warehouse=0
5. Wait for fill
6. Purchase #1: 5000x @ 62,250,900
   - AUTO-COLLECT: balance_delta=-62.25M, warehouse_delta=+10k
   - Preorder matched
   - TX saved: 10,000x @ 120,250,900
   - Rolling baseline: balance=X-120.25M, warehouse=10k
7. Purchase #2: 5000x @ 62,500,000
   - REGULAR: balance_delta=-62.5M, warehouse_delta=+5k
   - No preorder match
   - TX saved: 5,000x @ 62,500,000
   - Rolling baseline: balance=X-182.75M, warehouse=15k
8. Exit detail window

Verify:
- Preorder: Birch Sap x5,000 @ 58M (collected)
- TX #1: 10,000x @ 120,250,900 (auto-collect)
- TX #2: 5,000x @ 62,500,000 (regular)
- Total: 3 database entries (1 preorder, 2 transactions)
```

#### Test Case 3: No Preorder (Regular Purchase - Control Test)
```
Setup:
- No active preorders for target item

Execute:
1. Open Buy Overview for any item (e.g., Maple Sap)
2. Click "Relist" → Detail-window opens
3. BASELINE: balance=Y, warehouse=0
4. Purchase 5000x @ 50M
   - balance_delta=-50M, warehouse_delta=+5k
   - No preorder detected (warehouse changed!)
   - No auto-collect (no matching preorder)
   - TX saved: 5,000x @ 50M
   - Rolling baseline: balance=Y-50M, warehouse=5k

Verify:
- No preorder stored
- Transaction saved with regular calculation: 5,000x @ 50M
- No false positive auto-collect detection
```

#### Test Case 4: Partial Preorder Fill + Purchase
```
Setup:
1. Reset database
2. Start tracker
3. Pre-create partial fill: Birch Sap preorder 5000x @ 58M with quantity_filled=3000

Execute:
1. Open Buy Overview for Birch Sap
2. Click "Relist" → Detail-window opens
3. BASELINE: balance=X, warehouse=0
4. Purchase 2000x @ 62M
5. AUTO-COLLECT TRIGGERED (partial):
   - balance_delta = -62M
   - warehouse_delta = +5000 (2k purchase + 3k preorder)
   - Preorder matched: ID=1 (qty=5000, filled=3000)
   - Calculate contribution: 58M × (3000/5000) = 34.8M
   - Corrected price: 62M + 34.8M = 96.8M
   - Rolling baseline updated

Verify:
- Preorder: Birch Sap x5,000 @ 58M (status=collected, quantity_filled=3000)
- Transaction: 5,000x @ 96,800,000 Silver
- Per-item price: 19,360 Silver/item
- Partial fill correctly accounted for in price correction
```

#### Test Case 5: Auto-Preorder Creation (Insufficient Stock)
```
Setup:
1. Reset database
2. Start tracker
3. Ensure market has limited stock (e.g., only 2000x available)

Execute:
1. Open Buy Overview for Birch Sap
2. Click "Relist" → Detail-window opens
3. BASELINE: balance=X, warehouse=0
4. Attempt to buy 5000x @ 40M (but only 2000x available)
5. AUTO-PREORDER DETECTED:
   - balance_delta = -40M (FULL price paid)
   - warehouse_delta = +2000 (PARTIAL received)
   - Detection: estimated_qty=5000 (from balance), received=2000
   - Split calculation:
     * Purchase: 2000x @ 16M (40M × 2/5)
     * Preorder: 3000x @ 24M (40M × 3/5)
   - Rolling baseline updated: balance=X-40M, warehouse=2000

Verify:
- Transaction: 2,000x @ 16,000,000 Silver
- Preorder: Birch Sap x3,000 @ 24,000,000 (status=active)
- Total entries: 2 (purchase + new preorder)
- Price split proportionally correct
```

#### Test Case 6: Partial Fill + Replacement
```
Setup:
1. Reset database
2. Start tracker
3. Pre-create partial fill: Maple Sap 5000x @ 50M with quantity_filled=2000

Execute:
1. Open Buy Overview for Maple Sap
2. Click "Relist" → Detail-window opens
3. BASELINE: balance=Z, warehouse=0
4. Set new preorder: 8000x @ 55M (replacing old)
5. REPLACEMENT DETECTED:
   - balance_delta = -55M
   - warehouse_delta = 0 (no purchase, just preorder)
   - Old preorder found: ID=1 (Maple Sap, filled=2000)
   - Old marked as collected (including partial fill info)
   - New stored: Maple Sap x8,000 @ 55M (ID=2, status=active)
   - Rolling baseline: balance=Z-55M, warehouse=0

Verify:
- Old preorder: Maple Sap x5,000 @ 50M (collected, quantity_filled=2000)
- New preorder: Maple Sap x8,000 @ 55M (active, quantity_filled=0)
- No transaction created (correct - just replacement)
- ONE active constraint enforced
```

#### Test Case 7: Preorder Replacement (New Preorder While Old Active)
```
Setup:
1. Reset database
2. Start tracker

Execute:
1. Open Buy Overview for Pine Sap
2. Click "Relist" → Detail-window opens
3. BASELINE: balance=Z, warehouse=0
4. Set preorder #1: 3000x @ 40M
   - DETECTED: balance_delta=-40M, warehouse_delta=0
   - Preorder stored: Pine Sap x3,000 @ 40M (ID: 1, status=active)
   - Rolling baseline: balance=Z-40M, warehouse=0
5. Set preorder #2: 5000x @ 50M (without closing window!)
   - DETECTED: balance_delta=-50M, warehouse_delta=0
   - OLD PREORDER AUTO-COLLECTED: ID=1 marked as collected
   - NEW PREORDER STORED: Pine Sap x5,000 @ 50M (ID: 2, status=active)
   - Rolling baseline: balance=Z-90M, warehouse=0
6. Exit detail-window

Verify:
- Preorder #1: Pine Sap x3,000 @ 40M (status=collected, collected_at=[timestamp])
- Preorder #2: Pine Sap x5,000 @ 50M (status=active)
- Database enforces unique constraint: only 1 active per item
- No transactions created (correct - no purchases)
```

#### Test Case 8: Preorder Cancellation
```
Setup:
1. Reset database
2. Start tracker

Execute:
1. Open Buy Overview for Maple Sap
2. Click "Relist" → Detail-window opens
3. Set preorder: 4000x @ 35M
   - DETECTED: balance_delta=-35M, warehouse_delta=0
   - Preorder stored: Maple Sap x4,000 @ 35M (ID: 3, status=active)
4. Cancel preorder in game (Withdraw button)
5. Exit detail-window → Return to overview
6. Transaction log shows: "Withdrew order of Maple Sap x4,000 for 35,000,000 Silver"
7. DETECTED: type='withdrew', item='Maple Sap', qty=4000, price=35M
8. Preorder cancelled: ID=3 marked as cancelled

Verify:
- Preorder: Maple Sap x4,000 @ 35M (status=cancelled)
- No transaction created (correct - just cancellation)
- Log parsing correctly identified withdraw event
```

#### Test Case 9: Partial Fill + Auto-Preorder on Shortage (COMPLEX EDGE CASE)
```
Setup:
1. Reset database
2. Start tracker
3. Pre-create partial fill: Pine Sap 5000x @ 50M with quantity_filled=3000
4. Ensure market has limited stock (only 2000x available)

Execute:
1. Open Buy Overview for Pine Sap
2. Click "Relist" → Detail-window opens
3. BASELINE: balance=X, warehouse=0
4. Attempt to buy 4000x @ 40M (but only 2000x available)
5. COMPLEX DETECTION:
   - balance_delta = -40M (full price)
   - warehouse_delta = +5000 (3k preorder + 2k purchase)
   
   Detection Chain:
   a) Check preorder auto-collect:
      → Match found: Pine Sap 5000x @ 50M, filled=3000
      → Preorder contribution: 3000x
   
   b) Calculate actual purchase:
      → warehouse_delta - preorder_qty = 5000 - 3000 = 2000
      → balance_delta implies: 40M / base_price = 4000x intended
      → Shortage detected: 4000 - 2000 = 2000x
   
   c) Auto-preorder creation:
      → New preorder: 2000x @ 20M (40M × 2000/4000)
   
   d) Price correction:
      → Preorder: 50M × (3000/5000) = 30M
      → Purchase: 40M × (2000/4000) = 20M
      → Total: 50M for 5000x
   
6. Rolling baseline updated

Verify:
- Old preorder: Pine Sap x5,000 @ 50M (collected, quantity_filled=3000)
- Transaction: 5,000x @ 50,000,000 Silver (3k preorder + 2k purchase)
- New preorder: Pine Sap x2,000 @ 20,000,000 (active, quantity_filled=0)
- Total entries: 3 (old preorder collected, transaction, new preorder)
- Price calculation correct despite TWO complex features in one transaction
- Per-item price: 10,000 Silver/item (reasonable)
```

---

## 7. Risk Analysis & Mitigation

### Risk 1: Complex Scenario Detection Failure (NEW - CRITICAL)
**Impact**: CRITICAL  
**Probability**: MEDIUM

**Scenario**: Partial fill + auto-preorder in same transaction fails to detect correctly.

**Example**: User has partial preorder (3k filled), tries to buy 4k, only 2k available.
- If detection chain is wrong: Transaction price incorrect, new preorder not created
- If order is wrong: Could double-count quantities or miss shortage

**Mitigation**:
- **STRICT DETECTION ORDER**: Always check preorder auto-collect FIRST
- Subtract preorder qty from warehouse_delta BEFORE shortage detection
- Use adjusted purchase qty for auto-preorder calculation
- Log each step in detection chain for debugging
- Add integration test specifically for this scenario (Test Case 9)

**Detection Chain Validation**:
```python
# CORRECT order:
1. preorder_match = find_matching_preorder()
2. actual_purchase_qty = warehouse_delta - preorder_qty_collected
3. expected_purchase_qty = balance_delta / base_price
4. if actual < expected: auto_preorder_created = True
5. corrected_total = purchase_price + preorder_contribution
```

**Fallback**:
- If detection chain fails, log detailed error with all intermediate values
- Fallback to simpler detection (either preorder OR auto-preorder, not both)
- Manual UI correction via Preorder Management tab

---

### Risk 2: False Positive Auto-Collect Detection
**Impact**: HIGH  
**Probability**: MEDIUM

**Scenario**: Regular purchase falsely detected as preorder auto-collect.

**Mitigation**:
- Strict matching criteria (item name + quantity alignment)
- Require warehouse_delta > estimated_purchase_qty * 1.1
- Log all detection decisions for debugging
- Add plausibility check AFTER correction

**Fallback**:
- If correction causes plausibility check to fail, reject correction and save original

---

### Risk 2: Missed Preorder Placement
**Impact**: MEDIUM  
**Probability**: LOW

**Scenario**: Preorder placement not detected in detail-window (metrics not updated yet).

**Mitigation**:
- **Primary**: Detail-window detection (balance↓, warehouse=0)
- **Fallback**: Transaction log parsing after window close
- Duplicate check prevents double-storage
- Manual preorder entry (future enhancement)

**Fallback**:
- Transaction log will show "Placed order" event
- If detail-window detection missed it, log parsing will catch it
- User can manually correct transaction price after auto-collect (DB edit)

---

### Risk 3: Performance Degradation
**Impact**: MEDIUM  
**Probability**: LOW

**Scenario**: Preorder lookup slows down scan loop.

**Mitigation**:
- In-memory cache for active preorders
- Database indexes on item_name + status
- Limit cache refresh to once per minute
- Measure performance with benchmarks

**Acceptance Criteria**:
- Preorder lookup < 5ms per call
- No increase in average scan time

---

### Risk 4: Database Migration Failure
**Impact**: HIGH  
**Probability**: LOW

**Scenario**: Migration breaks existing database.

**Mitigation**:
- Test migration on backup database first
- Implement rollback mechanism
- Schema change is additive (no modifications to existing tables)
- Provide migration verification script

**Rollback Plan**:
```python
# Drop preorders table if migration fails
cursor.execute("DROP TABLE IF EXISTS preorders")
```

---

### Risk 5: Preorder Replacement Not Detected
**Impact**: MEDIUM  
**Probability**: LOW

**Scenario**: User sets new preorder while old one still active, but replacement not detected.

**Mitigation**:
- Database unique constraint enforces ONE active per item
- If constraint violated, exception logged and old preorder force-collected
- Rolling baseline update ensures correct deltas for subsequent transactions

**Fallback**:
- Database constraint prevents corruption (INSERT will fail)
- Log error and retry with explicit old preorder collection

---

## 8. Configuration & Tuning Parameters

### Preorder Matching
- `PREORDER_QUANTITY_TOLERANCE`: 1.1 (10% over-detection threshold for auto-collect)

### Cache Management
- `PREORDER_CACHE_TTL_SECONDS`: 60
- `PREORDER_MAX_CACHE_SIZE`: 1000

### Logging
- `PREORDER_DEBUG_LOGGING`: True (in debug mode)
- `PREORDER_LOG_PREFIX`: "[PREORDER]"

**REMOVED** (not applicable):
- ~~PREORDER_MATCH_TOLERANCE_MINUTES~~ (no time tolerance - preorders never expire)
- ~~PREORDER_MAX_AGE_DAYS~~ (no expiration)
- ~~PREORDER_CLEANUP_INTERVAL_SCANS~~ (no periodic cleanup)

### Partial Fill Detection
- `PARTIAL_FILL_MIN_PERCENTAGE`: 0.1 (minimum 10% of total to be considered significant)
- `AUTO_PREORDER_TOLERANCE`: 0.05 (5% tolerance for rounding in auto-preorder detection)

---

## 9. Preorder Management UI (MVP Feature)

### 9.1 Overview
**CRITICAL REQUIREMENT**: Users must be able to manage preorders manually, especially when preorders were placed/collected while the application was offline.

**Use Cases**:
1. **Offline Preorder Placement**: User set preorder while app was closed → Add manually when app starts
2. **Offline Auto-Collect**: Preorder was collected while app was offline → Mark as collected manually
3. **OCR Miss**: App failed to detect preorder placement → Add manually
4. **Correction**: Wrong quantity/price detected → Edit existing preorder
5. **Cleanup**: Orphaned/invalid preorders → Delete manually
6. **Overview**: View all active/collected/cancelled preorders

### 9.2 UI Design (Tkinter Implementation)

#### Location: New Tab in Main GUI
Add "Preorders" tab next to "History" tab in main window.

#### Layout Structure
```
┌─────────────────────────────────────────────────────────────┐
│  Preorders                                                   │
├─────────────────────────────────────────────────────────────┤
│  Filter: [All ▼]  [Active]  [Collected]  [Cancelled]        │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Item Name    │ Qty  │ Filled│ Price      │ Status │ Date││
│  ├─────────────────────────────────────────────────────────┤│
│  │ Birch Sap    │ 5000 │ 3000  │ 58,000,000 │ Active │ 10/20││
│  │ Pine Sap     │ 3000 │ 3000  │ 45,000,000 │ Collect│ 10/19││
│  │ Maple Sap    │ 2000 │ 0     │ 30,000,000 │ Cancel │ 10/18││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  [Add Preorder] [Edit] [Delete] [Mark Collected] [Refresh]  │
│                                                              │
│  Selected: Birch Sap x5,000 @ 58M (3000/5000 filled)        │
└─────────────────────────────────────────────────────────────┘
```

#### 9.2.1 Add Preorder Dialog
```
┌─────────────────────────────────────────┐
│  Add Preorder                           │
├─────────────────────────────────────────┤
│  Item Name: [___Birch Sap____________]  │
│             [Search in market.json]     │
│                                         │
│  Quantity:  [___5000_________________]  │
│                                         │
│  Price:     [___58000000_____________]  │
│             (Total price paid)          │
│                                         │
│  Date/Time: [2025-10-20 14:30:00____]  │
│             [Use Current Time]          │
│                                         │
│  Status:    [Active ▼]                  │
│                                         │
│  [Save]  [Cancel]                       │
└─────────────────────────────────────────┘
```

#### 9.2.2 Edit Preorder Dialog
```
┌─────────────────────────────────────────┐
│  Edit Preorder #42                      │
├─────────────────────────────────────────┤
│  Item Name: Birch Sap (read-only)       │
│                                         │
│  Quantity:  [___5000_________________]  │
│             (Total ordered)             │
│                                         │
│  Filled:    [___3000_________________]  │
│             (Partial fill tracking)     │
│                                         │
│  Price:     [___58000000_____________]  │
│             (Total price paid)          │
│                                         │
│  Status:    [Active ▼]                  │
│             [Active/Collected/Cancelled]│
│                                         │
│  Date:      2025-10-20 14:30:00         │
│             (Original timestamp)        │
│                                         │
│  [Save]  [Cancel]                       │
└─────────────────────────────────────────┘
```

### 9.3 PreorderManager API Extensions

Add new methods to `PreorderManager` class:

```python
def update_preorder(
    self,
    preorder_id: int,
    quantity: Optional[int] = None,
    quantity_filled: Optional[int] = None,
    price: Optional[float] = None,
    status: Optional[str] = None
) -> bool:
    """
    Update an existing preorder.
    
    Args:
        preorder_id: ID of preorder to update
        quantity: New total quantity (optional)
        quantity_filled: New filled quantity (optional)
        price: New total price (optional)
        status: New status (optional)
        
    Returns:
        True if update successful, False otherwise
    """
    try:
        cur = get_cursor()
        
        # Build dynamic UPDATE query
        updates = []
        params = []
        
        if quantity is not None:
            updates.append("quantity = ?")
            params.append(quantity)
        
        if quantity_filled is not None:
            updates.append("quantity_filled = ?")
            params.append(quantity_filled)
        
        if price is not None:
            updates.append("price = ?")
            params.append(price)
        
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        
        if not updates:
            return False  # Nothing to update
        
        updates.append("updated_at = CURRENT_TIMESTAMP")
        
        params.append(preorder_id)
        query = f"UPDATE preorders SET {', '.join(updates)} WHERE id = ?"
        
        cur.execute(query, params)
        
        # Invalidate cache
        self.invalidate_cache()
        
        if self.debug:
            log_debug(f"[PREORDER] Updated preorder ID={preorder_id}")
        
        return True
    
    except Exception as e:
        if self.debug:
            log_debug(f"[PREORDER] ERROR updating: {e}")
        return False

def delete_preorder(self, preorder_id: int) -> bool:
    """
    Delete a preorder (use with caution - prefer marking as cancelled).
    
    Args:
        preorder_id: ID of preorder to delete
        
    Returns:
        True if deletion successful, False otherwise
    """
    try:
        cur = get_cursor()
        cur.execute("DELETE FROM preorders WHERE id = ?", (preorder_id,))
        
        # Invalidate cache
        self.invalidate_cache()
        
        if self.debug:
            log_debug(f"[PREORDER] Deleted preorder ID={preorder_id}")
        
        return True
    
    except Exception as e:
        if self.debug:
            log_debug(f"[PREORDER] ERROR deleting: {e}")
        return False

def get_all_preorders(
    self,
    status_filter: Optional[str] = None,
    limit: int = 100
) -> List[Dict]:
    """
    Retrieve preorders for UI display.
    
    Args:
        status_filter: Filter by status ('active', 'collected', 'cancelled', None=all)
        limit: Maximum results to return
        
    Returns:
        List of preorder dicts sorted by timestamp DESC
    """
    try:
        cur = get_cursor()
        
        if status_filter:
            query = """
                SELECT id, item_name, quantity, quantity_filled, price, 
                       timestamp, status, collected_at, created_at
                FROM preorders
                WHERE status = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            cur.execute(query, (status_filter, limit))
        else:
            query = """
                SELECT id, item_name, quantity, quantity_filled, price, 
                       timestamp, status, collected_at, created_at
                FROM preorders
                ORDER BY timestamp DESC
                LIMIT ?
            """
            cur.execute(query, (limit,))
        
        rows = cur.fetchall()
        
        return [
            {
                'id': row[0],
                'item_name': row[1],
                'quantity': row[2],
                'quantity_filled': row[3],
                'price': row[4],
                'timestamp': row[5],
                'status': row[6],
                'collected_at': row[7],
                'created_at': row[8]
            }
            for row in rows
        ]
    
    except Exception as e:
        if self.debug:
            log_debug(f"[PREORDER] ERROR fetching all: {e}")
        return []
```

### 9.4 GUI Implementation (gui.py)

Add new tab and handlers:

```python
# In MainWindow.__init__() after history tab:

# Preorders Tab (NEW)
self.preorders_frame = ttk.Frame(self.notebook)
self.notebook.add(self.preorders_frame, text="Preorders")

self._setup_preorders_tab()

def _setup_preorders_tab(self):
    """Setup preorders management UI."""
    # Filter controls
    filter_frame = ttk.Frame(self.preorders_frame)
    filter_frame.pack(fill=tk.X, padx=5, pady=5)
    
    ttk.Label(filter_frame, text="Filter:").pack(side=tk.LEFT, padx=5)
    
    self.preorder_filter_var = tk.StringVar(value="All")
    filter_combo = ttk.Combobox(
        filter_frame,
        textvariable=self.preorder_filter_var,
        values=["All", "Active", "Collected", "Cancelled"],
        state="readonly",
        width=15
    )
    filter_combo.pack(side=tk.LEFT, padx=5)
    filter_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_preorders())
    
    # Preorders treeview
    tree_frame = ttk.Frame(self.preorders_frame)
    tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    columns = ("Item", "Qty", "Filled", "Price", "Status", "Date")
    self.preorders_tree = ttk.Treeview(
        tree_frame,
        columns=columns,
        show="headings",
        height=15
    )
    
    # Column headers
    self.preorders_tree.heading("Item", text="Item Name")
    self.preorders_tree.heading("Qty", text="Quantity")
    self.preorders_tree.heading("Filled", text="Filled")
    self.preorders_tree.heading("Price", text="Price")
    self.preorders_tree.heading("Status", text="Status")
    self.preorders_tree.heading("Date", text="Date")
    
    # Column widths
    self.preorders_tree.column("Item", width=200)
    self.preorders_tree.column("Qty", width=80)
    self.preorders_tree.column("Filled", width=80)
    self.preorders_tree.column("Price", width=120)
    self.preorders_tree.column("Status", width=80)
    self.preorders_tree.column("Date", width=100)
    
    # Scrollbar
    scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.preorders_tree.yview)
    self.preorders_tree.configure(yscrollcommand=scrollbar.set)
    
    self.preorders_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    # Action buttons
    button_frame = ttk.Frame(self.preorders_frame)
    button_frame.pack(fill=tk.X, padx=5, pady=5)
    
    ttk.Button(button_frame, text="Add Preorder", command=self._add_preorder).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Edit", command=self._edit_preorder).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Delete", command=self._delete_preorder).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Mark Collected", command=self._mark_collected).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Refresh", command=self._refresh_preorders).pack(side=tk.LEFT, padx=5)
    
    # Selection label
    self.preorder_selection_label = ttk.Label(self.preorders_frame, text="No selection")
    self.preorder_selection_label.pack(fill=tk.X, padx=5, pady=5)
    
    # Bind selection event
    self.preorders_tree.bind("<<TreeviewSelect>>", self._on_preorder_select)
    
    # Initial load
    self._refresh_preorders()

def _refresh_preorders(self):
    """Reload preorders from database."""
    # Clear tree
    for item in self.preorders_tree.get_children():
        self.preorders_tree.delete(item)
    
    # Get filter
    filter_value = self.preorder_filter_var.get()
    status_filter = None if filter_value == "All" else filter_value.lower()
    
    # Load from PreorderManager
    from preorder_manager import PreorderManager
    mgr = PreorderManager(debug=False)
    preorders = mgr.get_all_preorders(status_filter=status_filter)
    
    # Populate tree
    for po in preorders:
        self.preorders_tree.insert(
            "",
            tk.END,
            values=(
                po['item_name'],
                f"{po['quantity']:,}",
                f"{po['quantity_filled']:,}",
                f"{po['price']:,.0f}",
                po['status'].capitalize(),
                po['timestamp'][:10] if po['timestamp'] else ""
            ),
            tags=(str(po['id']),)  # Store ID in tags
        )

def _on_preorder_select(self, event):
    """Update selection label when preorder selected."""
    selection = self.preorders_tree.selection()
    if not selection:
        self.preorder_selection_label.config(text="No selection")
        return
    
    item = self.preorders_tree.item(selection[0])
    values = item['values']
    
    self.preorder_selection_label.config(
        text=f"Selected: {values[0]} x{values[1]} @ {values[3]} ({values[2]}/{values[1]} filled)"
    )

def _add_preorder(self):
    """Open dialog to add new preorder."""
    # TODO: Implement AddPreorderDialog
    messagebox.showinfo("Add Preorder", "Dialog implementation in progress")

def _edit_preorder(self):
    """Open dialog to edit selected preorder."""
    selection = self.preorders_tree.selection()
    if not selection:
        messagebox.showwarning("No Selection", "Please select a preorder to edit")
        return
    
    # TODO: Implement EditPreorderDialog
    messagebox.showinfo("Edit Preorder", "Dialog implementation in progress")

def _delete_preorder(self):
    """Delete selected preorder."""
    selection = self.preorders_tree.selection()
    if not selection:
        messagebox.showwarning("No Selection", "Please select a preorder to delete")
        return
    
    item = self.preorders_tree.item(selection[0])
    preorder_id = int(item['tags'][0])
    item_name = item['values'][0]
    
    # Confirm deletion
    result = messagebox.askyesno(
        "Confirm Delete",
        f"Delete preorder for {item_name}?\n\nThis action cannot be undone."
    )
    
    if result:
        from preorder_manager import PreorderManager
        mgr = PreorderManager(debug=False)
        if mgr.delete_preorder(preorder_id):
            messagebox.showinfo("Success", "Preorder deleted")
            self._refresh_preorders()
        else:
            messagebox.showerror("Error", "Failed to delete preorder")

def _mark_collected(self):
    """Mark selected preorder as collected."""
    selection = self.preorders_tree.selection()
    if not selection:
        messagebox.showwarning("No Selection", "Please select a preorder to mark as collected")
        return
    
    item = self.preorders_tree.item(selection[0])
    preorder_id = int(item['tags'][0])
    item_name = item['values'][0]
    
    # Confirm
    result = messagebox.askyesno(
        "Confirm Collection",
        f"Mark preorder for {item_name} as collected?"
    )
    
    if result:
        from preorder_manager import PreorderManager
        from datetime import datetime
        mgr = PreorderManager(debug=False)
        if mgr.mark_collected(preorder_id, datetime.now()):
            messagebox.showinfo("Success", "Preorder marked as collected")
            self._refresh_preorders()
        else:
            messagebox.showerror("Error", "Failed to update preorder")
```

### 9.5 Implementation Priority

This feature is **HIGH PRIORITY** because:
1. **Offline Gap Coverage**: Only way to handle preorders placed/collected while app was closed
2. **Error Correction**: OCR failures can be manually fixed
3. **User Control**: Direct visibility and control over tracked state

**Implementation Phase**: Add as **Phase 7** after core preorder tracking works.

---

## 10. Future Enhancements

### Enhancement 1: Export Preorder Data
Include preorder data in CSV/JSON exports.

### Enhancement 2: Partial Fill Progress Indicator
Visual indicator showing fill progress (e.g., progress bar "3000/5000 filled").

### Enhancement 3: Preorder Alerts
Desktop notifications when preorder filled (requires polling game state).

### Enhancement 4: Bulk Operations
Select multiple preorders and mark as collected/cancelled in batch.

**REMOVED ENHANCEMENTS** (not applicable):
- ~~Multi-Stage Auto-Collect~~ (only ONE active preorder per item)

---

## 11. Success Criteria

### Must-Have (MVP)
- ✅ Preorders stored when detected in detail-window (balance↓, warehouse=0)
- ✅ Only ONE active preorder per item (enforced by database constraint)
- ✅ Old preorder auto-collected when new one placed for same item
- ✅ Auto-collect detected when warehouse_delta exceeds expectation
- ✅ Price correction applied correctly (including partial fills)
- ✅ Partial preorder fills tracked via `quantity_filled` column
- ✅ Auto-preorder creation detected (insufficient stock scenario)
- ✅ Preorder marked as collected after transaction
- ✅ Preorder cancellation detected from "Withdrew order" log entries
- ✅ Birch Sap test case passes (correct total: 120,250,900)
- ✅ **Preorder Management UI**: Add/Edit/Delete/Mark Collected functionality

### Should-Have
- ⚠️ Partial fill + purchase scenario tested (Test Case 4)
- ⚠️ Auto-preorder creation tested (Test Case 5)
- ⚠️ Preorder replacement scenario tested and working
- ⚠️ Cancellation detection robust (match by item+qty+price)
- ⚠️ Comprehensive error handling
- ⚠️ **Manual preorder entry for offline gaps**
- ⚠️ **Filter/search in preorder UI**

### Nice-to-Have
- ❌ Preorder progress indicator (visual fill percentage)
- ❌ Export preorder data (CSV/JSON)
- ❌ Preorder alerts/notifications
- ❌ Bulk operations on preorders

**REMOVED** (not applicable):
- ~~Multiple preorders (FIFO matching)~~ (only ONE active per item)
- ~~Old preorders automatically expired~~ (no expiration)

---

## 12. Open Questions

1. **Q**: Should preorders be displayed in GUI history view?  
   **A**: Phase 2 enhancement, not MVP.

2. **Q**: What happens if user rapidly changes preorders (multiple replacements)?  
   **A**: Each replacement marks previous as collected. All tracked correctly via rolling baseline.

3. **Q**: Should we validate preorder price against market price?  
   **A**: No - preorder price can be above/below market (user's choice).

4. **Q**: What if "Withdrew order" log entry is missed (user closes window before log visible)?  
   **A**: Preorder remains active indefinitely (no harm). Next placement will auto-collect it. Consider manual cleanup tool for orphaned preorders.

5. **Q**: Database constraint violation handling when trying to insert second active preorder?  
   **A**: Should never happen (we check and collect old one first). If it does, log error and force-collect old one.

6. **Q**: How to handle partial fills that accumulate over time (e.g., 1k filled today, 2k more tomorrow)?  
   **A**: Track cumulative `quantity_filled`. When auto-collecting, use total filled amount for price calculation.

7. **Q**: What if auto-preorder creation fails (e.g., price fluctuates between attempt and execution)?  
   **A**: Detection uses ±5% tolerance. If still fails, fallback to regular transaction (conservative approach).

8. **Q**: Should partial fills trigger notifications?  
   **A**: Future enhancement. Current implementation only tracks for price correction purposes.

9. **Q**: What happens when partial fill + auto-preorder occur in SAME transaction?  
   **A**: CRITICAL SCENARIO. Detection chain must run in order: (1) Check preorder auto-collect, (2) Subtract preorder qty, (3) Check shortage, (4) Create new preorder if needed. Test Case 9 validates this scenario. Manual UI correction available if detection fails.

10. **Q**: How to debug complex detection failures (partial fill + auto-preorder)?  
    **A**: Enable debug logging. Each step logs intermediate values (preorder_qty_collected, actual_purchase_qty, expected_purchase_qty, shortage_qty). Use Test Case 9 as reference for expected behavior.

**RESOLVED**:
- ~~Should preorders expire?~~ **NO** - they remain active indefinitely
- ~~Multiple preorders for same item?~~ **NO** - only ONE active per item
- ~~Partial fills?~~ **YES** - supported via `quantity_filled` column (v2.0 update)
- ~~Auto-preorder creation?~~ **YES** - detected via warehouse/balance delta mismatch (v2.0 update)
- ~~Partial fill + auto-preorder combination?~~ **YES** - Scenario 5 + Test Case 9 document this (v2.0 final update)

---

## 12. Implementation Checklist

### Pre-Implementation
- [x] Review AGENTS.md for compliance
- [x] Analyze existing codebase structure
- [x] Design database schema
- [x] Design PreorderManager API
- [x] Create detailed implementation plan (this document)

### Phase 1: Database & Core Module
- [ ] Create `preorder_manager.py`
- [ ] Implement PreorderManager class
- [ ] Add database migration in `database.py`
- [ ] Write unit tests
- [ ] Verify performance (< 5ms lookups)

### Phase 2: Log Parsing Integration
- [ ] Add `_handle_preorder_placement()` to tracker.py
- [ ] Integrate with `process_ocr_text()`
- [ ] Test with existing parsing tests
- [ ] Add preorder-specific tests

### Phase 3: Detail-Window Integration
- [ ] Implement `_check_for_preorder_autocollect()`
- [ ] Modify `_monitor_detail_window()`
- [ ] Update `_infer_transaction_from_deltas()`
- [ ] Update all call sites
- [ ] Add preorder marking logic
- [ ] Manual test with Birch Sap

### Phase 4: Transaction Storage Enhancement
- [ ] Modify `store_transaction_db()` return value
- [ ] Update call sites
- [ ] Add transaction linking

### Phase 5: Edge Cases & Robustness
- [ ] Test partial fill + purchase scenario (Test Case 4)
- [ ] Test auto-preorder creation (Test Case 5)
- [ ] Test partial fill + replacement (Test Case 6)
- [ ] **Test partial fill + auto-preorder combo (Test Case 9)** ⭐ CRITICAL
- [ ] Test preorder replacement scenario
- [ ] Test auto-collect on replacement
- [ ] Add comprehensive error handling
- [ ] Test edge cases (rapid replacements, etc.)
- [ ] Validate detection chain order (preorder → shortage → combine)

### Phase 6: Testing & Documentation
- [ ] Complete unit tests (90% coverage)
- [ ] Integration tests
- [ ] Manual testing (8 test cases)
- [ ] Update AGENTS.md
- [ ] Update README.md
- [ ] Write troubleshooting guide

### Phase 7: Preorder Management UI (HIGH PRIORITY)
- [ ] Add "Preorders" tab to main GUI
- [ ] Implement preorders treeview with filter
- [ ] Add PreorderManager API extensions:
  - [ ] `update_preorder()`
  - [ ] `delete_preorder()`
  - [ ] `get_all_preorders()`
- [ ] Create Add Preorder dialog
- [ ] Create Edit Preorder dialog
- [ ] Implement Delete confirmation
- [ ] Implement Mark Collected action
- [ ] Test manual preorder lifecycle (add → edit → collect)
- [ ] Test offline gap scenario (manually add missed preorder)

---

## 13. Estimated Effort

**Total Estimated Time**: 15-21 hours (updated for partial fills + auto-preorder + UI)

| Phase | Estimated Time |
|-------|----------------|
| Phase 1: Database & Core Module | 2-3 hours |
| Phase 2: Detail-Window Preorder Detection | 2-3 hours |
| Phase 2b: Log Parsing for Cancellation | 1 hour |
| Phase 3: Auto-Collect Detection & Correction | 3-4 hours (+1h for partial fills) |
| Phase 4: Transaction Storage Enhancement | 1 hour |
| Phase 5: Edge Cases & Robustness | 2-3 hours (+1h for new scenarios) |
| Phase 6: Testing & Documentation | 2-3 hours |
| **Phase 7: Preorder Management UI** | **3-4 hours** (NEW) |

**Critical Path**: Phase 1 → Phase 2 → Phase 3 → Phase 7  
**Minimum Viable Product**: Phases 1-3 only (7-10 hours, NO UI)  
**Recommended MVP**: Phases 1-3 + Phase 7 (10-14 hours, WITH UI for offline gaps)

**Time Adjustments (v2.0 Final + UI)**:
- **+1 hour** Phase 3: Partial fill price calculation logic
- **+1 hour** Phase 3: Auto-preorder detection & splitting
- **+1 hour** Phase 5: Additional test scenarios (partial fills, auto-preorder)
- **+3-4 hours** Phase 7: Preorder management UI (NEW)
- **Total increase**: ~6-7 hours over original simplified estimate

**Phase 7 Breakdown** (Preorder UI):
- **1 hour**: PreorderManager API extensions (update/delete/get_all methods)
- **1.5 hours**: GUI tab + treeview + filter controls
- **0.5 hours**: Add/Edit dialogs (simple forms)
- **0.5 hours**: Delete/Mark Collected actions
- **0.5 hours**: Testing + polish

**Complexity Breakdown**:
- **Core preorder tracking**: 6-9 hours (MVP without UI)
- **Partial fill support**: +2 hours
- **Auto-preorder detection**: +1 hour
- **Preorder Management UI**: +3-4 hours (CRITICAL for offline gaps)
- **Testing & edge cases**: +3-5 hours
- **Total**: 15-21 hours

---

## 14. Conclusion

This implementation plan provides a comprehensive roadmap for adding preorder tracking to the BDO Market Tracker. The design follows the existing architectural patterns (state management, database layer separation, error handling) and integrates cleanly with the current codebase.

**Key Design Principles**:
1. **Separation of Concerns**: PreorderManager handles all preorder logic
2. **Performance First**: In-memory caching keeps lookups fast
3. **Robustness**: Graceful error handling, no crashes on edge cases
4. **Maintainability**: Clear logging, comprehensive tests
5. **Backward Compatibility**: No breaking changes to existing features
6. **User Control**: Manual preorder management UI for offline gap coverage

**v2.0 Final Updates (2025-01-21)**:
- ✅ **Partial Preorder Fills**: Track via `quantity_filled` column, calculate proportional price contribution
- ✅ **Auto-Preorder Creation**: Detect insufficient stock, split transaction into purchase + new preorder
- ✅ **Enhanced Test Coverage**: 9 comprehensive test cases covering all scenarios
- ✅ **Price Correction Algorithms**: Documented for full/partial auto-collect, auto-preorder, AND combined scenario
- ✅ **Preorder Management UI**: Add/Edit/Delete/Mark Collected with filter (Phase 7)
- ✅ **Complex Edge Case**: Partial fill + auto-preorder in SAME transaction (Scenario 5 + Test Case 9)
- ✅ **Time Estimate Updated**: 15-21 hours total (10-14 hours recommended MVP with UI)

**Critical Success Factor**:
The **Preorder Management UI** (Phase 7) is ESSENTIAL because:
- OCR may miss preorder placements
- Preorders set while app was offline need manual entry
- Users need visibility and control over tracked state
- Errors/corrections must be possible without DB manipulation

**Most Complex Scenario** (NEW):
Partial fill + auto-preorder in SAME transaction requires strict detection chain:
1. Check preorder auto-collect FIRST
2. Subtract preorder qty from warehouse_delta
3. Calculate actual purchase vs. expected
4. Detect shortage and create new preorder if needed
5. Combine preorder contribution + purchase price
Test Case 9 validates this critical path.

**Next Steps**:
1. Review this plan with stakeholders
2. Begin Phase 1 implementation (database + core module)
3. Iterate through phases with testing after each
4. Deploy MVP (Phases 1-3) for automated tracking
5. **Add Phase 7 (UI) for manual management** (HIGH PRIORITY for offline gaps)
6. Gather feedback and prioritize remaining enhancements

---

**Document Status**: READY FOR IMPLEMENTATION ✅  
**Version**: 2.0 Final + UI + Complex Edge Case  
**Last Updated**: 2025-01-21  
**Total Pages**: ~100 (expanded from 95 with combined scenario documentation)

**Key Additions in Final Update**:
- ⭐ **Scenario 5**: Partial Fill + Auto-Preorder combination (most complex)
- ⭐ **Test Case 9**: Validates combined scenario with detailed verification
- ⭐ **Detection Chain Logic**: Step-by-step implementation guide for complex cases
- ⭐ **Risk #1 (NEW)**: Complex scenario detection failure mitigation
- ⭐ **Price Algorithm Case 4**: Mathematical breakdown for combined scenario


