instructions

---
applyTo: '**'
---
# BDO Market Tracker – Agent Playbook
- **Mission**: Capture the in-game market window, OCR the transaction log, deduplicate against persisted state, and store clean buy/sell rows for the GUI and analytics.
- **Pipeline**: `MarketTracker` captures frames, `utils.preprocess` + `ocr_image_cached` yield text, `parsing.split_text_into_log_entries` + `extract_details_from_entry` structure events, tracker clusters anchors, and `database.save_transaction` commits with occurrence slots.
- **Transaction Cases**: Tracker resolves clustered anchors into `buy_collect`, `buy_relist_full`, `buy_relist_partial`, `sell_collect`, `sell_relist_full`, or `sell_relist_partial`—never skip the occurrence_index bookkeeping that allows repeated transactions per timestamp.
- **Windows Rule**: Only `sell_overview` and `buy_overview` may emit transactions; `sell_item`/`buy_item` dialogs merely trigger burst rescans and must never persist data.
- **Baseline & Delta**: The first snapshot seeds `tracker_state` with up to four rows; subsequent scans compare against the baseline text, DB lookups (`transaction_exists_*`), and `seen_tx_signatures`. Extend these guards instead of adding ad-hoc dedupe.
- **Timestamp Assignment**: Parsing now walks timestamps sequentially via a deque so mixed blocks like `11.46 11.46 11.30` map correctly. Do not revive distance-based heuristics that skew times.
- **Price Plausibility**: `check_price_plausibility` (market.json + BDO API) invalidates totals <60% of the minimum or >10x the maximum. Leave such entries with `price=None` so tracker can reconstruct them from UI deltas.
- **UI Deltas**: Overview metrics (`orders/ordersCompleted/remainingPrice` or `salesCompleted/price`) patch missing collect lines. Always retain the transaction quantity rather than substituting UI counts.
- **Item Identity**: Route every name through `market_json_manager.correct_item_name`; exact whitelist hits must remain untouched and fuzzy matches should respect the existing thresholds.
- **Database Usage**: Acquire cursors via `database.get_cursor()`/`get_connection()` only; SQLite connections are thread-bound and must not be cached on the tracker.
- **Debug Workflow**: Reproduce issues with `ocr_log.txt`, `debug_orig.png`, and `debug_proc.png`. The GPU/EasyOCR startup banner during tests is expected and should stay.
- **Key Files**: `tracker.py` (state machine, clustering, UI inference), `parsing.py` (regex segmentation), `database.py` (persistence + tracker_state), `utils.py` (OCR, caching, plausibility), `config.py` (regions, thresholds), `gui.py` (Tkinter front end).
- **Testing**: Run `C:/Python313/python.exe scripts/run_all_tests.py` before shipping; quick spot checks live in `scripts/test_parsing_crystal.py` and `scripts/test_window_detection.py`.
- **Smoke Inputs**: The VS Code tasks ("Quick parsing smoke test", "Run simulation after inference patch", etc.) replay critical OCR samples—use them whenever parsing or clustering changes.
- **Logging Style**: Keep debug messages short (`[PRICE-TRUNCATED]`, `[DELTA]`) and reuse precompiled regexes; avoid per-iteration `re.compile`.
- **Failure Policy**: Never fall back to system time or fabricated totals—drop the candidate or persist `price=None` if OCR data is unusable.
- **Config Discipline**: Treat `config/market.json` and `config/item_categories.csv` as the single sources of truth for names and buy/sell hints.
- **Performance Guardrails**: Respect screenshot hash caching and burst timers; keep network/API calls out of the capture loop to maintain ~1.5s scans.
- **GUI Expectations**: Mirror new tracker flags in `gui.py` and persist them with `save_state` so auto-track resumes after restarts.
- **First Troubleshooting Step**: Walk the full pipeline—capture → OCR → parsing → clustering → DB → GUI—to pinpoint regressions; most issues stem from window misclassification or timestamp pairing.
