# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

**BDO Market Tracker** - OCR-based market transaction tracker for Black Desert Online with automated transaction detection, live API integration, GPU acceleration, and persistent baseline. Version 0.2.4, BETA status.

## Common Commands

### Setup & Installation
```powershell
# Install dependencies
pip install -r requirements.txt

# Prerequisites (must be installed separately):
# - Tesseract-OCR (C:\Program Files\Tesseract-OCR\tesseract.exe)
# - CUDA Toolkit + cuDNN (optional, for GPU acceleration)
```

### Running the Application
```powershell
# Start GUI (main entry point)
python gui.py

# Single scan test
python tracker.py  # MarketTracker.single_scan()
```

### Testing
```powershell
# Run all tests (29/32 tests passing)
python scripts/run_all_tests.py

# Run specific tests
python scripts/test_exact_user_scenario.py
python scripts/test_integration.py
python scripts/test_window_detection.py
python scripts/test_item_validation.py
python scripts/test_parsing_crystal.py

# Performance benchmarks
python scripts/benchmark_performance.py
```

### Database Operations
```powershell
# Check database contents
python check_db.py

# Reset database (WARNING: deletes all data)
python scripts/utils/reset_db.py

# Deduplicate database
python scripts/utils/dedupe_db.py

# Fix database issues
python fix_db.py
```

### OCR & Debugging
```powershell
# Compare OCR methods (EasyOCR vs Tesseract)
python scripts/utils/compare_ocr.py

# Calibrate screen region
python scripts/utils/calibrate_region.py

# Debug window detection
python scripts/utils/debug_window.py

# Direct parsing test
python test_parsing_direct.py
```

### API Testing
```powershell
# Test BDO World Market API
python scripts/test_bdo_api.py

# Test Garmoth API integration
python scripts/test_garmoth_api.py
```

## High-Level Architecture

### Core Processing Flow
1. **Screenshot Capture** (`utils.py::capture_region`) → captures game window region via `mss`
2. **Preprocessing** (`utils.py::preprocess`) → CLAHE, sharpening, contrast enhancement
3. **OCR** (`utils.py::extract_text`) → EasyOCR (primary) + Tesseract (fallback), with screenshot hash caching
4. **Parsing** (`parsing.py`) → timestamp clustering, event extraction, item/qty/price parsing with OCR error correction
5. **Window Detection** (`utils.py::detect_window_type`) → identifies sell_overview, buy_overview, sell_item, buy_item
6. **Transaction Clustering** (`tracker.py::_cluster_events`) → groups related events (transaction + placed/listed/withdrew) with time-based windows
7. **Case Resolution** (`tracker.py::_resolve_cases`) → determines transaction type: collect, relist_full, relist_partial
8. **Validation & Deduplication** (`tracker.py`) → whitelist check, quantity bounds, DB-based delta detection, unique constraints
9. **Database Storage** (`database.py`) → thread-safe SQLite with persistent baseline (tracker_state table)

### Critical Architecture Concepts

**Window Types (Mutually Exclusive)**
- Only ONE tab visible at a time (Buy XOR Sell)
- `sell_overview`: "Sales Completed" keyword → transaction log for sell events
- `buy_overview`: "Orders Completed" keyword → transaction log for buy events  
- `sell_item`: "Set Price" + "Register Quantity" → NO transaction log
- `buy_item`: "Desired Price" + "Desired Amount" → NO transaction log
- **Transaction logs only exist in overview windows**

**Persistent Baseline System**
- `tracker_state` DB table survives app restarts
- `last_overview_text` persisted via `save_state()` → enables delta detection after restart
- First snapshot imports 4 visible log lines on initial window open
- DB-based checks prevent skipping genuine new transactions

**Transaction Cases (6 types)**
- Sell: `collect`, `relist_full`, `relist_partial`
- Buy: `collect`, `relist_full`, `relist_partial`
- Cases determined by event clustering with time windows:
  - withdrew events: ≤8s window
  - other events: ≤3s window
  - first snapshot: 10min window for historical logs

**Timestamp Clustering Logic**
- Handles reversed chronological order (newest→oldest)
- Timestamp cluster at beginning → index-based event assignment
- 1st event gets 1st timestamp, 2nd event gets 2nd timestamp, etc.
- Prevents incorrect timestamp attribution

**Occurrence Index System**
- `occurrence_index` in DB allows multiple identical transactions per timestamp
- Prevents duplicate constraint failures for repeated buy/sell of same item/qty/price
- Runtime + persistent state tracking via `_occurrence_state`

**OCR Error Correction**
- Letter→Digit: O→0, I→1, l→1, S→5, Z→2, B→8
- Space-tolerant price parsing: "585, 585, OO0" → 585,585,000
- Missing leading digits detection via plausibility check
- Fuzzy item name matching with market.json whitelist (4874 items)

