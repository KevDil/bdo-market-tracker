"""
Unit-Tests für Detail-Fenster Transaktionserkennung.

Tests für:
- _extract_detail_window_metrics (Metriken-Extraktion)
- _infer_transaction_from_deltas (Transaktions-Inferenz)
- _monitor_detail_window (State Machine)
"""

import pytest
import datetime
from tracker import MarketTracker
from utils import normalize_numeric_str


class TestDetailWindowMetrics:
    """Tests für _extract_detail_window_metrics."""
    
    def setup_method(self):
        """Setup vor jedem Test."""
        self.tracker = MarketTracker(debug=False)
    
    def test_extract_sell_item_metrics_complete(self):
        """Test: Vollständige Sell-Item Metriken"""
        ocr_text = """
        Powder of Darkness
        Set Price: 15,000 Silver
        Register Quantity: 100
        Balance: 1,234,567,890 Silver
        Warehouse Quantity: 50
        """
        
        metrics = self.tracker._extract_detail_window_metrics(ocr_text, 'sell_item')
        
        assert metrics is not None
        assert 'balance' in metrics
        assert metrics['balance'] == 1234567890
        assert 'warehouse_qty' in metrics
        assert metrics['warehouse_qty'] == 50
        assert 'set_price' in metrics
        assert metrics['set_price'] == 15000
        assert 'quantity' in metrics
        assert metrics['quantity'] == 100
        # Item-Name-Extraktion ist optional (kommt in Realität aus dedizierter ROI)
        # Wenn erkannt, dann sollte es korrekt sein
        if 'item_name' in metrics:
            assert 'powder' in metrics['item_name'].lower() or 'darkness' in metrics['item_name'].lower()
    
    def test_extract_buy_item_metrics_complete(self):
        """Test: Vollständige Buy-Item Metriken"""
        ocr_text = """
        Brutal Death Elixir
        Desired Price: 4,500,000 Silver
        Desired Amount: 5
        Balance: 9,876,543,210 Silver
        Warehouse Quantity: 10
        """
        
        metrics = self.tracker._extract_detail_window_metrics(ocr_text, 'buy_item')
        
        assert metrics is not None
        assert metrics['balance'] == 9876543210
        assert metrics['warehouse_qty'] == 10
        assert 'desired_price' in metrics
        assert metrics['desired_price'] == 4500000
        assert 'quantity' in metrics
        assert metrics['quantity'] == 5
        # Item-Name-Extraktion ist optional (kommt in Realität aus dedizierter ROI)
        if 'item_name' in metrics:
            assert 'brutal' in metrics['item_name'].lower() or 'death' in metrics['item_name'].lower()
    
    def test_extract_balance_only(self):
        """Test: Nur Balance erkannt (Minimal-Fall)"""
        ocr_text = "Balance: 5,000,000 Silver"
        
        metrics = self.tracker._extract_detail_window_metrics(ocr_text, 'sell_item')
        
        assert metrics is not None
        assert metrics['balance'] == 5000000
        assert 'warehouse_qty' not in metrics
    
    def test_extract_warehouse_only(self):
        """Test: Nur Warehouse erkannt (Balance ist jetzt Pflicht!)"""
        # Balance ist Pflicht - Warehouse alleine reicht nicht
        ocr_text = "Warehouse Quantity: 25"
        
        metrics = self.tracker._extract_detail_window_metrics(ocr_text, 'buy_item')
        
        # Sollte None zurückgeben weil Balance fehlt
        assert metrics is None
    
    def test_extract_empty_text(self):
        """Test: Leerer OCR-Text"""
        metrics = self.tracker._extract_detail_window_metrics("", 'sell_item')
        assert metrics is None
        
        metrics = self.tracker._extract_detail_window_metrics(None, 'buy_item')
        assert metrics is None
    
    def test_extract_invalid_window_type(self):
        """Test: Ungültiger Window-Type"""
        ocr_text = "Balance: 1,000,000 Silver"
        metrics = self.tracker._extract_detail_window_metrics(ocr_text, 'invalid_type')
        # Sollte trotzdem Balance extrahieren (keine Window-Type-Abhängigkeit für Balance)
        assert metrics is not None
        assert metrics['balance'] == 1000000


