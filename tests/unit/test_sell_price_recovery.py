import datetime
import sys
from pathlib import Path

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
def _patch_defaults(monkeypatch):
    monkeypatch.setattr(tracker, "load_state", lambda key, default=None: default)
    monkeypatch.setattr(tracker, "save_state", lambda *args, **kwargs: None)


def _make_tracker(monkeypatch, base_price: int):
    mt = tracker.MarketTracker(debug=False)
    monkeypatch.setattr(mt, "_get_base_price", lambda _name: base_price)
    return mt


def test_recover_sell_price_prefers_ui_prefix_hint(monkeypatch):
    mt = _make_tracker(monkeypatch, base_price=18_400_000)
    entry = {
        "raw": (
            "Transaction of [Party] Harmony Draught - Demihuman x263 worth 4,270,245,5_ Silver"
        ),
        "type": "transaction",
    }
    entry["_ui_unit_price"] = 18_300_000

    recovered = mt._recover_sell_price(
        "[Party] Harmony Draught - Demihuman",
        263,
        None,
        entry,
    )

    assert recovered == 4_270_245_525
    assert entry.get("_price_hint_mode") == "prefix"


def test_recover_sell_price_uses_ui_for_missing_value(monkeypatch):
    mt = _make_tracker(monkeypatch, base_price=18_400_000)
    entry = {
        "raw": (
            "Transaction of [Party] Harmony Draught - Demihuman x97 worth 1,574,957,47_ Silver"
        ),
        "type": "transaction",
    }
    entry["_ui_unit_price"] = 18_300_000

    recovered = mt._recover_sell_price(
        "[Party] Harmony Draught - Demihuman",
        97,
        None,
        entry,
    )

    assert recovered == 1_574_957_475


def test_store_transaction_skips_near_time_duplicate(monkeypatch):
    mt = _make_tracker(monkeypatch, base_price=645_000)

    saved_rows: list[dict] = []

    class _Cursor:
        def __init__(self) -> None:
            self._last_select: list[tuple] | None = None
            self.rowcount = 0

        def execute(self, sql: str, params: tuple | None = None):
            self.rowcount = 0
            sql_norm = " ".join(sql.strip().split()).lower()
            if "select id, timestamp from transactions where content_hash" in sql_norm:
                self._last_select = []
            elif "insert or ignore into transactions" in sql_norm:
                item_name, quantity, price, ttype, ts_str, tx_case, occ_idx, content_hash = params  # type: ignore
                timestamp = datetime.datetime.fromisoformat(str(ts_str))
                saved_rows.append(
                    {
                        "item_name": item_name,
                        "quantity": quantity,
                        "price": price,
                        "transaction_type": ttype,
                        "timestamp": timestamp,
                        "tx_case": tx_case,
                        "occurrence_index": occ_idx,
                        "content_hash": content_hash,
                    }
                )
                self.rowcount = 1
            return self

        def fetchone(self):
            if self._last_select:
                return self._last_select[0]
            return None

        def fetchall(self):
            return []

    class _Conn:
        def commit(self) -> None:
            return None

    monkeypatch.setattr(tracker, "get_cursor", lambda: _Cursor())
    monkeypatch.setattr(tracker, "get_connection", lambda: _Conn())
    monkeypatch.setattr(tracker, "fetch_occurrence_indices", lambda *args, **kwargs: [])
    monkeypatch.setattr(tracker, "update_tx_timestamp_if_earlier", lambda *args, **kwargs: False)

    def fake_find_existing(item, qty, price, ttype, timestamp=None, occurrence_index=None):
        for row in saved_rows:
            if (
                row["item_name"] == item
                and row["quantity"] == qty
                and row["price"] == price
                and row["transaction_type"] == ttype
                and row["timestamp"].strftime("%Y-%m-%d %H:%M:%S") == str(timestamp)
            ):
                return (1, timestamp, occurrence_index or 0)
        return None

    def fake_exists_near_time(item, qty, price, timestamp, tolerance_minutes=5, ignore_quantity=False):
        if not isinstance(timestamp, datetime.datetime):
            timestamp = datetime.datetime.fromisoformat(str(timestamp))
        tolerance = datetime.timedelta(minutes=tolerance_minutes)
        for row in saved_rows:
            if row["item_name"] != item:
                continue
            if not ignore_quantity and row["quantity"] != qty:
                continue
            if row["price"] != price:
                continue
            if abs(row["timestamp"] - timestamp) <= tolerance:
                return True
        return False

    monkeypatch.setattr(tracker, "find_existing_tx_by_values", fake_find_existing)
    monkeypatch.setattr(tracker, "transaction_exists_by_values_near_time", fake_exists_near_time)

    ts_first = datetime.datetime(2025, 10, 19, 11, 23)
    tx = {
        "item_name": "Brutal Death Elixir",
        "quantity": 128,
        "price": 78_720_000,
        "transaction_type": "buy",
        "timestamp": ts_first,
        "case": "buy_collect",
        "occurrence_index": 0,
    }

    assert mt.store_transaction_db(tx.copy()) is True
    assert len(saved_rows) == 1

    ts_duplicate = ts_first + datetime.timedelta(minutes=3)
    tx_dup = {**tx, "timestamp": ts_duplicate}

    assert mt.store_transaction_db(tx_dup.copy()) is False
    assert len(saved_rows) == 1


def test_brutal_death_elixir_snapshot_classified_buy(monkeypatch):
    stored: list[dict] = []

    def fake_store(self, tx: dict) -> bool:  # pragma: no cover - simple lambda wrapper
        stored.append(tx.copy())
        return True

    monkeypatch.setattr(tracker.MarketTracker, "store_transaction_db", fake_store, raising=False)
    monkeypatch.setattr(tracker, "detect_window_type", lambda _text: "sell_overview")
    monkeypatch.setattr(tracker, "detect_tab_from_text", lambda _text: "sell")
    monkeypatch.setattr(tracker, "check_price_plausibility", lambda *args, **kwargs: {"plausible": True, "reason": "ok"})
    monkeypatch.setattr(tracker, "correct_item_name", lambda name, min_score=80: name)

    mt = tracker.MarketTracker(debug=False)

    def fake_base_price(name: str) -> int | None:
        if "Brutal Death Elixir" in name:
            return 645_000
        if "Harmony Draught" in name:
            return 18_300_000
        return 18_300_000

    monkeypatch.setattr(mt, "_get_base_price", fake_base_price)

    sample_text = (
        "Central Market @ Buy Warehouse Balance Utens- 66,673,516,797 2025.10.19 11.23 "
        "Transaction of Brutal Death Elixir x128 worth 78,720,000 Silver has been com_ "
        "Transaction of [Party] Harmony Draught Demihuman x263 worth 4,270,245,5_. "
        "Transaction of [Party] Harmony Draught - Edania x17 worth 269,990,175 Silver. "
        "Listed Magical Shard X2OO for 696,000,000 Silver. The price of enhancement m: 2025.10.19 11.23 "
        "Sell 'LMLiR Pearl Item Selling Limit 0 / 35 Sell Enter search term."
    )

    mt.process_ocr_text(sample_text)

    bde = next(tx for tx in stored if tx["item_name"] == "Brutal Death Elixir")
    assert bde["transaction_type"] == "buy"
