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
import utils  # noqa: E402


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


def _prepare_tracker(monkeypatch):
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
    monkeypatch.setattr(tracker, "log_debug", lambda *_, **__: None)
    monkeypatch.setattr(tracker, "check_price_plausibility", lambda *_, **__: {"plausible": True})

    mt = tracker.MarketTracker(debug=False)
    mt._baseline_initialized = True
    mt._request_immediate_rescan = 0
    return mt, saved_rows


def test_extract_buy_ui_metrics_handles_spacers():
    mt = tracker.MarketTracker(debug=False)
    sample = (
        "Central Market @ Buy Warehouse Balance 17,441,634,889 "
        "298 ECCO 1494 Monk's Branch Orders 1000 Orders Completed ： 5 Collect 891 22,387,500 Re-list"
    )

    metrics = mt._extract_buy_ui_metrics(sample)
    key = "monk's branch"
    assert key in metrics, f"Expected '{key}' in metrics, got {metrics}"
    entry = metrics[key]
    assert entry["orders"] == 1000
    assert entry["ordersCompleted"] == 5
    assert entry["remainingPrice"] == 22_387_500


def test_ui_inference_emits_collect_transaction(monkeypatch):
    mt, saved_rows = _prepare_tracker(monkeypatch)
    monkeypatch.setattr(tracker, "get_item_price_range_by_name", lambda *_, **__: {"base_price": 112_500})
    monkeypatch.setattr(tracker.MarketTracker, "_valid_item_name", lambda self, name: True)

    prev_metrics = {
        "monk's branch": {
            "item": "Monk's Branch",
            "orders": 1000,
            "ordersCompleted": 0,
            "remainingPrice": 0,
        }
    }
    mt._last_ui_buy_metrics = prev_metrics
    now = datetime.datetime.now()
    ts_text = now.strftime("%Y.%m.%d %H.%M")
    ocr_text = (
        "Central Market @ Buy Warehouse Balance 17,441,634,889 "
        f"{ts_text} Placed order of Monk's Branch x5 for 562,500 Silver "
        "Monk's Branch Orders 1000 Orders Completed 5 Collect 562,500 Re-list"
    )

    mt.process_ocr_text(ocr_text)

    inferred = [
        row for row in saved_rows
        if row[0] == "Monk's Branch"
        and row[1] == 5
        and row[2] == 562_500
        and row[3] == "buy"
        and row[5] == "collect_ui_inferred"
    ]
    assert inferred, f"Expected synthetic collect transaction, got {saved_rows}"


def test_sell_price_reconstruction_from_hint(monkeypatch):
    mt, saved_rows = _prepare_tracker(monkeypatch)
    monkeypatch.setattr(tracker, "get_item_price_range_by_name", lambda *_, **__: {"base_price": 3_510_000_000})
    monkeypatch.setattr(tracker.MarketTracker, "_get_base_price", lambda self, item: 3_510_000_000)
    monkeypatch.setattr(tracker.MarketTracker, "_valid_item_name", lambda self, name: True)
    monkeypatch.setattr(utils, "get_item_likely_type", lambda name: "sell" if "Exalted Soul Fragment" in name else "sell")

    now = datetime.datetime.now()
    ts_text = now.strftime("%Y.%m.%d %H.%M")
    ocr_text = (
        "Central Market Warehouse Balance 17,441,634,889 "
        f"{ts_text} Transaction of Exalted Soul Fragment x1 worth 052,140,000 Silver has been completed"
    )

    mt.process_ocr_text(ocr_text)

    reconstructed = [
        row for row in saved_rows
        if row[0] == "Exalted Soul Fragment"
        and row[1] == 1
        and row[2] == 3_052_140_000
        and row[3] == "sell"
    ]
    assert reconstructed, f"Expected reconstructed sell price, got {saved_rows}"


def test_first_snapshot_preserves_multiple_transactions(monkeypatch):
    mt, saved_rows = _prepare_tracker(monkeypatch)
    monkeypatch.setattr(tracker, "get_item_price_range_by_name", lambda *_, **__: {"base_price": 730_000_000})
    monkeypatch.setattr(tracker.MarketTracker, "_valid_item_name", lambda self, name: True)
    monkeypatch.setattr(tracker, "correct_item_name", lambda name, min_score=86: name)
    mt._baseline_initialized = False
    mt.last_overview_text = ""
    mt.last_processed_game_ts = None

    first_snapshot_text = (
        "Central Market @ Buy Warehouse Balance 15,432,522,389 "
        "2025.10.18 17.44 Placed order of Trace of Nature x5,000 for 730,000,000 Silver "
        "Transaction of Trace of Nature x5,000 worth 730,000,000 Silver has been completed "
        "2025.10.18 17.46 Placed order of Trace of Nature x5,000 for 740,000,000 Silver "
        "Transaction of Trace of Nature x5,000 worth 740,000,000 Silver has been completed "
        "Warehouse Capacity 6,976.8 11,000 VT"
    )

    mt.process_ocr_text(first_snapshot_text)

    assert len(saved_rows) == 2, f"Expected both historical and current transactions, got {saved_rows}"
    timestamps = sorted(row[4] for row in saved_rows)
    assert timestamps == ["2025-10-18 17:44:00", "2025-10-18 17:46:00"]

    # Subsequent scan should not duplicate entries
    mt.process_ocr_text(first_snapshot_text)
    assert len(saved_rows) == 2, "Entries should not duplicate on subsequent scans"
