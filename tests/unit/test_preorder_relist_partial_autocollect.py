import datetime
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from ._stubs import install_dependency_stubs  # type: ignore
except ImportError:  # pragma: no cover - safety net for direct execution
    sys.path.insert(0, str(Path(__file__).parent))
    from _stubs import install_dependency_stubs  # type: ignore

install_dependency_stubs()

from tracker import MarketTracker  # noqa: E402


@pytest.fixture()
def tracker_with_mocks():
    tracker = MarketTracker(debug=False)
    tracker.store_transaction_db = MagicMock(return_value=True)
    tracker._preorder_manager = MagicMock()
    tracker._safe_correct_item_name = MagicMock(return_value=("Gem of Void", True))
    tracker._preorder_manager.store_preorder.return_value = 42
    tracker._preorder_manager.find_matching_preorder.return_value = {
        "id": 41,
        "item_name": "Gem of Void",
        "quantity": 10,
        "quantity_filled": 3,
        "price": 448_000_000,
        "timestamp": datetime.datetime(2025, 10, 27, 18, 39, 55),
    }
    return tracker


def _install_metric_sequence(tracker: MarketTracker, metrics_sequence: list[dict]):
    """Patch _extract_detail_window_metrics to replay a metric sequence."""

    sequence = metrics_sequence.copy()

    def _next(*_args, **_kwargs):
        if len(sequence) > 1:
            return sequence.pop(0)
        return sequence[0]

    tracker._extract_detail_window_metrics = MagicMock(side_effect=_next)


def test_relist_partial_autocollect_handles_missing_warehouse(monkeypatch, tracker_with_mocks):
    tracker = tracker_with_mocks

    baseline_balance = 7_200_000_000

    metrics_sequence = [
        {
            "balance": baseline_balance,
            "warehouse_qty": None,
            "item_name": "Gem of Void",
        },
        {
            "balance": baseline_balance - 448_000_000,
            "warehouse_qty": None,
            "item_name": "Gem of Void",
        },
        {
            "balance": baseline_balance - 448_000_000,
            "warehouse_qty": 3,
            "item_name": "Gem of Void",
        },
    ]
    _install_metric_sequence(tracker, metrics_sequence)

    fixed_ts = datetime.datetime(2025, 10, 27, 18, 39, 56)
    monkeypatch.setattr(datetime, "datetime", MagicMock(now=MagicMock(return_value=fixed_ts)))

    tracker._monitor_detail_window("buy_item", "frame-0")
    tracker._monitor_detail_window("buy_item", "frame-1")
    tracker._monitor_detail_window("buy_item", "frame-2")

    assert tracker.store_transaction_db.call_count == 10

    buy_collect_calls = [
        call.args[0]
        for call in tracker.store_transaction_db.call_args_list
        if call.args and call.args[0].get("tx_case") == "buy_collect"
    ]
    assert buy_collect_calls, "Es wurde keine Auto-Collect-Transaktion gespeichert"

    auto_collect_tx = buy_collect_calls[-1]
    assert auto_collect_tx["item_name"] == "Gem of Void"
    assert auto_collect_tx["quantity"] == 3
    assert auto_collect_tx["price"] == 134_400_000

    tracker._preorder_manager.mark_collected.assert_called_once()
    tracker._preorder_manager.store_preorder.assert_called_once()

    preorder_kwargs = tracker._preorder_manager.store_preorder.call_args.kwargs
    assert preorder_kwargs["item_name"] == "Gem of Void"
    assert preorder_kwargs["quantity"] == 10
    assert preorder_kwargs["price"] == 448_000_000


def test_apply_relist_side_effects_idempotent(tracker_with_mocks):
    tracker = tracker_with_mocks
    tracker._relist_side_effect_signatures.clear()
    tracker._preorder_manager.reset_mock()
    tracker._preorder_manager.find_matching_preorder.return_value = {
        "id": 51,
        "item_name": "Gem of Void",
    }

    tx_payload = {
        'item_name': 'Gem of Void',
        'quantity': 10,
        'price': 448_000_000,
        'timestamp': datetime.datetime(2025, 10, 27, 18, 45, 0),
        'transaction_type': 'buy',
        'occurrence_index': None,
        '_pending_relist': {
            'tx_item': 'Gem of Void',
            'tx_qty': 10,
            'tx_price': 448_000_000,
            'tx_timestamp': datetime.datetime(2025, 10, 27, 18, 45, 0),
            'tx_type': 'buy',
            'placed_entry': {'qty': 10, 'price': 448_000_000},
            'listed_entry': None,
        },
    }

    tracker._apply_relist_side_effects(tx_payload)
    tracker._apply_relist_side_effects(tx_payload)

    tracker._preorder_manager.find_matching_preorder.assert_called_once()
    tracker._preorder_manager.store_preorder.assert_called_once()
    tracker._preorder_manager.mark_collected.assert_called_once()


def test_apply_relist_side_effects_no_payload(tracker_with_mocks):
    tracker = tracker_with_mocks
    tracker._preorder_manager.reset_mock()

    tracker._apply_relist_side_effects({'item_name': 'Gem of Void'})

    tracker._preorder_manager.find_matching_preorder.assert_not_called()
    tracker._preorder_manager.store_preorder.assert_not_called()
    tracker._preorder_manager.mark_collected.assert_not_called()
