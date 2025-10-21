"""
Unit Tests für Pig Blood 3-Transaction-Bug Fix.

Testet die Smart Delta-Reset Logik und Warehouse-Baseline-Handling.
"""

import pytest
from tracker import MarketTracker
import datetime


class TestPigBloodFix:
    """Tests für Pig Blood Scenario Fixes."""

    def test_warehouse_baseline_none_handling(self):
        """
        Test: Warte auf vollständige Metriken bevor Baseline gesetzt wird.
        
        Scenario:
        1. Detail-Fenster öffnen mit Balance=X, Warehouse=None
        2. Warehouse erscheint später
        
        Expected: Baseline wird ERST gesetzt wenn beide Metriken vorhanden
        """
        tracker = MarketTracker(debug=True)
        
        # Scan 1: Nur Balance vorhanden
        tracker._extract_detail_window_metrics = lambda text, wtype: {
            'balance': 100000,
            'warehouse_qty': None,
            'item_name': 'Test Item'
        }
        
        ocr_text_1 = "Balance 100,000"
        tracker._monitor_detail_window('buy_item', ocr_text_1)
        
        # Erwartung: Window NICHT aktiv (warte auf Warehouse)
        assert tracker._detail_window_active == False
        assert tracker._detail_baseline_balance is None
        assert tracker._detail_baseline_warehouse is None
        
        # Scan 2: Warehouse erscheint
        tracker._extract_detail_window_metrics = lambda text, wtype: {
            'balance': 100000,
            'warehouse_qty': 5000,
            'item_name': 'Test Item'
        }
        
        ocr_text_2 = "Balance 100,000\nWarehouse 5,000"
        tracker._monitor_detail_window('buy_item', ocr_text_2)
        
        # Erwartung: Jetzt aktiv mit vollständiger Baseline
        assert tracker._detail_window_active == True
        assert tracker._detail_baseline_balance == 100000
        assert tracker._detail_baseline_warehouse == 5000

    def test_smart_delta_reset_on_new_transaction(self):
        """
        Test: Smart Reset wenn neue Transaction beginnt (beide Deltas ändern sich).
        
        Scenario:
        1. Balance -10k, Warehouse +0 → Akkumuliere
        2. Balance -20k, Warehouse +5000 → Neue TX erkannt, alte Akkumulation verwerfen
        
        Expected: Nur die neue Transaction wird erfasst, nicht die Summe
        """
        tracker = MarketTracker(debug=True)
        
        # Event 1: Nur Balance ändert (unvollständige TX)
        result1 = tracker._infer_transaction_from_deltas(
            window_type='buy_item',
            balance_delta=-10000,
            warehouse_delta=0,
            current_metrics={'item_name': 'Test Item'},
            last_metrics={}
        )
        assert result1 is None
        assert tracker._detail_partial_balance_delta == -10000
        assert tracker._detail_partial_warehouse_delta == 0
        
        # Event 2: BEIDE ändern sich → Neue Transaction!
        result2 = tracker._infer_transaction_from_deltas(
            window_type='buy_item',
            balance_delta=-20000,
            warehouse_delta=5000,
            current_metrics={'item_name': 'Test Item'},
            last_metrics={}
        )
        
        # Erwartung: Transaction mit -20k (NICHT -30k!)
        assert result2 is not None
        assert result2['price'] == 20000  # Nur aktuelle Transaction
        assert result2['quantity'] == 5000
        
        # Akkumulator sollte zurückgesetzt sein
        assert tracker._detail_partial_balance_delta == 0
        assert tracker._detail_partial_warehouse_delta == 0

    def test_pig_blood_exact_scenario(self):
        """
        Test: Exaktes Pig Blood Scenario aus Real-World Logs.
        
        Timeline:
        20:29:33: Window Entry (Balance=203,652,688,220, Warehouse=10,000)
        20:29:34: Change #1 (Balance -14.5M, Warehouse +0) → Preorder Fill
        20:29:36: Change #2 (Balance -14.5M, Warehouse +5k) → Direct Purchase
        
        Expected:
        - Nach Change #1: Keine Transaction (incomplete)
        - Nach Change #2: 1 Transaction @ 14.5M (NICHT @ 29M!)
        """
        tracker = MarketTracker(debug=True)
        
        # Mock the extraction function
        def mock_extract(text, wtype):
            # Parse text to determine which state we're in
            if "203,652,688,220" in text:
                return {'balance': 203652688220, 'warehouse_qty': 10000, 'item_name': 'Pig Blood'}
            elif "203,638,188,220" in text:
                return {'balance': 203638188220, 'warehouse_qty': 10000, 'item_name': 'Pig Blood'}
            elif "203,623,688,220" in text:
                return {'balance': 203623688220, 'warehouse_qty': 15000, 'item_name': 'Pig Blood'}
            return None
        
        tracker._extract_detail_window_metrics = mock_extract
        
        # 20:29:33: Window Entry
        ocr_1 = "Balance 203,652,688,220\nWarehouse 10,000\nPig Blood"
        tracker._monitor_detail_window('buy_item', ocr_1)
        
        assert tracker._detail_window_active == True
        assert tracker._detail_baseline_balance == 203652688220
        assert tracker._detail_baseline_warehouse == 10000
        
        # 20:29:34: Preorder Fill (Balance changes, Warehouse stays)
        ocr_2 = "Balance 203,638,188,220\nWarehouse 10,000\nPig Blood"
        tracker._monitor_detail_window('buy_item', ocr_2)
        
        # Should have incomplete accumulation
        assert tracker._detail_partial_balance_delta == -14500000
        assert tracker._detail_partial_warehouse_delta == 0
        
        # 20:29:36: Direct Purchase (BOTH change)
        ocr_3 = "Balance 203,623,688,220\nWarehouse 15,000\nPig Blood"
        tracker._monitor_detail_window('buy_item', ocr_3)
        
        # Smart reset should have discarded old accumulation
        # New transaction should be @ 14.5M, NOT @ 29M
        # Check partial deltas were reset after save
        assert tracker._detail_partial_balance_delta == 0
        assert tracker._detail_partial_warehouse_delta == 0

    def test_sequential_different_prices(self):
        """
        Test: Mehrere sequenzielle Käufe mit verschiedenen Preisen.
        
        Verhindert dass Deltas aus verschiedenen Transaktionen summiert werden.
        """
        tracker = MarketTracker(debug=True)
        
        # TX #1: Balance -100k, Warehouse +5000 (komplett in einem Scan)
        r1 = tracker._infer_transaction_from_deltas(
            'buy_item', -100000, 5000, {'item_name': 'Item A'}, {}
        )
        assert r1 is not None
        assert r1['price'] == 100000
        assert r1['quantity'] == 5000
        
        # TX #2 Teil 1: Balance -200k, Warehouse +0
        r2a = tracker._infer_transaction_from_deltas(
            'buy_item', -200000, 0, {'item_name': 'Item A'}, {}
        )
        assert r2a is None
        assert tracker._detail_partial_balance_delta == -200000
        
        # TX #2 Teil 2: Balance -50k, Warehouse +3000 (BEIDE ändern → Reset!)
        r2b = tracker._infer_transaction_from_deltas(
            'buy_item', -50000, 3000, {'item_name': 'Item A'}, {}
        )
        assert r2b is not None
        # Should be 50k (current scan), NOT 250k (sum)!
        assert r2b['price'] == 50000
        assert r2b['quantity'] == 3000

    def test_no_reset_when_only_one_delta_changes(self):
        """
        Test: Kein Reset wenn nur ein Delta sich ändert (normale Akkumulation).
        
        Nur wenn BEIDE Deltas gleichzeitig ändern soll reset getriggert werden.
        """
        tracker = MarketTracker(debug=True)
        
        # Scan 1: Balance -50k
        r1 = tracker._infer_transaction_from_deltas(
            'buy_item', -50000, 0, {'item_name': 'Test'}, {}
        )
        assert r1 is None
        assert tracker._detail_partial_balance_delta == -50000
        
        # Scan 2: Balance -30k (weiterhin nur Balance)
        r2 = tracker._infer_transaction_from_deltas(
            'buy_item', -30000, 0, {'item_name': 'Test'}, {}
        )
        assert r2 is None
        # Sollte ADDIEREN (normale Akkumulation)
        assert tracker._detail_partial_balance_delta == -80000
        
        # Scan 3: Warehouse +1000 (jetzt komplett)
        r3 = tracker._infer_transaction_from_deltas(
            'buy_item', 0, 1000, {'item_name': 'Test'}, {}
        )
        assert r3 is not None
        # Sollte volle 80k sein (alle akkumulierten Balance-Changes)
        assert r3['price'] == 80000
        assert r3['quantity'] == 1000

    def test_sell_transaction_smart_reset(self):
        """Test dass Smart Reset auch bei Sell-Transactions funktioniert."""
        tracker = MarketTracker(debug=True)
        
        # TX #1 partial: Balance +50k, Warehouse +0
        r1 = tracker._infer_transaction_from_deltas(
            'sell_item', 50000, 0, {'item_name': 'Sell Item'}, {}
        )
        assert r1 is None
        assert tracker._detail_partial_balance_delta == 50000
        
        # TX #2: BEIDE ändern → Reset
        r2 = tracker._infer_transaction_from_deltas(
            'sell_item', 88725, -1000, {'item_name': 'Sell Item'}, {}
        )
        assert r2 is not None
        # Should be based on 88725, NOT 138725
        assert r2['quantity'] == 1000


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