class TestTransactionInference:
    """Tests für _infer_transaction_from_deltas."""
    
    def setup_method(self):
        """Setup vor jedem Test."""
        self.tracker = MarketTracker(debug=False)
    
    def test_infer_sell_transaction_basic(self):
        """Test: Einfacher Verkauf (Balance steigt, Warehouse sinkt)"""
        current_metrics = {
            'item_name': 'Powder of Darkness',
            'set_price': 15000,
            'balance': 1235000000,
            'warehouse_qty': 40,
        }
        last_metrics = {
            'balance': 1233500000,
            'warehouse_qty': 50,
        }
        
        balance_delta = 1500000  # +1.5M (nach Steuern)
        warehouse_delta = -10  # -10 Items verkauft
        
        tx = self.tracker._infer_transaction_from_deltas(
            'sell_item',
            balance_delta,
            warehouse_delta,
            current_metrics,
            last_metrics
        )
        
        assert tx is not None
        assert tx['transaction_type'] == 'sell'
        assert tx['quantity'] == 10
        assert tx['item_name'] == 'Powder of Darkness'
        # Preis sollte ca. 15000*10 = 150000 sein (Brutto)
        assert 140000 <= tx['price'] <= 170000
        assert tx['tx_case'] == 'sell_collect_ui_inferred'  # Detail-Window transactions use _ui_inferred suffix
        assert tx['_from_detail_window'] is True
    
    def test_infer_buy_transaction_basic(self):
        """Test: Einfacher Kauf (Balance sinkt, Warehouse steigt)"""
        current_metrics = {
            'item_name': 'Brutal Death Elixir',
            'desired_price': 4500000,
            'balance': 9854043210,
            'warehouse_qty': 15,
        }
        last_metrics = {
            'balance': 9876543210,
            'warehouse_qty': 10,
        }
        
        balance_delta = -22500000  # -22.5M ausgegeben
        warehouse_delta = 5  # +5 Items gekauft
        
        tx = self.tracker._infer_transaction_from_deltas(
            'buy_item',
            balance_delta,
            warehouse_delta,
            current_metrics,
            last_metrics
        )
        
        assert tx is not None
        assert tx['transaction_type'] == 'buy'
        assert tx['quantity'] == 5
        assert tx['item_name'] == 'Brutal Death Elixir'
        # Preis sollte ca. 4500000*5 = 22500000 sein
        assert 22000000 <= tx['price'] <= 23000000
        assert tx['tx_case'] == 'buy_collect_ui_inferred'  # Detail-Window transactions use _ui_inferred suffix
        assert tx['_from_detail_window'] is True
    
    def test_infer_sell_invalid_deltas(self):
        """Test: Ungültige Sell-Deltas (Balance sinkt statt steigt)"""
        current_metrics = {
            'item_name': 'Test Item',
            'balance': 1000000,
            'warehouse_qty': 50,
        }
        last_metrics = {
            'balance': 2000000,
            'warehouse_qty': 60,
        }
        
        balance_delta = -1000000  # Negativ bei Sell = ungültig!
        warehouse_delta = -10
        
        tx = self.tracker._infer_transaction_from_deltas(
            'sell_item',
            balance_delta,
            warehouse_delta,
            current_metrics,
            last_metrics
        )
        
        assert tx is None
    
    def test_infer_buy_warehouse_only_delta(self):
        """Test: Warehouse-Only Delta (Preorder-Collect ohne Kauf)
        
        Wenn warehouse_delta > 0 ABER balance_delta = 0:
        → Preorder wurde collected, aber noch kein Kauf
        → Sollte KEINE Transaktion erstellen (warten auf echten Kauf)
        """
        current_metrics = {
            'item_name': 'Powder of Flame',
            'desired_price': 2230000,
            'balance': 10000000,  # Unverändert
            'warehouse_qty': 5000,  # +5000 (Preorder collected)
        }
        last_metrics = {
            'balance': 10000000,  # Gleich!
            'warehouse_qty': 0,
        }
        
        balance_delta = 0  # Keine Balance-Änderung
        warehouse_delta = 5000  # +5000 Items
        
        tx = self.tracker._infer_transaction_from_deltas(
            'buy_item',
            balance_delta,
            warehouse_delta,
            current_metrics,
            last_metrics
        )
        
        # Sollte None zurückgeben (warten auf echten Kauf mit balance_delta < 0)
        assert tx is None
        # pending_collect_qty sollte gesetzt sein
        assert self.tracker._detail_pending_collect_qty == 5000
    
    def test_infer_buy_preorder_collect_combo(self):
        """Test: Preorder-Collect + Purchase kombiniert (Lion Blood Szenario)
        
        Sequenz:
        1. Warehouse-Only Delta +3048 (Preorder collected) → pending_collect_qty = 3048
        2. Combined Delta: Balance -95.5M, Warehouse +5000 (Purchase)
        → Sollte 8048x @ 95.5M total erstellen
        """
        # Schritt 1: Warehouse-Only Delta (Preorder-Collect)
        self.tracker._detail_pending_collect_qty = 0
        self.tracker._detail_partial_balance_delta = 0
        self.tracker._detail_partial_warehouse_delta = 0
        
        current_metrics_1 = {
            'item_name': 'Lion Blood',
            'desired_price': 19100,
            'balance': 10000000,  # Unverändert
            'warehouse_qty': 3048,  # +3048 (Preorder collected)
        }
        last_metrics_1 = {
            'balance': 10000000,
            'warehouse_qty': 0,
        }
        
        tx1 = self.tracker._infer_transaction_from_deltas(
            'buy_item',
            0,  # balance_delta = 0
            3048,  # warehouse_delta = +3048
            current_metrics_1,
            last_metrics_1
        )
        
        # Sollte None zurückgeben, aber pending_collect_qty setzen
        assert tx1 is None
        assert self.tracker._detail_pending_collect_qty == 3048
        
        # Schritt 2: Combined Delta (Balance + Warehouse)
        current_metrics_2 = {
            'item_name': 'Lion Blood',
            'desired_price': 19100,
            'balance': 9904500000,  # -95.5M
            'warehouse_qty': 8048,  # +5000 (total 3048+5000)
        }
        last_metrics_2 = {
            'balance': 10000000,
            'warehouse_qty': 3048,
        }
        
        tx2 = self.tracker._infer_transaction_from_deltas(
            'buy_item',
            -95500000,  # balance_delta = -95.5M
            5000,  # warehouse_delta = +5000
            current_metrics_2,
            last_metrics_2
        )
        
        # Sollte Transaction mit kombinierter Menge erstellen
        assert tx2 is not None
        assert tx2['transaction_type'] == 'buy'
        assert tx2['quantity'] == 8048  # 3048 (preorder) + 5000 (purchase)
        assert tx2['price'] == 95500000  # Nur neuer Kauf-Preis
        assert tx2['item_name'] == 'Lion Blood'
        assert tx2['tx_case'] == 'buy_collect_ui_inferred'
        # pending_collect_qty sollte zurückgesetzt sein
        assert self.tracker._detail_pending_collect_qty == 0
    
    def test_infer_buy_invalid_deltas(self):
        """Test: Ungültige Buy-Deltas (Warehouse sinkt statt steigt)"""
        current_metrics = {
            'item_name': 'Test Item',
            'balance': 8000000,
            'warehouse_qty': 5,
        }
        last_metrics = {
            'balance': 10000000,
            'warehouse_qty': 10,
        }
        
        balance_delta = -2000000
        warehouse_delta = -5  # Negativ bei Buy = ungültig!
        
        tx = self.tracker._infer_transaction_from_deltas(
            'buy_item',
            balance_delta,
            warehouse_delta,
            current_metrics,
            last_metrics
        )
        
        assert tx is None
    
    def test_infer_buy_with_new_preorder(self):
        """Test: Purchase + neue Preorder (warehouse_delta = 0)
        
        Wenn gleichzeitig gekauft UND neue Preorder gesetzt wird:
        - Balance: -95.5M (Kauf)
        - Warehouse: 0 (5000 gekauft - 5000 neue Preorder = 0)
        - OCR enthält "Placed order x5000"
        → Sollte 5000x @ 95.5M erstellen
        """
        # Setze OCR-Text-Buffer mit "Placed order"
        self.tracker._detail_last_ocr_text = "2025.10.20 21:43 Placed order of Lion Blood x5,000 for 95,500,000 Silver"
        self.tracker._detail_pending_collect_qty = 0
        self.tracker._detail_partial_balance_delta = 0
        self.tracker._detail_partial_warehouse_delta = 0
        
        current_metrics = {
            'item_name': 'Lion Blood',
            'desired_price': 19100,
            'balance': 9904500000,  # -95.5M
            'warehouse_qty': 23048,  # Unchanged (5000 bought - 5000 placed = 0)
        }
        last_metrics = {
            'balance': 10000000000,
            'warehouse_qty': 23048,  # Same!
        }
        
        tx = self.tracker._infer_transaction_from_deltas(
            'buy_item',
            -95500000,  # balance_delta = -95.5M
            0,  # warehouse_delta = 0 (!)
            current_metrics,
            last_metrics
        )
        
        # Sollte Transaction erstellen trotz warehouse_delta = 0
        assert tx is not None
        assert tx['transaction_type'] == 'buy'
        assert tx['quantity'] == 5000  # Aus "Placed order" extrahiert
        assert tx['price'] == 95500000
        assert tx['item_name'] == 'Lion Blood'
        assert tx['tx_case'] == 'buy_collect_ui_inferred'
    
    def test_infer_no_item_name(self):
        """Test: Keine Item-Name vorhanden (sollte fehlschlagen)"""
        current_metrics = {
            'balance': 1500000,
            'warehouse_qty': 40,
        }
        last_metrics = {
            'balance': 1000000,
            'warehouse_qty': 50,
        }
        
        balance_delta = 500000
        warehouse_delta = -10
        
        tx = self.tracker._infer_transaction_from_deltas(
            'sell_item',
            balance_delta,
            warehouse_delta,
            current_metrics,
            last_metrics
        )
        
        assert tx is None
    
    def test_infer_quantity_out_of_range(self):
        """Test: Menge außerhalb gültiger Range (1-500000)"""
        self.tracker._detail_window_active = 'sell_item'
        self.tracker._detail_window_item = 'Test Item'
        self.tracker._detail_baseline_balance = 1000000
        self.tracker._detail_baseline_warehouse = 600000
        self.tracker._detail_partial_balance_delta = 0
        self.tracker._detail_partial_warehouse_delta = 0
        
        current_metrics = {
            'item_name': 'Test Item',
            'balance': 200000000,  # +199M
            'warehouse_qty': 0,
        }
        last_metrics = {
            'balance': 1000000,
            'warehouse_qty': 600000,  # 600000 Items verkauft (über 500000 Limit)
        }
        
        balance_delta = 199000000  # Großer Gewinn
        warehouse_delta = -600000  # Zu viele Items (über Limit)
        
        tx = self.tracker._infer_transaction_from_deltas(
            'sell_item',
            balance_delta,
            warehouse_delta,
            current_metrics,
            last_metrics
        )
        
        # Sollte abgelehnt werden wegen quantity > 500000
        assert tx is None


