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

from parsing import parse_timestamp_text, split_text_into_log_entries  # noqa: E402
import tracker  # noqa: E402


BASELINE_TEXT = (
    "Central Market Warehouse Balance 28,668,475,444 Buy Manage Warehouse "
    "Warehouse Capacity 5,045.5 / 11,000 VT 2025.10.18 15.47 Placed order of Sinner's Blood x5,000 for 11,700,000 Silver "
    "2025.10.18 15.47 Transaction of Sinner's Blood x5,000 worth 62,000,000 Silver has been completed "
    "2025.10.18 15.47 Placed order of Spirit's Leaf x5,000 for 11,250,000 Silver "
    "Transaction of Spirit's Leaf x1,111 worth 2,510,860 Silver has been completed"
)

NEW_SNAPSHOT_TEXT = (
    "Central Market Warehouse Balance 28,609,975,444 Buy 2025.10.18 15.54 "
    "Placed order of Sinner's Blood x1,000 for 58,500,000 Silver 2025.10.18 15.54 "
    "Transaction of Sinner's Blood x1,000 worth 11,700,000 Silver has been completed "
    "2025.10.18 15.47 Placed order of Sinner's Blood x5,000 for 11,700,000 Silver "
    "2025.10.18 15.47 Transaction of Sinner's Blood x5,000 worth 62,000,000 Silver has been completed"
)


def test_split_text_prefers_nearest_timestamp():
    entries = split_text_into_log_entries(NEW_SNAPSHOT_TEXT)
    assert len(entries) >= 2

    first_ts_text = entries[0][1]
    assert first_ts_text is not None
    first_ts = parse_timestamp_text(first_ts_text)
    assert first_ts == datetime.datetime(2025, 10, 18, 15, 54)

    second_ts_text = entries[1][1]
    assert second_ts_text is not None
    second_ts = parse_timestamp_text(second_ts_text)
    assert second_ts == datetime.datetime(2025, 10, 18, 15, 54)


class _DummyConnection:
    def commit(self) -> None:  # pragma: no cover - trivial
        pass


class _DummyCursor:
    def __init__(self, saved_rows: list[tuple], state: dict[str, str]) -> None:
        self._saved_rows = saved_rows
        self._state = state
        self._results: list[Any] = []
        self.rowcount = 0

    def execute(self, sql: str, params: Optional[tuple] = None) -> "_DummyCursor":
        normalized = " ".join(sql.strip().lower().split())
        params = params or tuple()
        self.rowcount = 0
        if "select count(*) from transactions" in normalized:
            self._results = [(len(self._saved_rows),)]
        elif normalized.startswith("insert or replace into tracker_state"):
            key, value = params[:2]
            self._state[key] = value
            self._results = []
            self.rowcount = 1
        elif normalized.startswith("select value from tracker_state"):
            key = params[0]
            if key in self._state:
                self._results = [(self._state[key],)]
            else:
                self._results = []
        elif normalized.startswith("insert or ignore into transactions"):
            self._saved_rows.append(params)
            self._results = []
            self.rowcount = 1
        else:
            self._results = []
        return self

    def fetchone(self) -> Optional[tuple]:
        return self._results[0] if self._results else None

    def fetchall(self) -> list[Any]:
        return list(self._results)


def test_tracker_prefers_price_transaction(monkeypatch):
    saved_rows: list[tuple] = []
    state_store: dict[str, str] = {}

    def fake_get_cursor() -> _DummyCursor:
        return _DummyCursor(saved_rows, state_store)

    monkeypatch.setattr(tracker, "get_cursor", fake_get_cursor)
    monkeypatch.setattr(tracker, "get_connection", lambda: _DummyConnection())
    monkeypatch.setattr(tracker, "save_state", lambda key, value: state_store.__setitem__(key, value))
    monkeypatch.setattr(tracker, "load_state", lambda key, default=None: state_store.get(key, default))
    monkeypatch.setattr(tracker, "fetch_occurrence_indices", lambda *_, **__: [])
    monkeypatch.setattr(tracker, "transaction_exists_by_item_timestamp", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "transaction_exists_exact", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "transaction_exists_any_side", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "transaction_exists_by_values_near_time", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "find_existing_tx_by_values", lambda *_, **__: None)
    monkeypatch.setattr(tracker, "update_tx_timestamp_if_earlier", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "check_price_plausibility", lambda *_, **__: {"plausible": True})
    monkeypatch.setattr(tracker, "correct_item_name", lambda name, min_score=86: name)
    monkeypatch.setattr(tracker, "log_debug", lambda *_, **__: None)
    monkeypatch.setattr(tracker.MarketTracker, "_valid_item_name", lambda self, name: True)

    mt = tracker.MarketTracker(debug=False)
    mt.last_overview_text = BASELINE_TEXT

    mt.process_ocr_text(NEW_SNAPSHOT_TEXT)

    matching = [
        row for row in saved_rows
        if row[0] == "Sinner's Blood"
        and row[1] == 1000
        and row[2] == 11_700_000
        and row[3] == "buy"
    ]
    assert len(matching) == 1, f"expected a single saved row for new 1,000x transaction, got {saved_rows}"

    ts_str = matching[0][4]
    assert ts_str == "2025-10-18 15:54:00"

    legacy = [row for row in saved_rows if row[1] == 5000]
    assert not legacy, f"legacy 5,000x rows should be skipped, got {legacy}"
