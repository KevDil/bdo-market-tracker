# Repository Guidelines
- Reply to the user in German.

## Scope & Sources of Truth
- This is the single authoritative guide for maintainers, automation agents, and contributors. Retired specs (`instructions.md`, `copilot-instructions.md`, `.windsurf/rules/project-rules.md`) now mirror this file or point to archived copies under `docs/archive/`.
- Keep this document synchronized with real implementation details (OCR engine, ROI, cache values, test counts, etc.). When you change behaviour, update this file before merging.

## System Overview
- Platform: Windows 10+ with Python 3.10–3.13. Tkinter GUI (`python gui.py`) is the primary entry point; scripts under `scripts/` cover calibration, testing, and maintenance.
- Pipeline sequence: focus check → region capture → ROI trim (top 75%) → preprocessing → EasyOCR → parsing and clustering → dedupe → SQLite persistence → GUI updates/export.
- Key modules at repo root: `config.py` (persistent settings), `utils.py` (capture/OCR/cache/focus), `parsing.py` (regex anchors, normalization, **Performance V6: parsing cache**), `tracker.py` (clustering, UI inference, dedupe coordination), `database.py` (SQLite layer, **Performance V6: batch-insert**), `market_json_manager.py` (name correction + RapidFuzz, **Performance V6: item-name cache**), `bdo_api_client.py` (price bounds + throttled retries), `gui.py` (controls, auto-track, exports), `preorder_manager.py` (preorder/listing lifecycle management).

## Preorder & Listing Tracking (NEW)
- **Purpose**: Track pre-placed market orders (buy-side preorders, sell-side listings) and detect auto-collection when transactions occur.
- **Database**: Two tables (`preorders` and `listings`) store active/collected/cancelled orders with fields: `id`, `item_name`, `quantity`, `quantity_filled/quantity_sold`, `price`, `timestamp`, `status`, `collected_at`, `collected_tx_id`.
- **Unique Constraint**: Only ONE active order per item enforced via unique index `WHERE status='active'`. Placing new order auto-collects old one.
- **PreorderManager API** (`preorder_manager.py`):
  - `store_preorder(item, qty, price, timestamp)` / `store_listing(...)`: Store new order, auto-collect old one if exists.
  - `find_matching_preorder(item, warehouse_delta, balance_delta, timestamp)`: Match order for auto-collect detection.
  - `mark_collected(preorder_id, collected_at, tx_id)` / `mark_listing_collected(...)`: Mark order as collected after transaction.
  - `cancel_preorder(item, qty, price)` / `cancel_listing(...)`: Mark order as cancelled from log events.
  - In-memory cache with 60s TTL for active orders.
- **Detection Logic** (in `tracker.py`):
  - **Placement Detection**:
    - **Buy-Side** (`buy_item` window): `balance↓`, `warehouse=0` → Preorder placed. Extract quantity from UI metrics (`orders` field).
    - **Sell-Side** (`sell_item` window): `balance≈0`, `warehouse↓` → Listing placed. Quantity = abs(warehouse_delta).
  - **Collection Detection**:
    - **Auto-Collect** (Detail-Window): Warehouse surplus detected → Query PreorderManager → Apply price correction (add preorder/listing price to transaction total).
    - **Manual Collect** (Overview Collect Button): Transaction log shows "Transaction of [item]" → Match and mark order as collected.
  - **Cancellation Detection**: Transaction log shows "Withdrew order of [item]" (buy-side) or "Withdrew [item] from market listing" (sell-side) → Mark order as cancelled.
- **Price Correction**: When preorder/listing is auto-collected, transaction total = purchase/sale price + preorder/listing price. This prevents under-reporting when game collects old orders silently.
- **Integration Points**:
  - `_monitor_detail_window()`: Calls `_detect_preorder_placement()` / `_detect_listing_placement()` BEFORE plausibility checks.
  - `_check_for_preorder_autocollect()`: Queries PreorderManager, calculates price correction.
  - `process_ocr_text()`: Parses log entries for "withdrew" and "transaction" events, calls handlers.
  - `_handle_preorder_cancellation()`: Processes "Withdrew order" log entries.
  - `_handle_preorder_or_listing_collection()`: Processes "Transaction of" log entries from Collect button.
- **Parsing Support** (`parsing.py`): Updated patterns to recognize both "Withdrew order of" (buy-side) and "Withdrew ... from market listing" (sell-side).
- **No Expiration**: Preorders/listings remain active indefinitely until collected or cancelled.

## Project Layout & Assets
- Support data: `config/` for presets, `debug/` for latest screenshots/log artefacts, `dev-screenshots/` for reproducible scenarios, `docs/` for research and historical notes, `backups/` for DB snapshots.
- The working database `bdo_tracker.db` lives in the repo for development; recreate with `python scripts/utils/reset_db.py` (requires confirmation).
- Archived material resides under `docs/archive/` (full instruction history, legacy OCR analyses) and `docs/archived/`; treat both as read-only context.

