import datetime
import sys
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from ._stubs import install_dependency_stubs  # type: ignore
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).parent))
    from _stubs import install_dependency_stubs  # type: ignore

install_dependency_stubs()

import tracker  # noqa: E402
import pytest


@pytest.fixture(autouse=True)
def _patch_price_checks(monkeypatch):
    monkeypatch.setattr(tracker, "check_price_plausibility", lambda *args, **kwargs: {"plausible": True})
    monkeypatch.setattr(tracker.MarketTracker, "_is_unit_price_plausible", lambda self, *_args, **_kwargs: True)


def test_recover_buy_price_from_hint():
    mt = tracker.MarketTracker(debug=False)
    ts = datetime.datetime(2025, 10, 18, 23, 37)

    transaction_entry = {
        "raw": "Transaction of Black Stone Powder x1,111 worth 688,420 Silver",
        "raw_price_hint": 688420,
    }
    raw_related = [
        {"type": "transaction", "raw_price_hint": 688420},
        {"type": "placed", "price": 4_499_550, "qty": 1111},
    ]

    recovered = mt._recover_buy_price(
        "Black Stone Powder",
        1111,
        4_499_550,
        transaction_entry,
        raw_related,
    )
    assert recovered == 4_688_420


def test_process_image_skips_duplicate_with_hint(monkeypatch):
    saved: list[dict[str, Any]] = []
    state_store: dict[str, str] = {}

    class _Cursor:
        def __init__(self) -> None:
            self._sql = ""

        def execute(self, sql: str, params: Optional[tuple] = None) -> "_Cursor":
            self._sql = sql.lower()
            return self

        def fetchone(self) -> Optional[tuple[Any, ...]]:
            if "select count(*) from transactions" in self._sql:
                return (len(saved),)
            return None

        def fetchall(self) -> list[Any]:
            return []

    class _Conn:
        def commit(self) -> None:
            pass

    def fake_get_cursor():
        return _Cursor()

    def fake_get_connection():
        return _Conn()

    def fake_save_state(key: str, value: str) -> None:
        state_store[key] = value

    def fake_load_state(key: str, default=None):
        return state_store.get(key, default)

    def fake_correct_item_name(name, min_score=86):
        return name

    def fake_detect_window_type(_text: str) -> str:
        return "buy_overview"

    def fake_detect_tab(_text: str) -> str:
        return "buy"

    saved_occurrence = {}

    def fake_fetch_occurrence_indices(item, qty, price, ttype, timestamp):
        key = (item, qty, price, ttype, timestamp)
        return saved_occurrence.get(key, [])

    def fake_transaction_exists_exact(item, qty, price, ttype, timestamp, occurrence_index):
        for entry in saved:
            if (
                entry["item_name"] == item
                and entry["quantity"] == qty
                and entry["price"] == price
                and entry["transaction_type"] == ttype
                and entry["timestamp"] == timestamp
                and entry.get("occurrence_index", 0) == occurrence_index
            ):
                return True
        return False

    def fake_transaction_exists_any_side(item, qty, price, timestamp):
        for entry in saved:
            if (
                entry["item_name"] == item
                and entry["quantity"] == qty
                and entry["timestamp"] == timestamp
                and entry["price"] == price
            ):
                return True
        return False

    def fake_find_existing_tx_by_values(item, qty, price, ttype, timestamp=None, occurrence_index: int | None = None):
        for entry in saved:
            if (
                entry["item_name"] == item
                and entry["quantity"] == qty
                and entry["price"] == price
                and entry["transaction_type"] == ttype
            ):
                return (1, timestamp or entry["timestamp"], occurrence_index or entry.get("occurrence_index", 0))
        return None

    def fake_store(self, tx: dict[str, Any]) -> bool:
        key = (
            tx["item_name"],
            tx["quantity"],
            tx["price"],
            tx["transaction_type"],
            tx["timestamp"],
        )
        if any(
            entry["item_name"] == tx["item_name"]
            and entry["quantity"] == tx["quantity"]
            and entry["timestamp"] == tx["timestamp"]
            and entry["price"] == tx["price"]
            for entry in saved
        ):
            return False
        saved.append(tx.copy())
        saved_occurrence.setdefault(key, []).append(tx.get("occurrence_index", 0))
        return True

    monkeypatch.setattr(tracker, "get_cursor", fake_get_cursor)
    monkeypatch.setattr(tracker, "get_connection", fake_get_connection)
    monkeypatch.setattr(tracker, "save_state", fake_save_state)
    monkeypatch.setattr(tracker, "load_state", fake_load_state)
    monkeypatch.setattr(tracker, "correct_item_name", fake_correct_item_name)
    monkeypatch.setattr(tracker, "detect_window_type", fake_detect_window_type)
    monkeypatch.setattr(tracker, "detect_tab_from_text", fake_detect_tab)
    monkeypatch.setattr(tracker, "fetch_occurrence_indices", fake_fetch_occurrence_indices)
    monkeypatch.setattr(tracker, "transaction_exists_exact", fake_transaction_exists_exact)
    monkeypatch.setattr(tracker, "transaction_exists_any_side", fake_transaction_exists_any_side)
    monkeypatch.setattr(tracker, "find_existing_tx_by_values", fake_find_existing_tx_by_values)
    monkeypatch.setattr(tracker.MarketTracker, "store_transaction_db", fake_store)
    monkeypatch.setattr(tracker, "transaction_exists_by_values_near_time", lambda *args, **kwargs: False)
    monkeypatch.setattr(tracker, "update_tx_timestamp_if_earlier", lambda *args, **kwargs: False)

    usage_count: dict[str, int] = {}
    ts = datetime.datetime(2025, 10, 18, 23, 37)
    sequence_map = {
        "scan-1": [
            {
                "type": "transaction",
                "item": "Black Stone Powder",
                "qty": 1111,
                "price": 4_688_420,
                "timestamp": ts,
                "raw": "",
                "raw_price_hint": None,
            },
            {
                "type": "placed",
                "item": "Black Stone Powder",
                "qty": 1111,
                "price": 4_499_550,
                "timestamp": ts,
                "raw": "",
                "raw_price_hint": None,
            },
        ],
        "scan-2": [
            {
                "type": "transaction",
                "item": "Black Stone Powder",
                "qty": 1111,
                "price": None,
                "timestamp": ts,
                "raw": "Transaction of Black Stone Powder x1,111 worth 688,420 Silver",
                "raw_price_hint": 688420,
            },
            {
                "type": "placed",
                "item": "Black Stone Powder",
                "qty": 1111,
                "price": 4_499_550,
                "timestamp": ts,
                "raw": "",
                "raw_price_hint": None,
            },
        ],
    }
    current_entries: list[dict[str, Any]] = []

    def fake_split(_text: str):
        usage = usage_count.get(_text, 0)
        usage_count[_text] = usage + 1
        dataset = sequence_map.get(_text)
        if not dataset or usage > 0:
            current_entries.clear()
            return []
        current = [dict(entry) for entry in dataset]
        current_entries.clear()
        current_entries.extend(current)
        return [(i, "", "") for i in range(len(current))]

    def fake_extract(_ts_text: str, _snippet: str):
        return current_entries.pop(0)

    monkeypatch.setattr(tracker, "split_text_into_log_entries", fake_split)
    monkeypatch.setattr(tracker, "extract_details_from_entry", fake_extract)

    mt = tracker.MarketTracker(debug=False)

    mt.process_ocr_text("scan-1")
    assert saved, "expected first snapshot to persist a Black Stone Powder transaction"
    mt.process_ocr_text("scan-2")

    prices = [entry["price"] for entry in saved if entry["item_name"] == "Black Stone Powder"]
    assert prices == [4_688_420]
