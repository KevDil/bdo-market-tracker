# Test Suite Inventory (October 2025)

## Structure Overview

- `tests/unit/`: automated regression tests that only depend on pure-Python modules.
- `tests/manual/`: heavyweight scripts that require the full Windows OCR environment (EasyOCR, OpenCV, GUI focus, real DB/API access). These are excluded from automated runs.
- `scripts/archive/`, `scripts/archived/`: legacy material kept for historical reference. They exercise deprecated code paths and should not be executed without review.

`scripts/run_all_tests.py` now discovers and runs only the files under `tests/unit/`.

## Automated Unit Tests

| File | Focus | Notes |
| --- | --- | --- |
| `tests/unit/test_collect_anchor.py` | Parsing: filters UI-only “Collect” entries | pure parsing pipeline |
| `tests/unit/test_powder_of_darkness.py` | Parsing: Powder of Darkness regression | validates qty/price extraction |
| `tests/unit/test_parsing_crystal.py` | Parsing: Crystal of Void Destruction extraction | ensures transaction detection |
| `tests/unit/test_ocr_robustness.py` | Parsing normalization (Silver keyword, transaction priority) | covers common OCR noise |
| `tests/unit/test_price_plausibility.py` | Price plausibility (net vs gross totals) | stubs heavy deps for deterministic behaviour |

All unit tests follow simple `assert` semantics and can be executed with `python tests/unit/<file>.py` or via the aggregated runner.

## Manual / Heavyweight Tests

| File | Category | Reason |
| --- | --- | --- |
| `tests/manual/test_end_to_end.py` | E2E workflow | Requires live BDO API + EasyOCR |
| `tests/manual/test_exact_user_scenario.py` | Scenario replay | Visual log inspection, depends on tracker internals |
| `tests/manual/test_integration.py` | DB replay | Needs real SQLite + OCR pipeline |
| `tests/manual/test_item_validation.py` | Tracker + DB validation | Requires MarketTracker, heavy OCR deps |
| `tests/manual/test_magical_shard_fix_final.py` | Regression replay | Manipulates real DB, needs OCR stack |
| `tests/manual/test_market_json_system.py` | Market JSON + API smoke | Hits external API |
| `tests/manual/test_regression_helix_timestamp.py` | Timestamp regression | Uses MarketTracker with OCR deps |
| `tests/manual/test_window_detection.py` | Window classification heuristics | Console-only but requires utils with OCR deps |

Run these scripts manually on a configured Windows machine. They are **not** part of CI.

## Legacy Material

- `scripts/archive/`: one-off reproductions from October 2025 bug hunts (timestamp drift, historical baseline, etc.).
- `scripts/archived/`: older investigations for OCR, UI metrics, and API layers.

These folders exist for historical context. Treat each script as unmaintained unless explicitly revived.

## Framework & Conventions

- Automated tests rely on plain `assert` statements; no external framework is required (compatible with `pytest` if available).
- Manual scripts print human-readable guidance and often clean up the database after execution.
- All tests prepend the repository root to `sys.path` so they can be launched from any working directory.

## Follow-Up Actions

1. Add integration tests that mock the tracker pipeline (without requiring OpenCV/EasyOCR) to improve automation coverage.
2. Evaluate whether the manual scripts can be refactored into fixture-driven tests once lightweight mocks for OCR + GUI are available.
3. Keep `tests/unit/` up to date when new parsing or plausibility fixes ship; update this inventory accordingly.
