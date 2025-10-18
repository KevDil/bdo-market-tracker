import datetime
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from ._stubs import install_dependency_stubs  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from _stubs import install_dependency_stubs  # type: ignore

install_dependency_stubs()

import tracker  # noqa: E402


BASELINE_TEXT = (
    "Central Market Warehouse Balance 60,000,000,000 2025.10.18 18.32 "
    "Transaction of Magical Shard x100 worth 347,000,000 Silver has been completed "
    "2025.10.18 18.27 Transaction of Sealed Black Magic Crystal x286 worth 860,860,000 Silver has been completed"
)

SNAPSHOT_TEXT = (
    "Central Market 2025.10.18 18.27 Transaction of Sealed Black Magic Crystal "
    "x286 worth 860,860,000 Silver has been completed"
)


class _InitCursor:
    """Minimal cursor stub to satisfy tracker initialization."""

    def __init__(self) -> None:
        self._normalized_sql = ""

    def execute(self, sql: str, params: Optional[tuple] = None) -> "_InitCursor":
        self._normalized_sql = " ".join(sql.strip().lower().split())
        return self

    def fetchone(self) -> Optional[tuple[Any, ...]]:
        if "select count(*) from transactions" in self._normalized_sql:
            return (1,)
        if "select id, timestamp from transactions where content_hash" in self._normalized_sql:
            return None
        return None

    def fetchall(self) -> list[Any]:
        return []


def test_historical_transaction_import(monkeypatch):
    saved: list[dict[str, Any]] = []
    state_store: dict[str, str] = {
        "last_overview_text": BASELINE_TEXT,
        "last_ui_buy_metrics": "{}",
        "last_ui_sell_metrics": "{}",
        "tx_occurrence_state_v1": "{}",
    }

    monkeypatch.setattr(tracker, "get_cursor", lambda: _InitCursor())
    monkeypatch.setattr(tracker, "get_connection", lambda: object())
    monkeypatch.setattr(tracker, "save_state", lambda key, value: state_store.__setitem__(key, value))

    def fake_load_state(key: str, default: Optional[str] = None) -> Optional[str]:
        return state_store.get(key, default)

    monkeypatch.setattr(tracker, "load_state", fake_load_state)
    monkeypatch.setattr(tracker, "fetch_occurrence_indices", lambda *_, **__: [])
    monkeypatch.setattr(tracker, "transaction_exists_exact", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "transaction_exists_any_side", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "transaction_exists_by_values_near_time", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "find_existing_tx_by_values", lambda *_, **__: None)
    monkeypatch.setattr(tracker, "update_tx_timestamp_if_earlier", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "check_price_plausibility", lambda *_, **__: {"plausible": True})
    monkeypatch.setattr(tracker, "correct_item_name", lambda name, min_score=86: name)
    monkeypatch.setattr(tracker, "get_base_price_from_cache", lambda *_, **__: None)
    monkeypatch.setattr(tracker, "get_item_price_range_by_name", lambda *_, **__: {"base_price": 3_000_000})
    monkeypatch.setattr(tracker.MarketTracker, "_is_unit_price_plausible", lambda self, *_args, **_kwargs: True)
    monkeypatch.setattr(tracker.MarketTracker, "_valid_item_name", lambda self, name: True)
    monkeypatch.setattr(tracker, "log_debug", lambda *_, **__: None)
    monkeypatch.setattr(tracker, "detect_window_type", lambda *_: "buy_overview")
    monkeypatch.setattr(tracker, "detect_tab_from_text", lambda *_: "buy")

    def fake_store(self, tx: dict[str, Any]) -> bool:
        saved.append(tx.copy())
        return True

    monkeypatch.setattr(tracker.MarketTracker, "store_transaction_db", fake_store)

    mt = tracker.MarketTracker(debug=False)
    mt.last_processed_game_ts = datetime.datetime(2025, 10, 18, 18, 32)

    mt.process_ocr_text(SNAPSHOT_TEXT)

    matches = [
        tx for tx in saved
        if tx["item_name"] == "Sealed Black Magic Crystal"
        and tx["quantity"] == 286
        and tx["price"] == 860_860_000
        and tx["transaction_type"] == "buy"
    ]

    assert matches, (
        "historical transaction should be imported when not present in DB despite "
        "existing baseline snapshot"
    )

