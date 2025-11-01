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

    tracker._detail_cached_input_fields = {'quantity': 10, 'price': 448_000_000}
    tracker._detail_cached_input_timestamp = datetime.datetime(2025, 10, 27, 18, 39, 55)

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

    assert tracker.store_transaction_db.call_count >= 1

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


def test_apply_relist_side_effects_legacy_record(monkeypatch, tracker_with_mocks):
    tracker = tracker_with_mocks
    tracker._relist_side_effect_signatures.clear()
    pm = tracker._preorder_manager
    pm.reset_mock()

    pm.find_matching_preorder.return_value = None
    pm.record_legacy_preorder.return_value = 101
    pm.store_preorder.return_value = 202

    ui_orders_completed = 33
    tx_timestamp = datetime.datetime(2025, 10, 31, 12, 35, 25)

    tracker._detail_cached_input_fields = {'quantity': 50, 'price': 1_320_000_000}
    tracker._detail_cached_input_timestamp = tx_timestamp

    tx_payload = {
        'item_name': 'Crystallized Despair',
        'quantity': 33,
        'price': 871_200_000,
        'timestamp': tx_timestamp,
        'transaction_type': 'buy',
        '_pending_relist': {
            'tx_item': 'Crystallized Despair',
            'tx_qty': 33,
            'tx_price': 871_200_000,
            'tx_timestamp': tx_timestamp,
            'tx_type': 'buy',
            'listed_entry': None,
            'placed_entry': {'qty': 50, 'price': 1_320_000_000},
            'ui_orders_completed': ui_orders_completed,
        },
    }

    tracker._apply_relist_side_effects(tx_payload)

    pm.find_matching_preorder.assert_called_once()
    pm.record_legacy_preorder.assert_called_once_with(
        item_name='Crystallized Despair',
        quantity=33,
        price=871_200_000,
        collected_at=tx_timestamp,
        status='collected',
    )
    pm.update_quantity_filled.assert_not_called()
    pm.store_preorder.assert_called_once_with(
        'Crystallized Despair',
        50,
        1_320_000_000,
        tx_timestamp,
    )
    assert tracker._detail_cached_input_fields is None
    assert tracker._detail_cached_input_timestamp is None


def test_apply_relist_side_effects_no_payload(tracker_with_mocks):
    tracker = tracker_with_mocks
    tracker._preorder_manager.reset_mock()

    tracker._apply_relist_side_effects({'item_name': 'Gem of Void'})

    tracker._preorder_manager.find_matching_preorder.assert_not_called()
    tracker._preorder_manager.store_preorder.assert_not_called()
    tracker._preorder_manager.mark_collected.assert_not_called()


def test_sync_preorder_fill_from_ui_updates_once():
    tracker = MarketTracker(debug=False)
    tracker._preorder_manager = MagicMock()
    tracker._safe_correct_item_name = MagicMock(side_effect=lambda raw, min_score=80: (raw, True))

    metrics_entry = {
        "item": "Crystallized Despair",
        "ordersCompleted": 2,
    }

    tracker._preorder_manager.update_quantity_filled_by_item.return_value = True

    tracker._sync_preorder_fill_from_ui(metrics_entry, 2, 'crystallized despair')

    tracker._preorder_manager.update_quantity_filled_by_item.assert_called_once_with(
        "Crystallized Despair", 2
    )

    # Wiederholung mit gleichem Wert darf keinen zweiten Aufruf auslösen
    tracker._sync_preorder_fill_from_ui(metrics_entry, 2, 'crystallized despair')
    assert tracker._preorder_manager.update_quantity_filled_by_item.call_count == 1

    # Höherer Wert aktualisiert erneut
    tracker._sync_preorder_fill_from_ui(metrics_entry, 3, 'crystallized despair')
    tracker._preorder_manager.update_quantity_filled_by_item.assert_called_with(
        "Crystallized Despair", 3
    )
    assert tracker._preorder_manager.update_quantity_filled_by_item.call_count == 2


def test_check_for_autocollect_uses_ui_fallback(monkeypatch):
    tracker = MarketTracker(debug=False)
    tracker._preorder_manager = MagicMock()
    tracker._get_base_price = MagicMock(return_value=None)

    pm = tracker._preorder_manager
    pm.update_quantity_filled_by_item.return_value = True
    pm.find_matching_preorder.return_value = None
    pm.get_active_preorders.return_value = [
        {
            "id": 77,
            "item_name": "Crystallized Despair",
            "quantity": 47,
            "quantity_filled": 0,
            "price": 2_585_000_000,
            "timestamp": datetime.datetime(2025, 11, 1, 12, 0, 0),
        }
    ]

    ts = datetime.datetime(2025, 11, 1, 12, 0, 5)
    result = tracker._check_for_preorder_autocollect(
        item_name="Crystallized Despair",
        warehouse_delta=4,
        balance_delta=-110_000_000,
        timestamp=ts,
        fallback_unit_price=55_000_000,
        fallback_qty=None,
        fallback_autocollect_qty=2,
    )

    pm.update_quantity_filled_by_item.assert_called_once_with("Crystallized Despair", 2)
    assert result is not None
    assert result["quantity_filled"] == 2
    assert result["quantity"] == 47
    assert "_auto_collect_estimate" in result