class TestDetailWindowStateMachine:
    """Tests für _monitor_detail_window State Machine."""
    
    def setup_method(self):
        """Setup vor jedem Test."""
        self.tracker = MarketTracker(debug=False)
    
    def test_state_initial_entry(self):
        """Test: Erstes Betreten des Detail-Fensters setzt Baseline
        
        Baseline wird direkt aus erster OCR-Ablesung gesetzt (keine Manipulation).
        Warehouse-Only-Deltas (Preorder-Collect) werden später beim Transaction-Inference gefiltert.
        """
        ocr_text = """
        Powder of Darkness
        Balance: 1,000,000 Silver
        Warehouse Quantity: 50
        """
        
        # Vor dem Call: State sollte inaktiv sein
        assert not self.tracker._detail_window_active
        
        # Erster Call: Baseline setzen
        self.tracker._monitor_detail_window('sell_item', ocr_text)
        
        # Nach dem Call: State aktiv, Baseline gesetzt
        assert self.tracker._detail_window_active
        assert self.tracker._detail_window_type == 'sell_item'
        assert self.tracker._detail_baseline_balance == 1000000
        # Baseline wird direkt aus OCR-Ablesung gesetzt (keine Manipulation mehr)
        assert self.tracker._detail_baseline_warehouse == 50
    
    def test_state_no_change_no_transaction(self):
        """Test: Keine Änderung → Keine Transaktion"""
        ocr_text = """
        Test Item
        Balance: 1,000,000 Silver
        Warehouse Quantity: 50
        """
        
        # Baseline setzen
        self.tracker._monitor_detail_window('sell_item', ocr_text)
        
        # Gleicher Text nochmal → Keine Transaktion
        initial_sig_count = len(self.tracker.seen_tx_signatures)
        self.tracker._monitor_detail_window('sell_item', ocr_text)
        
        # Keine neue Transaktion gespeichert
        assert len(self.tracker.seen_tx_signatures) == initial_sig_count
    
    def test_state_reset_on_window_change(self):
        """Test: Fensterwechsel resettet State
        
        Baseline wird aus OCR-Ablesung gesetzt (keine Manipulation).
        """
        ocr_text_sell = "Balance: 1,000,000 Silver\nWarehouse Quantity: 50"
        ocr_text_buy = "Balance: 2,000,000 Silver\nWarehouse Quantity: 10"
        
        # Sell-Fenster betreten
        self.tracker._monitor_detail_window('sell_item', ocr_text_sell)
        assert self.tracker._detail_window_type == 'sell_item'
        
        # Zu Buy-Fenster wechseln
        self.tracker._monitor_detail_window('buy_item', ocr_text_buy)
        
        # State sollte neu initialisiert sein
        assert self.tracker._detail_window_type == 'buy_item'
        assert self.tracker._detail_baseline_balance == 2000000
        # Baseline wird direkt aus OCR-Ablesung gesetzt
        assert self.tracker._detail_baseline_warehouse == 10
    
    def test_state_manual_reset(self):
        """Test: Manueller State-Reset"""
        ocr_text = "Balance: 1,000,000 Silver\nWarehouse Quantity: 50"
        
        # State aktivieren
        self.tracker._monitor_detail_window('sell_item', ocr_text)
        assert self.tracker._detail_window_active
        
        # Manueller Reset
        self.tracker._reset_detail_window_state()
        
        # Alles sollte zurückgesetzt sein
        assert not self.tracker._detail_window_active
        assert self.tracker._detail_window_type is None
        assert self.tracker._detail_baseline_balance is None
        assert self.tracker._detail_baseline_warehouse is None


class TestNormalizeNumericStr:
    """Tests für normalize_numeric_str (Helper-Funktion)."""
    
    def test_normalize_simple(self):
        """Test: Einfache Zahlen"""
        assert normalize_numeric_str("123") == 123
        assert normalize_numeric_str("1,234") == 1234
        assert normalize_numeric_str("1,234,567") == 1234567
    
    def test_normalize_ocr_confusables(self):
        """Test: OCR-Confusables (O→0, l→1, S→5)"""
        assert normalize_numeric_str("1,234,S67") == 1234567
        assert normalize_numeric_str("1O5") == 105
        assert normalize_numeric_str("l23") == 123
    
    def test_normalize_invalid(self):
        """Test: Ungültige Eingaben"""
        assert normalize_numeric_str("") is None
        assert normalize_numeric_str("abc") is None
        assert normalize_numeric_str(None) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
