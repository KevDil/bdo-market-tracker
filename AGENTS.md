# Repository Guidelines

## Scope & Sources of Truth
- This is the single authoritative guide for maintainers, automation agents, and contributors. Retired specs (`instructions.md`, `copilot-instructions.md`, `.windsurf/rules/project-rules.md`) now mirror this file or point to archived copies under `docs/archive/`.
- Keep this document synchronized with real implementation details (OCR engine, ROI, cache values, test counts, etc.). When you change behaviour, update this file before merging.

## System Overview
- Platform: Windows 10+ with Python 3.10–3.13. Tkinter GUI (`python gui.py`) is the primary entry point; scripts under `scripts/` cover calibration, testing, and maintenance.
- Pipeline sequence: focus check → region capture → ROI trim (top 75%) → preprocessing → EasyOCR → parsing and clustering → dedupe → SQLite persistence → GUI updates/export.
- Key modules at repo root: `config.py` (persistent settings), `utils.py` (capture/OCR/cache/focus), `parsing.py` (regex anchors, normalization), `tracker.py` (clustering, UI inference, dedupe coordination), `database.py` (SQLite layer), `market_json_manager.py` (name correction + RapidFuzz), `bdo_api_client.py` (price bounds + throttled retries), `gui.py` (controls, auto-track, exports).

## Project Layout & Assets
- Support data: `config/` for presets, `debug/` for latest screenshots/log artefacts, `dev-screenshots/` for reproducible scenarios, `docs/` for research and historical notes, `backups/` for DB snapshots.
- The working database `bdo_tracker.db` lives in the repo for development; recreate with `python scripts/utils/reset_db.py` (requires confirmation).
- Archived material resides under `docs/archive/` (full instruction history, legacy OCR analyses) and `docs/archived/`; treat both as read-only context.

## Operational Workflow & Invariants
- Focus guard: only run capture when the foreground window title contains `"Black Desert"` or `"BLACK DESERT -"`. `FOCUS_REQUIRED` must remain true.
- Capture: default region `(734, 371, 1823, 1070)` stored in `tracker_settings.capture_region`. Adjust using `python scripts/utils/calibrate_region.py` and verify visually.
- ROI trim: keep y-range at top 0–75% of the capture to include notifications while excluding inventory icons.
- Polling: standard interval `POLL_INTERVAL = 0.15s`; burst scans at 0.08s for `sell_item`/`buy_item`; `GAME_FRIENDLY_MODE` pushes polling ≥0.8s when GPU is active.
- OCR: EasyOCR only (`OCR_ENGINE = 'easyocr'`, `OCR_FALLBACK_ENABLED = False`), GPU optional with 2 GB cap and low-priority streams. Cache MD5 of ROI with `CACHE_TTL = 5.0` seconds and `MAX_CACHE_SIZE = 20`; never disable cache.
- Window categories: `sell_overview` and `buy_overview` may produce transactions. `sell_item`/`buy_item` trigger burst rescans and must not write to DB.

## Parsing, Classification & Inference
- `parsing.split_text_into_log_entries` segments OCR output; `extract_details_from_entry` attaches event metadata. Event anchors prioritize `transaction > purchased > placed > listed`; exclude UI-only rows where quantity is missing.
- Game timestamps are mandatory; never substitute system time. Quantities must satisfy `1 ≤ quantity ≤ 5000`; reject noise unless UI delta inference fills data.
- Item names always pass through `market_json_manager.correct_item_name`. Exact whitelist matches stay verbatim; near matches require RapidFuzz score ≥86.
- Market price checks use live BDO ranges; sell-side totals are validated against net proceeds (tax factor 0.88725) so legitimate post-tax values are accepted without triggering UI fallbacks.
- Sell totals with missing leading digits are reconstructed before persistence: we pull the base price from the local `market_json_manager` cache, apply the marketplace tax factor (0.88725), and choose the candidate whose trailing digits match the OCR hint. This path works fully offline and prevents historic sell rows like Exalted Soul Fragment from being dropped.
- UI metrics (orders, ordersCompleted, remainingPrice, etc.) normalise mixed punctuation (`:` vs `：`) and ignore hotkey digits by selecting the last significant silver amount before `Re-list`. Delta inference creates `_ui_inferred` entries only when previous metrics exist, counters increase, the price delta is plausible, and a matching placed log is present within ~120 seconds. Placed-only log rows are never persisted directly; the synthetic collect path is the sole way they surface.
- Supported cases: `buy_collect`, `buy_relist_full`, `buy_relist_partial`, `sell_collect`, `sell_relist_full`, `sell_relist_partial`, plus the two `_ui_inferred` variants. Adding a new case requires GUI filters/exports/tests updates.

## Deduplication & Persistence
- Runtime dedupe uses `seen_tx_signatures` (deque max 1000) and `make_content_hash` with a 20-minute tolerance. Identical hashes after 20 minutes count as new transactions.
- `store_transaction_db` manages `_batch_content_hashes` per run; do not bypass or mutate this set from outside the function.
- Database schema (see `database.py` migrations): table `transactions` with `item_name`, `quantity`, `price`, `transaction_type`, `timestamp`, `tx_case`, `occurrence_index`, `content_hash`. Unique index `idx_unique_tx_full` spans these fields to guard duplicates.
- `occurrence_index` plus `_occurrence_slot` differentiate repeated same-second events. The resolver now only reuses a stored index when the snapshot timestamp trails the latest committed event by ≥1 s (historical import) or when the baseline already contained the line; fresh same-minute transactions continue to receive new indices. Use helpers (`fetch_occurrence_indices`, `transaction_exists_exact`) instead of manual SQL.
- `store_transaction_db` performs an additional historical guard: if an older snapshot (≤ last processed timestamp) tries to persist an item that already has matching occurrences for that minute, the insert is skipped even if the baseline cache was cleared during an auto-track toggle. This blocks the double-save seen when restarting auto-track mid-session.
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
