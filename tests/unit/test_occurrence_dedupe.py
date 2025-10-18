import datetime
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from ._stubs import install_dependency_stubs  # type: ignore
except ImportError:  # pragma: no cover - fallback for direct execution
    sys.path.insert(0, str(Path(__file__).parent))
    from _stubs import install_dependency_stubs  # type: ignore

install_dependency_stubs()

import tracker  # noqa: E402


class _InitCursor:
    """Minimal cursor stub to satisfy tracker initialization + duplicate checks."""

    def __init__(self) -> None:
        self._normalized_sql = ""

    def execute(self, sql: str, params: Optional[tuple] = None) -> "_InitCursor":
        del params
        self._normalized_sql = " ".join(sql.strip().lower().split())
        return self

    def fetchone(self) -> Optional[tuple[Any, ...]]:
        if "select count(*) from transactions" in self._normalized_sql:
            return (1,)
        if "select id, timestamp from transactions where content_hash" in self._normalized_sql:
            # pretend no matching content hash present (handled separately in tests)
            return None
        return None

    def fetchall(self) -> list[Any]:
        return []


class _Conn:
    def commit(self) -> None:
        pass


def _install_common_patches(monkeypatch):
    state_store: dict[str, str] = {
        "last_overview_text": "",
        "last_ui_buy_metrics": "{}",
        "last_ui_sell_metrics": "{}",
        "tx_occurrence_state_v1": "{}",
    }

    monkeypatch.setattr(tracker, "get_cursor", lambda: _InitCursor())
    monkeypatch.setattr(tracker, "get_connection", lambda: _Conn())
    monkeypatch.setattr(tracker, "save_state", lambda key, value: state_store.__setitem__(key, value))

    def fake_load_state(key: str, default: Optional[str] = None) -> Optional[str]:
        return state_store.get(key, default)

    monkeypatch.setattr(tracker, "load_state", fake_load_state)
    monkeypatch.setattr(tracker, "log_debug", lambda *_, **__: None)
    monkeypatch.setattr(tracker, "get_item_price_range_by_name", lambda *_: {"base_price": 3_000_000})
    monkeypatch.setattr(tracker, "get_base_price_from_cache", lambda *_: None)
    monkeypatch.setattr(tracker, "check_price_plausibility", lambda *_, **__: {"plausible": True})
    monkeypatch.setattr(tracker.MarketTracker, "_is_unit_price_plausible", lambda self, *_args, **_kwargs: True)
    monkeypatch.setattr(tracker.MarketTracker, "_valid_item_name", lambda self, name: True)

    return state_store


def test_occurrence_reused_when_baseline_reset(monkeypatch):
    _install_common_patches(monkeypatch)

    # existing DB already contains occurrence index 0 for the transaction
    monkeypatch.setattr(tracker, "fetch_occurrence_indices", lambda *_, **__: [0])
    # no direct DB duplicates are detected (focus on occurrence reuse path)
    monkeypatch.setattr(tracker, "transaction_exists_exact", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "transaction_exists_any_side", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "transaction_exists_by_values_near_time", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "find_existing_tx_by_values", lambda *_, **__: None)
    monkeypatch.setattr(tracker, "update_tx_timestamp_if_earlier", lambda *_, **__: False)

    mt = tracker.MarketTracker(debug=False)
    mt.last_processed_game_ts = datetime.datetime(2025, 1, 1, 19, 30)

    tx = {
        "item_name": "Legendary Beast's Blood",
        "quantity": 1000,
        "price": 210_000_000,
        "transaction_type": "buy",
        "timestamp": datetime.datetime(2025, 1, 1, 19, 13),
        "_seen_in_prev": False,
        "occurrence_slot": 0,
    }

    reused = mt._resolve_occurrence_index(tx)

    assert reused is True, "existing occurrence index should be reused even if not seen in baseline text"
    assert tx["occurrence_index"] == 0, "occurrence index must match the stored DB slot to avoid duplicates"