**API Integration**
- BDO World Market API: dynamic min/max prices via `bdo_api_client.py`
- `market_json_manager.py`: item name ↔ ID mapping, whitelist validation
- Price plausibility: unit price must be in [Min*0.9, Max*1.1]
- 7-day cache (prices only change on weekly patch day)

**Performance Optimizations**
- Screenshot hash caching: 50-80% reduction for static screens (MD5-based, 2s TTL)
- GPU acceleration: 2GB VRAM limit + low priority = no game lag, 20% faster
- Pre-compiled regex patterns: 10-15% faster parsing
- LRU caches: item validation (500), item correction (implicit via rapidfuzz)
- DB indices: 4 indices for 30-40% faster queries
- Memory-stable: deque(maxlen=1000) for seen signatures

## Key Files & Responsibilities

**Core Processing**
- `tracker.py`: MarketTracker class, window detection, event clustering, case resolution, DB interaction
- `parsing.py`: Timestamp extraction, log entry splitting, item/qty/price parsing, OCR correction patterns
- `utils.py`: Screenshot capture, preprocessing, OCR (EasyOCR + Tesseract), fuzzy matching, window title detection
- `database.py`: Thread-safe SQLite connections, tracker_state persistence, deduplication queries
- `gui.py`: Tkinter GUI, region selection, single/auto scan controls, data visualization, health monitoring

**Configuration & Data**
- `config.py`: Region, poll interval, OCR parameters, GPU settings, item bounds (MIN=1, MAX=5000)
- `config/market.json`: Item database (4874 items), name ↔ ID mapping, whitelist source
- `config/item_categories.csv`: most_likely_buy/most_likely_sell for historical transaction classification
- `bdo_api_client.py`: BDO World Market API client, price range queries, caching
- `market_json_manager.py`: Item name correction, validation, fuzzy matching against market.json

**Database Schema**
- `transactions`: id, item_name, quantity, price, transaction_type (buy/sell), timestamp, tx_case, occurrence_index
- `tracker_state`: key-value store for persistent state (last_overview_text, tx_occurrence_state_v1)
- Unique constraint: (item_name, quantity, price, transaction_type, timestamp, occurrence_index)

**Debug & Artifacts**
- `debug_orig.png`: Latest raw screenshot
- `debug_proc.png`: Latest preprocessed screenshot (CLAHE + sharpen)
- `ocr_log.txt`: Live OCR output with timestamps (auto-rotates at 10MB)
- `debug/`: Archived debug screenshots with UTC timestamps

## Development Rules

### Critical Constraints
- **ONLY evaluate transaction logs in sell_overview and buy_overview** (detail windows have no logs)
- **ALWAYS only ONE tab visible** (Sales Completed XOR Orders Completed)
- **First snapshot imports 4 visible log lines immediately** on market window open
- **Persistent baseline** (`tracker_state` DB) enables delta detection across app restarts
- **Buy/Sell determination**: Primary = window type, Secondary = text anchors (purchased/sold), Tertiary = item categories
- **No database object sharing across threads** (use `get_cursor()` / `get_connection()`)
- **Always use game timestamps**, never system time as primary source
- **Item names resolved exclusively via config/market.json** (4874 items whitelist)
- **Quantity bounds: [1, 5000]** filters unrealistic values and UI noise
- **Never save raw OCR 1:1** – always structure, validate, deduplicate first
- **âš ï¸ CRITICAL: Users REGULARLY buy/sell identical transactions (same item/qty/price) within SECONDS**
  - Example: 5x batches of 5000x Material within 1 minute
  - **NEVER use time-based dedup windows** (e.g., "skip if within 5 minutes") - breaks legitimate use cases!
  - **ONLY deduplicate using Content-Hash** (position-aware, includes OCR raw text)
  - **Trust OCR timestamps** - if parser says 23:25, don't change it to 23:26 without solid proof

### When Debugging Issues
1. **ALWAYS check first**: `debug_proc.png`, `debug_orig.png`, `ocr_log.txt`
2. Check last 100 lines of `ocr_log.txt` for parsing errors
3. Verify window type detection (should match current tab)
4. Check timestamp clustering logic (neuester→ältester)
5. Verify item name is in `config/market.json` whitelist
6. Check quantity is in bounds [1, 5000]
7. Verify no division-by-zero in price fallback calculations

### Testing Requirements
- All new features must have test script in `scripts/test_*.py`
- Run `scripts/run_all_tests.py` before committing
- Current status: 29/32 tests passing (3 deprecated)
- Deprecated tests (should be updated or archived):
  - `test_listed_fix_targeted` (anchor priority logic replaced this)
  - `test_listed_transaction_fix` (redundant with test_magical_shard_fix_final)
  - `test_user_scenario_lion_blood` (OCR error now rejected by whitelist)