## Operational Workflow & Invariants
- Focus guard: only run capture when the foreground window title contains `"Black Desert"` or `"BLACK DESERT -"`. `FOCUS_REQUIRED` must remain true.
- Capture: default region `(734, 371, 1823, 1070)` stored in `tracker_settings.capture_region`. Adjust using `python scripts/utils/calibrate_region.py` and verify visually.
- ROI strategy: three specialized regions (`detect_log_roi`, `detect_window_label_roi`, `detect_metrics_roi`) for targeted OCR. Log-ROI covers transactions (0-32% height), Label-ROI identifies window type (33-65%), Metrics-ROI captures UI deltas (33-97%). Label is processed first; Log-OCR skips when detail windows detected. See `dev-screenshots/regions.png` for visual reference.
- Polling: standard interval `POLL_INTERVAL = 0.15s`; burst scans at 0.08s for `sell_item`/`buy_item`; `GAME_FRIENDLY_MODE` pushes polling ≥0.8s when GPU is active.
- OCR: EasyOCR only (`OCR_ENGINE = 'easyocr'`, `OCR_FALLBACK_ENABLED = False`), GPU with RTX 4070 SUPER. **Performance V5 (2025-10-22)**: EXHAUSTIVE per-ROI optimization tested 6,240 configurations. Optimal params per ROI: warehouse_sell 15.9ms, warehouse_buy 18.0ms, balance 18.1ms, item_name 20.2ms, label 56.5ms, log 151.3ms, metrics 186.0ms. Uses ROI-specific canvas_size (400-1200), text_threshold (0.50-0.70), batch_size (4-8), contrast_ths (0.22-0.32), adjust_contrast (0.25-0.40), low_text (0.32-0.40), link_threshold (0.32-0.40). Average speedup: **-59% to -85%** vs previous configs. Cache MD5 of ROI with `CACHE_TTL = 5.0` seconds and `MAX_CACHE_SIZE = 20`; never disable cache. GPU-Erkennung nutzt `reader.recognizer`/`reader.detector`-Devices, Logs zeigen `[EASYOCR] … device=cuda:0` bei aktiven GPU-Läufen. See `docs/EASYOCR_OPTIMIZATION_2025-10-22.md` for tuning details.
- **Performance V6 (2025-10-22)**: Parsing & Database optimizations provide 4.4x speedup on typical 5-item scans. (1) **Parsing Cache**: Content-hash-based caching in `split_text_into_log_entries()` with 30s TTL, 3.1x speedup on repeated text (60-80% hit rate). (2) **Item-Name Cache**: LRU cache (maxsize=500) in `correct_item_name()`, 1954x speedup with 98% hit rate on repeated items. (3) **Database Batch-Insert**: `store_transactions_batch()` for multi-item writes, 5-11x speedup on 5-10 item batches. Combined: 4.4x faster overall (40ms → 4.3ms per typical scan). See `docs/PERFORMANCE_V6_2025-10-22.md` for full details.
- Vollbild-Preprocessing wird per Frame-Hash im RAM gepuffert; identische Frames überspringen die CLAHE-Runde completely (0 ms), Messwerte landen in `metrics['preprocess_cache_hit']`.
- Detail-/Metrics-ROI wird **NUR bei echten Transaktionen** ausgelesen: nach Fensterwechseln (einmalig via `_pending_metrics_refresh`), Burst-Rescans (`_request_immediate_rescan > 0`), oder Detail-Hinweisen (`Set Price`/`Desired Price`). Der frühere 5-Sekunden-Timer wurde entfernt, da UI-Metriken nur für Delta-Inferenz bei tatsächlichen Transaktionen gebraucht werden. In aktiven Detailfenstern werden sowohl Log- als auch Metrics-ROI übersprungen – nur das Label wird ausgelesen, sodass Burst-Scans keinen dreifachen OCR-Aufwand mehr verursachen. Transaction-Parsing (`split_text_into_log_entries`) basiert ausschließlich auf dem Log-ROI und akzeptiert im Fallback nur noch Zeilen mit echten Ankern (`transaction`, `placed`, `withdrew`, `listed`, `purchased`, `sold`); UI-Text aus dem Metrics-ROI landet nicht mehr in den Structured-Eintragslisten.
- Window categories: `sell_overview` and `buy_overview` may produce transactions. `sell_item`/`buy_item` trigger burst rescans and must not write to DB.
- **Detail-Window Baseline Capture** (FIX 2025-10-21): Baseline wird im **ersten Frame** nach Window-Transition gesetzt (Frame-Perfect), bevor User-Aktionen möglich sind. Bei Window-Transition zu `buy_item`/`sell_item` wird `_detail_needs_baseline_capture` Flag gesetzt; der nächste Scan erfasst Balance/Warehouse als Baseline und aktiviert Delta-Monitoring. Dies verhindert verpasste Transaktionen bei SOFORT-Käufen (z.B. Preorder auto-collect). Als Sicherheitsnetz dient ein **Log-Based Fallback**: Nach Detail-Window-Exit wird der Transaction-Log auf fehlende "Purchased"-Einträge geprüft und diese nachgespeichert. Zusätzlich erzwingt `_force_save_pending_transaction()` beim Schließen eines Detail-Fensters eine `buy_collect_balance_only_forced`-Transaktion, falls nur ein Balance-Delta vorliegt und Warehouse-Deltas noch fehlen. Siehe `docs/DETAIL_WINDOW_BASELINE_FIX_2025-10-21.md` für Details.

