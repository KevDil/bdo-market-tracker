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


TEXT_NO_ANCHOR = """
Central Market Warehouse Balance 14,940,283,614 2025.10.18 18.51
Sealed Black Magic Crystal Orders 876 Orders Completed 524 Collect 696,000,000 Re-list
"""

TEXT_WITH_ANCHOR = """
Central Market Warehouse Balance 14,940,283,614 2025.10.18 18.51
2025.10.18 18.51 Placed order of Sealed Black Magic Crystal x876 for 2,628,000,000 Silver
2025.10.18 18.51 Withdrew order of Sealed Black Magic Crystal x232 for 696,000,000 Silver
Sealed Black Magic Crystal Orders 876 Orders Completed 524 Collect 696,000,000 Re-list
"""

REAL_TRANSACTION_TEXT = """
Central Market Warehouse Balance 14,940,283,614 2025.10.18 18.51
2025.10.18 18.51 Placed order of Sealed Black Magic Crystal x876 for 2,628,000,000 Silver
2025.10.18 18.51 Withdrew order of Sealed Black Magic Crystal x232 for 696,000,000 Silver
2025.10.18 18.51 Transaction of Sealed Black Magic Crystal x524 worth 1,572,000,000 Silver has been completed
Sealed Black Magic Crystal Orders 876 Orders Completed 524 Collect 696,000,000 Re-list
"""


class _FakeConnection:
    def commit(self) -> None:  # pragma: no cover - trivial
        pass


def _bootstrap_tracker(monkeypatch, saved_rows: list[dict[str, Any]]) -> tracker.MarketTracker:
    state_store: dict[str, str] = {}

    monkeypatch.setattr(tracker, "get_cursor", lambda: None)
    monkeypatch.setattr(tracker, "get_connection", lambda: _FakeConnection())
    monkeypatch.setattr(tracker, "save_state", lambda key, value: state_store.__setitem__(key, value))
    monkeypatch.setattr(tracker, "load_state", lambda key, default=None: state_store.get(key, default))
    monkeypatch.setattr(tracker, "fetch_occurrence_indices", lambda *_, **__: [])
    monkeypatch.setattr(tracker, "transaction_exists_exact", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "transaction_exists_any_side", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "transaction_exists_by_values_near_time", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "find_existing_tx_by_values", lambda *_, **__: None)
    monkeypatch.setattr(tracker, "update_tx_timestamp_if_earlier", lambda *_, **__: False)
    monkeypatch.setattr(tracker, "check_price_plausibility", lambda *_, **__: {"plausible": False, "reason": "too_low", "expected_min": 1_300_000_000, "expected_max": 1_900_000_000})
    monkeypatch.setattr(tracker, "correct_item_name", lambda name, min_score=86: name)
    monkeypatch.setattr(tracker.MarketTracker, "_valid_item_name", lambda self, name: True)
    monkeypatch.setattr(tracker.MarketTracker, "_is_unit_price_plausible", lambda self, *_: True)
    monkeypatch.setattr(tracker.MarketTracker, "_get_base_price", lambda self, name: 3_000_000)
    monkeypatch.setattr(tracker, "log_debug", lambda *_, **__: None)
    monkeypatch.setattr(tracker, "detect_window_type", lambda *_: "buy_overview")
    monkeypatch.setattr(tracker, "detect_tab_from_text", lambda *_: "buy")

    fixed_now = datetime.datetime(2025, 10, 18, 18, 51, 5)

    class _FixedDatetime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):  # pragma: no cover - deterministic helper
            return fixed_now.replace(tzinfo=tz)

    monkeypatch.setattr(tracker.datetime, "datetime", _FixedDatetime)

    def fake_store(self, tx: dict[str, Any]) -> bool:
        saved_rows.append(tx.copy())
        return True

    monkeypatch.setattr(tracker.MarketTracker, "store_transaction_db", fake_store)

    mt = tracker.MarketTracker(debug=False)
    mt.last_overview_text = ""
    return mt


def test_ui_infer_requires_anchor(monkeypatch):
    saved: list[dict[str, Any]] = []
    mt = _bootstrap_tracker(monkeypatch, saved)
    mt._baseline_initialized = False

    mt.process_ocr_text(TEXT_NO_ANCHOR)

    assert not saved, "UI inference ohne Anker darf keine Transaktion speichern"


def test_ui_infer_with_anchor_reconstructs_price(monkeypatch):
    saved: list[dict[str, Any]] = []
    mt = _bootstrap_tracker(monkeypatch, saved)
    mt._baseline_initialized = False

    mt.process_ocr_text(TEXT_WITH_ANCHOR)

    assert len(saved) == 1, f"erwartete genau einen UI-Eintrag, erhielt {len(saved)}"
    tx = saved[0]
    assert tx["item_name"] == "Sealed Black Magic Crystal"
    assert tx["quantity"] == 524
    assert tx["price"] == 1_572_000_000, f"rekonstruierter Preis falsch: {tx['price']}"
    assert isinstance(tx["timestamp"], datetime.datetime)
    assert tx["timestamp"] == datetime.datetime(2025, 10, 18, 18, 51, 0)
    assert tx.get("_ui_inferred") is True

    saved.clear()
    mt.process_ocr_text(REAL_TRANSACTION_TEXT)

    assert len(saved) == 1, "echter Logeintrag sollte separat gespeichert werden"
    real_tx = saved[0]
    assert real_tx["transaction_type"] == "buy"
    assert real_tx["price"] == 1_572_000_000

