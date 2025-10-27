"""
Test Suite: Accumulated Purchase Validation
===========================================

Tests the increased validation limit (500000) for accumulated purchases
that occur when BDO batches multiple rapid purchases into a single UI delta.

Scenario: User rapidly purchases 5x 5000 Lion Blood
- BDO batches UI updates → single +25000 warehouse delta
- Detail-window monitoring accumulates partial deltas
- Validation should accept quantities up to 500000
- Log warning for quantities > 5000
"""

import sys
import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from ._stubs import install_dependency_stubs  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from _stubs import install_dependency_stubs  # type: ignore

install_dependency_stubs()

from tracker import MarketTracker  # noqa: E402


class TestAccumulatedPurchases:
    """
    Test accumulated purchase validation with increased limit.
    """
    
    @pytest.fixture
    def tracker(self):
        """Create tracker with debug enabled."""
        tracker = MarketTracker()
        tracker.debug = True
        return tracker
    
    def test_single_purchase_5000_accepted(self, tracker):
        """
        Einzelkauf 5000x wird akzeptiert (normale Obergrenze).
        """
        # Setup: Detail-Fenster aktiv, Baseline gesetzt, partial deltas initialisiert
        tracker._detail_window_active = 'buy_item'
        tracker._detail_window_item = 'Lion Blood'
        tracker._detail_baseline_balance = 200_000_000_000
        tracker._detail_baseline_warehouse = 15_000
        tracker._detail_partial_balance_delta = 0
        tracker._detail_partial_warehouse_delta = 0
        
        # Simuliere Delta: 1x 5000 Kauf
        current_metrics = {
            'balance': 200_000_000_000 - 95_500_000,  # -95.5M (5000x @ 19100 ea)
            'warehouse': 15_000 + 5_000,  # +5000
            'item_name': 'Lion Blood'
        }
        
        balance_delta = -95_500_000
        warehouse_delta = 5_000
        
        with patch('tracker.correct_item_name', return_value=('Lion Blood', False)):
            transaction = tracker._infer_transaction_from_deltas(
                window_type='buy_item',
                balance_delta=balance_delta,
                warehouse_delta=warehouse_delta,
                current_metrics=current_metrics,
                last_metrics=None
            )
        
        # Verify
        assert transaction is not None
        assert transaction['quantity'] == 5000
        assert transaction['item_name'] == 'Lion Blood'
        assert transaction['transaction_type'] == 'buy'
        assert transaction['tx_case'] == 'buy_collect_ui_inferred'  # Detail-Window Delta-Inferenz
    
    def test_accumulated_purchase_25000_accepted(self, tracker):
        """
        Akkumulierter Kauf 25000x (5x 5000) wird akzeptiert mit Warnung.
        """
        # Setup: Detail-Fenster aktiv, Baseline gesetzt, partial deltas initialisiert
        tracker._detail_window_active = 'buy_item'
        tracker._detail_window_item = 'Lion Blood'
        tracker._detail_baseline_balance = 200_000_000_000
        tracker._detail_baseline_warehouse = 15_000
        tracker._detail_partial_balance_delta = 0
        tracker._detail_partial_warehouse_delta = 0
        
        # Simuliere Delta: 5x 5000 Käufe (batched by BDO)
        current_metrics = {
            'balance': 200_000_000_000 - 477_500_000,  # -477.5M (25000x @ 19100 ea)
            'warehouse': 15_000 + 25_000,  # +25000
            'item_name': 'Lion Blood'
        }
        
        balance_delta = -477_500_000
        warehouse_delta = 25_000
        
        with patch('tracker.correct_item_name', return_value=('Lion Blood', False)):
            transaction = tracker._infer_transaction_from_deltas(
                window_type='buy_item',
                balance_delta=balance_delta,
                warehouse_delta=warehouse_delta,
                current_metrics=current_metrics,
                last_metrics=None
            )
        
        # Verify
        assert transaction is not None
        assert transaction['quantity'] == 25000
        assert transaction['item_name'] == 'Lion Blood'
        assert transaction['transaction_type'] == 'buy'
        assert transaction['tx_case'] == 'buy_collect_ui_inferred'  # Detail-Window Delta-Inferenz
    
    def test_accumulated_purchase_100000_accepted(self, tracker):
        """
        Großer akkumulierter Kauf 100000x (20x 5000) wird akzeptiert.
        """
        # Setup: partial deltas initialisiert
        tracker._detail_window_active = 'buy_item'
        tracker._detail_window_item = 'Concentrated Magical Black Stone (Weapon)'
        tracker._detail_baseline_balance = 500_000_000_000
        tracker._detail_baseline_warehouse = 10_000
        tracker._detail_partial_balance_delta = 0
        tracker._detail_partial_warehouse_delta = 0
        
        # Simuliere Delta: 20x 5000 Käufe
        current_metrics = {
            'balance': 500_000_000_000 - 28_500_000_000,  # -28.5B (100000x @ 285k ea)
            'warehouse': 10_000 + 100_000,  # +100000
            'item_name': 'Concentrated Magical Black Stone (Weapon)'
        }
        
        balance_delta = -28_500_000_000
        warehouse_delta = 100_000
        
        with patch('tracker.correct_item_name', return_value=('Concentrated Magical Black Stone (Weapon)', False)):
            transaction = tracker._infer_transaction_from_deltas(
                window_type='buy_item',
                balance_delta=balance_delta,
                warehouse_delta=warehouse_delta,
                current_metrics=current_metrics,
                last_metrics=None
            )
        
        # Verify
        assert transaction is not None
        assert transaction['quantity'] == 100000
        assert transaction['item_name'] == 'Concentrated Magical Black Stone'  # Normalisiert durch correct_item_name
    
    def test_max_limit_500000_accepted(self, tracker):
        """
        Maximum Limit 500000x wird akzeptiert.
        """
        # Setup: partial deltas initialisiert
        tracker._detail_window_active = 'buy_item'
        tracker._detail_window_item = 'Pure Powder Reagent'
        tracker._detail_baseline_balance = 1_000_000_000_000
        tracker._detail_baseline_warehouse = 50_000
        tracker._detail_partial_balance_delta = 0
        tracker._detail_partial_warehouse_delta = 0
        
        # Simuliere Delta: 100x 5000 Käufe (maximale akkumulierte Menge)
        current_metrics = {
            'balance': 1_000_000_000_000 - 75_000_000_000,  # -75B (500000x @ 150k ea)
            'warehouse': 50_000 + 500_000,  # +500000
            'item_name': 'Pure Powder Reagent'
        }
        
        balance_delta = -75_000_000_000
        warehouse_delta = 500_000
        
        with patch('tracker.correct_item_name', return_value=('Pure Powder Reagent', False)):
            transaction = tracker._infer_transaction_from_deltas(
                window_type='buy_item',
                balance_delta=balance_delta,
                warehouse_delta=warehouse_delta,
                current_metrics=current_metrics,
                last_metrics=None
            )
        
        # Verify
        assert transaction is not None
        assert transaction['quantity'] == 500000
        assert transaction['item_name'] == 'Pure Powder Reagent'
    
    def test_over_limit_500001_rejected(self, tracker):
        """
        Über Limit 500001x wird abgelehnt (Schutz vor unrealistischen Werten).
        """
        # Setup
        tracker._detail_window_active = 'buy_item'
        tracker._detail_window_item = 'Pure Powder Reagent'
        tracker._detail_baseline_balance = 1_000_000_000_000
        tracker._detail_baseline_warehouse = 50_000
        
        # Simuliere Delta: unrealistische Menge
        current_metrics = {
            'balance': 1_000_000_000_000 - 100_000_000_000,
            'warehouse': 50_000 + 500_001,  # +500001 (über Limit!)
            'item_name': 'Pure Powder Reagent'
        }
        
        balance_delta = -100_000_000_000
        warehouse_delta = 500_001
        
        with patch('tracker.correct_item_name', return_value=('Pure Powder Reagent', False)):
            transaction = tracker._infer_transaction_from_deltas(
                window_type='buy_item',
                balance_delta=balance_delta,
                warehouse_delta=warehouse_delta,
                current_metrics=current_metrics,
                last_metrics=None
            )
        
        # Verify: Sollte abgelehnt werden
        assert transaction is None
    
    def test_partial_delta_accumulation_with_new_limit(self, tracker):
        """
        Partial-Delta Accumulation funktioniert mit neuem Limit.
        Test: Balance kommt in Scan 1, Warehouse in Scan 2 → akkumuliert 25000x.
        """
        # Setup
        tracker._detail_window_active = 'buy_item'
        tracker._detail_window_item = 'Lion Blood'
        tracker._detail_baseline_balance = 200_000_000_000
        tracker._detail_baseline_warehouse = 15_000
        
        # Scan 1: Nur Balance-Delta
        current_metrics_1 = {
            'balance': 200_000_000_000 - 477_500_000,  # -477.5M
            'warehouse': 15_000,  # Noch kein Delta
            'item_name': 'Lion Blood'
        }
        
        balance_delta_1 = -477_500_000
        warehouse_delta_1 = 0
        
        with patch('tracker.correct_item_name', return_value=('Lion Blood', False)):
            transaction_1 = tracker._infer_transaction_from_deltas(
                window_type='buy_item',
                balance_delta=balance_delta_1,
                warehouse_delta=warehouse_delta_1,
                current_metrics=current_metrics_1,
                last_metrics=None
            )
        
        # Verify: Keine Transaktion (unvollständiges Delta)
        assert transaction_1 is None
        assert tracker._detail_partial_balance_delta == -477_500_000
        assert tracker._detail_partial_warehouse_delta == 0
        
        # Scan 2: Warehouse-Delta kommt an
        current_metrics_2 = {
            'balance': 200_000_000_000 - 477_500_000,  # Gleich
            'warehouse': 15_000 + 25_000,  # Jetzt Delta!
            'item_name': 'Lion Blood'
        }
        
        balance_delta_2 = 0  # Kein neues Balance-Delta
        warehouse_delta_2 = 25_000  # Warehouse-Delta jetzt da
        
        with patch('tracker.correct_item_name', return_value=('Lion Blood', False)):
            transaction_2 = tracker._infer_transaction_from_deltas(
                window_type='buy_item',
                balance_delta=balance_delta_2,
                warehouse_delta=warehouse_delta_2,
                current_metrics=current_metrics_2,
                last_metrics=current_metrics_1
            )
        
        # Verify: Transaktion mit akkumuliertem Delta
        assert transaction_2 is not None
        assert transaction_2['quantity'] == 25000
        assert transaction_2['item_name'] == 'Lion Blood'
        
        # Verify: Partial-Deltas wurden zurückgesetzt
        assert tracker._detail_partial_balance_delta == 0
        assert tracker._detail_partial_warehouse_delta == 0
    
    def test_zero_quantity_rejected(self, tracker):
        """
        Menge 0 wird abgelehnt (Untergrenze bleibt bei 1).
        """
        # Setup
        tracker._detail_window_active = 'buy_item'
        tracker._detail_window_item = 'Lion Blood'
        tracker._detail_baseline_balance = 200_000_000_000
        tracker._detail_baseline_warehouse = 15_000
        
        # Simuliere Delta mit 0 Warehouse-Delta (sollte nicht passieren, aber sicher ist sicher)
        current_metrics = {
            'balance': 200_000_000_000 - 100_000,
            'warehouse': 15_000,  # Kein Delta = 0 quantity
            'item_name': 'Lion Blood'
        }
        
        balance_delta = -100_000
        warehouse_delta = 0
        
        with patch('tracker.correct_item_name', return_value=('Lion Blood', False)):
            transaction = tracker._infer_transaction_from_deltas(
                window_type='buy_item',
                balance_delta=balance_delta,
                warehouse_delta=warehouse_delta,
                current_metrics=current_metrics,
                last_metrics=None
            )
        
        # Verify: Sollte abgelehnt werden (quantity=0 < 1)
        assert transaction is None
    
    def test_negative_quantity_rejected(self, tracker):
        """
        Negative Menge wird abgelehnt (sollte nicht passieren, aber Schutz nötig).
        """
        # Setup
        tracker._detail_window_active = 'buy_item'
        tracker._detail_window_item = 'Lion Blood'
        tracker._detail_baseline_balance = 200_000_000_000
        tracker._detail_baseline_warehouse = 15_000
        
        # Simuliere negativen Warehouse-Delta (bug in code?)
        current_metrics = {
            'balance': 200_000_000_000 - 100_000_000,
            'warehouse': 15_000 - 5000,  # Negatives Delta = -5000 quantity
            'item_name': 'Lion Blood'
        }
        
        balance_delta = -100_000_000
        warehouse_delta = -5000
        
        with patch('tracker.correct_item_name', return_value=('Lion Blood', False)):
            transaction = tracker._infer_transaction_from_deltas(
                window_type='buy_item',
                balance_delta=balance_delta,
                warehouse_delta=warehouse_delta,
                current_metrics=current_metrics,
                last_metrics=None
            )
        
        # Verify: Sollte abgelehnt werden (quantity=-5000 < 1)
        assert transaction is None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