## Parsing, Classification & Inference
- `parsing.split_text_into_log_entries` segments OCR output; `extract_details_from_entry` attaches event metadata. Event anchors prioritize `transaction > purchased > placed > listed`; exclude UI-only rows where quantity is missing.
- Game timestamps are mandatory; never substitute system time. Quantities must satisfy `1 ≤ quantity ≤ 5000`; reject noise unless UI delta inference fills data.
- Item names always pass through `market_json_manager.correct_item_name`. Exact whitelist matches stay verbatim; near matches require RapidFuzz score ≥86.
- Market price checks use live BDO ranges; sell-side totals are validated against net proceeds (tax factor 0.88725) so legitimate post-tax values are accepted without triggering UI fallbacks.
- Sell totals with missing trailing digits are reconstructed before persistence: we prefer the current UI unit price when available, merge prefix-style OCR hints like `4,270,245,5_ Silver`, and only fall back to the cached `market_json_manager` base price (tax factor 0.88725) when UI data is unavailable. This keeps offline recovery working while handling patches that shift marketplace base prices.
- UI metrics (orders, ordersCompleted, remainingPrice, etc.) normalise mixed punctuation (`:` vs `：`) and ignore hotkey digits by selecting the last significant silver amount before `Re-list`. Delta inference creates `_ui_inferred` entries only when previous metrics exist, counters increase, the price delta is plausible, and a matching placed log is present within ~120 seconds. Placed-only log rows are never persisted directly; the synthetic collect path is the sole way they surface.
- Supported cases: `buy_collect`, `buy_relist_full`, `buy_relist_partial`, `buy_collect_balance_only_forced`, `sell_collect`, `sell_relist_full`, `sell_relist_partial`, plus die zwei `_ui_inferred` Varianten. Adding a new case requires GUI filters/exports/tests updates.

## Deduplication & Persistence
- Runtime dedupe uses `seen_tx_signatures` (deque max 1000) and `make_content_hash` with a 20-minute tolerance. A secondary ≤5 min value check blocks near-time duplicates even when timestamps drift, so OCR re-saves (e.g., 11:23 vs. 11:26 Brutal Death Elixir) no longer persist twice.
- `store_transaction_db` manages `_batch_content_hashes` per run; do not bypass or mutate this set from outside the function.
- Database schema (see `database.py` migrations): table `transactions` with `item_name`, `quantity`, `price`, `transaction_type`, `timestamp`, `tx_case`, `occurrence_index`, `content_hash`. Unique index `idx_unique_tx_full` spans these fields to guard duplicates. Additional tables `preorders` and `listings` track active market orders (see Preorder & Listing Tracking section above).
- `occurrence_index` plus `_occurrence_slot` differentiate repeated same-second events. The resolver now only reuses a stored index when the snapshot timestamp trails the latest committed event by ≥1 s (historical import) or when the baseline already contained the line; fresh same-minute transactions continue to receive new indices. Use helpers (`fetch_occurrence_indices`, `transaction_exists_exact`) instead of manual SQL.
- `store_transaction_db` performs an additional historical guard: if an older snapshot (≤ last processed timestamp) tries to persist an item that already has matching occurrences for that minute, the insert is skipped even if the baseline cache was cleared during an auto-track toggle. This blocks the double-save seen when restarting auto-track mid-session.
- Detailfenster-Erkennung nutzt normalisierte Schlüsselfrasen mit robuster ODER-Logik. `sell_item` wird erkannt, sobald `Set Price` sowie **mindestens eines** der Skalenfelder `MAX` oder `MIN` (inklusive OCR-Varianten wie `M4X`, `rnax`, `M1N`, `MLN`) im Text stehen; `Register Quantity` ist optional. `buy_item` setzt analog auf `Desired Price` + (`MAX` **ODER** `MIN`), `Desired Amount` ist optional. Dies ermöglicht robuste Erkennung auch bei Layout-Varianten oder partiellen OCR-Fehlern. Legacy-Heuristiken (Base/Min/Max) bleiben als Fallback aktiv.
- Parser bewahrt `raw_price_hint` für Transaktionszeilen; `MarketTracker` rekonstruiert Buy-Totals anhand dieser Suffixe statt fallback-mäßig den Placed-Betrag zu speichern. Placed/Withdrew-Hints werden dabei ignoriert, sodass nach fehlenden führenden Ziffern (z. B. `688,420`) der volle Betrag (4 688 420) wiederhergestellt und Duplikate verhindert werden.
- Transaktionen ohne erkannte Menge werden nur noch übernommen, wenn starke Anker (listed/withdrew/purchased mit Menge, UI-Metriken oder echte Transaction-Zeile) vorliegen; andernfalls werden sie verworfen, um 1×-Phantome zu verhindern.
- Persistent state in `tracker_state` tracks `last_overview_text`, UI baselines, and flags; only refresh after successful transaction commits. `tracker_settings` holds toggles (capture region, GPU usage, debug mode).
- Baseline gaps are repaired automatically: if a transaction line appears in the cached overview text but no matching DB row exists (even with an older timestamp), the next scan re-imports it despite the recency guard.
- UI-inferred buys trigger only when matching placed/withdrew/transaction anchors exist in the current snapshot; implausible totals are reconstructed from anchor data/base prices or the inference is skipped entirely.