### Performance Considerations
- Poll interval: 0.5s default (captures >95% of transactions)
- GPU mode: RTX 4070 @ 2GB VRAM limit + low priority = no game lag
- Cache hit rate: 50% typical → ~1000ms avg OCR time
- Throughput: ~99 scans/min (GPU cached), ~60 scans/min (CPU)
- Memory: stable ~80MB (deque maxlen=1000 prevents unbounded growth)

### Code Style & Patterns
- Defensive programming: `try/except` on all OCR, DB, GUI, threading operations
- Pre-compile regex patterns for repeated use (see `parsing.py::_DETAIL_PATTERNS`)
- Use `@lru_cache` for expensive repeated lookups (item validation, correction)
- Thread-safe DB access: always use `get_connection()` / `get_cursor()`, never share conn objects
- Debug logging via `log_debug()` with timestamps for development diagnostics

### Important Anti-Patterns
- Never blindly trust OCR output (always validate against whitelist)
- Never skip deduplication (use session signatures + unique index + DB delta check)
- Never assume OCR quality (handle spaces, missing digits, confusables)
- Never use system time as primary timestamp (always parse game timestamps)
- Never evaluate transaction logs in detail windows (sell_item, buy_item)
- Never perform price fallback calculations on historical logs without current UI metrics

## Context from Instructions.md

### Transaction Cases Explained
```
sell_collect: 1x Transaction (item sold & collected)
sell_relist_partial: Transaction + Withdrew + Listed (partial sale, rest re-listed)
sell_relist_full: Transaction + Listed (full sale, new listing placed)
buy_collect: 1x Transaction (item bought & collected)
buy_relist_full: Transaction + Listed (full buy, new order placed)
buy_relist_partial: Transaction + Withdrew + Listed (partial buy, rest re-ordered)
```

### Price Reconstruction Formulas
Only apply when:
1. Transaction triggered by Collect/Relist button
2. Current overview window (not historical log)
3. All UI metrics extractable

**Buy Overview**: `ordersCompleted * (remainingPrice / (orders - ordersCompleted))`
**Sell Overview**: `salesCompleted * price * 0.88725`

Constraints:
- Buy: (orders - ordersCompleted) > 0 AND remainingPrice > 0
- Sell: salesCompleted > 0 AND price > 0
- Division by zero → no fallback

### Window Detection Keywords
- `sell_overview`: "Sales Completed" (whitespace-tolerant, OCR variants accepted)
- `buy_overview`: "Orders Completed" (whitespace-tolerant, OCR variants accepted)
- `sell_item`: "Set Price" AND "Register Quantity" (both required)
- `buy_item`: "Desired Price" AND "Desired Amount" (both required)

### Anchor Priority (Event Classification)
```
transaction > purchased > placed > listed
```
This prevents "Listed-Only-Saves" where a listing without transaction is incorrectly saved.

## Windows-Specific Notes

### Focus Detection
- `FOCUS_REQUIRED = True` by default
- `FOCUS_WINDOW_TITLES = ["Black Desert", "BLACK DESERT -"]`
- Skips OCR when game window not in foreground (prevents wasted scans)
- Uses Win32 API (`get_foreground_window_title()`)

### Tesseract Path
Default: `C:\Program Files\Tesseract-OCR\tesseract.exe`
Update in `config.py` if installed elsewhere.

### Database Path
Default: `bdo_tracker.db` (same directory as script)
Backups automatically created in `backups/` directory.

## Useful Patterns

### Adding New Test
```python
# scripts/test_your_feature.py
import sys
sys.path.insert(0, "c:\\Users\\kdill\\Desktop\\market_tracker")

from tracker import MarketTracker
from database import get_connection

print("🧪 Testing your feature\n")
print("="*70)

tracker = MarketTracker(debug=True)
# ... test implementation

print("✅ PASS" if condition else "❌ FAIL")
```

### Debugging OCR Issues
```python
# Check last N lines of OCR log
with open("ocr_log.txt", "r", encoding="utf-8") as f:
    lines = f.readlines()[-100:]  # Last 100 lines
    for line in lines:
        print(line.strip())
```

### Database Query Pattern
```python
from database import get_connection

conn = get_connection()
cur = conn.cursor()

# Query with proper parameterization
cur.execute("""
    SELECT * FROM transactions 
    WHERE item_name = ? AND transaction_type = ?
    ORDER BY timestamp DESC
""", (item_name, tx_type))

results = cur.fetchall()
conn.commit()  # Always commit after writes
```

### Item Validation Pattern
```python
from market_json_manager import correct_item_name, is_valid_item

# Validate with fuzzy matching
corrected_name, is_valid = correct_item_name(raw_ocr_name, min_score=86)

if is_valid:
    # Use corrected_name
    pass
else:
    # Reject - not in whitelist
    pass
```

## Version History

- **0.2.4** (2025-10-12): Live API integration, performance optimizations, duplicate handling, 29/32 tests passing
- **0.2.3** (2025-10-12): Persistent baseline, OCR V2, GPU acceleration
- **0.2.0** (2025-10-11): Window detection, transaction cases, clustering logic