## Coding Standards & Architecture Notes
- Follow PEP 8 with 4-space indentation, snake_case for functions/variables, PascalCase for classes. Keep module responsibilities isolated; avoid cross-layer imports that break the pipeline separation.
- Avoid sharing SQLite connections across threads; always call `database.get_connection()` or `get_cursor()` per usage.
- Keep regexes precompiled at module scope, caches intact, and asynchronous features disabled (`USE_ASYNC_PIPELINE = False`) unless queue contention is solved.
- Do not alter ROI, polling cadence, caching parameters, or focus requirements without reproducible measurements captured in `dev-screenshots/` and documented here.

## Build, Test & Validation
- `python gui.py`: launches the Tkinter interface (auto-track, history, CSV/JSON export).
- `python scripts/run_all_tests.py`: runs the curated suite (29 active, 3 deprecated). Address failures or update deprecated markers if retiring tests.
- Targeted diagnostics: `python tests/unit/test_parsing_crystal.py`, `python tests/unit/test_collect_anchor.py`, `python tests/unit/test_powder_of_darkness.py`. Use them when touching parsing, clustering, or detection logic. Manual end-to-end replays now live under `tests/manual/`.
- Troubleshooting aids: `python analyze_ocr.py --image debug/debug_proc.png` to inspect OCR output; `python scripts/utils/dedupe_db.py` for DB cleanup; `python scripts/utils/reset_db.py` to reset state (also clears `last_overview_text`).
- Always capture fresh `debug_orig.png`, `debug_proc.png`, and `ocr_log.txt` snapshots when investigating regressions. Log rotation limits remain at 10 MB.

## Contribution & Review Workflow
- Run the full test suite before committing meaningful changes; confirm dependencies (EasyOCR/Tesseract models) are installed.
- Commit messages should be imperative and descriptive (e.g., `Refactor price plausibility checks...`). Note database migrations, ROI updates, or behavioural changes explicitly in the body.
- Pull requests must include: behavioural summary, verification steps (tests, scripts, screenshots for GUI), linked issues, and any coordination requirements (e.g., needing DB reset).
- Never revert or overwrite user-provided changes outside your scope. When encountering unexpected diffs, pause and clarify with the owner before proceeding.
- Sync this file with actual behaviour and archive references whenever configuration, cases, or invariants change.

## Safety, Configuration & No-Go Items
- Maintain the focus guard, ROI bounds, caching, and content-hash dedupe. Disabling these invites duplicate writes and OCR noise.
- Do not introduce system-time fallbacks for timestamps or bypass item whitelist validation to force saves.
- Avoid blocking operations inside the capture loop; network calls (BDO API) and DB writes must occur after OCR completes.
- After `reset_db`, ensure `tracker_state` baselines are cleared (handled in code) before resuming tracking.
- Use GPU modes cautiously; keep memory cap at 2048 MB and low-priority streams to preserve game performance.

## When in Doubt
- Reproduce with GUI auto-track plus debug logging. Validate parsed lines against `ocr_log.txt` and the debug screenshots before adjusting parsing or detection.
- Inspect database results with `check_db.py` or `inspect_db.py` to confirm stored transactions match expectations.
- Keep communication concise: document open questions, highlight risks, and ensure tests or smoke scripts back any change request.
