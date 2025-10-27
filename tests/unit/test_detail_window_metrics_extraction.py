#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Unit-Tests für Detail-Window-Metriken-Extraktion
Tests die Regex-Pattern-Fixes für verschiedene OCR-Formate
"""

import sys
from pathlib import Path

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


class TestDetailWindowMetricsExtraction:
    """Tests für _extract_detail_window_metrics() mit verschiedenen OCR-Formaten"""
    
    def setup_method(self):
        """Setup vor jedem Test"""
        self.tracker = MarketTracker(debug=False)
    
    # === Balance-Pattern Tests ===
    
    def test_extract_balance_without_silver(self):
        """Test: Balance wird auch ohne 'Silver'-Suffix erkannt (Detail-ROI Format)"""
        text = "Balance 204,793,068,735"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None, "Metrics should not be None"
        assert 'balance' in metrics, "Balance should be extracted"
        assert metrics['balance'] == 204793068735, f"Expected 204793068735, got {metrics['balance']}"
    
    def test_extract_balance_with_silver(self):
        """Test: Balance wird auch MIT 'Silver'-Suffix erkannt (Overview Format)"""
        text = "Balance: 123,456,789 Silver"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None
        assert 'balance' in metrics
        assert metrics['balance'] == 123456789
    
    def test_extract_balance_with_colon(self):
        """Test: Balance mit Doppelpunkt"""
        text = "Balance: 50,000,000"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None
        assert metrics['balance'] == 50000000
    
    # === Warehouse-Pattern Tests ===
    
    def test_extract_warehouse_number_first(self):
        """Test: Warehouse wird erkannt wenn Zahl ZUERST kommt (Detail-ROI Format)"""
        # Warehouse alleine reicht nicht - Balance ist Pflicht!
        # Test mit Balance kombiniert
        text = "Balance 100,000,000\n10,000 Warehouse Quantity"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None
        assert 'warehouse_qty' in metrics, "Warehouse should be extracted"
        assert metrics['warehouse_qty'] == 10000, f"Expected 10000, got {metrics['warehouse_qty']}"
    
    def test_extract_warehouse_number_after(self):
        """Test: Warehouse wird erkannt wenn Zahl DANACH kommt (Overview Format)"""
        text = "Balance 100,000,000\nWarehouse Quantity: 50"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None
        assert 'warehouse_qty' in metrics
        assert metrics['warehouse_qty'] == 50
    
    def test_extract_warehouse_short_form(self):
        """Test: Warehouse mit 'WH' Kurzform"""
        text = "Balance 100,000,000\nWH: 25"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None
        assert 'warehouse_qty' in metrics
        assert metrics['warehouse_qty'] == 25

    def test_extract_warehouse_on_next_line_after_label(self):
        """Test: Warehouse-Zahl steht auf eigener Zeile unter dem Label."""
        text = "Balance 5,000,000\nWarehouse Quantity\n3"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')

        assert metrics is not None
        assert metrics['warehouse_qty'] == 3

    def test_extract_warehouse_missing_triggers_flag(self, monkeypatch):
        """Test: Wenn keine Warehouse-Zahl erkannt wird, bleibt Flag aktiv."""

        # Flag-Verhalten beobachten
        calls = []

        def fake_set_need_flag(flag, value, reason=""):
            calls.append((flag, value, reason))

        monkeypatch.setattr(self.tracker, '_set_need_flag', fake_set_need_flag)

        text = "Balance 5,000,000\nWarehouse Quantity"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')

        assert metrics is not None
        assert 'warehouse_qty' not in metrics
        assert ('detail_warehouse', True, 'detail_extract_missing_warehouse') in calls
    
    # === Item-Name Tests ===
    
    def test_extract_item_name_with_timestamp(self):
        """Test: Item-Name wird auch mit Timestamp-Präfix erkannt"""
        text = "2025.10.20 19.23 Powder of Flame\nBalance 100,000,000"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None
        assert 'item_name' in metrics, "Item name should be extracted"
        assert 'Powder of Flame' in metrics['item_name'], f"Expected 'Powder of Flame', got '{metrics['item_name']}'"
    
    def test_extract_item_name_without_timestamp(self):
        """Test: Item-Name ohne Timestamp"""
        text = "Brutal Death Elixir\nBalance 50,000,000"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None
        assert 'item_name' in metrics
        assert 'Brutal Death Elixir' in metrics['item_name']
    
    def test_extract_item_name_with_grade(self):
        """Test: Item-Name mit Grade-Bracket"""
        text = "[Grade 3] Caphras Stone\nBalance 100,000,000"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None
        assert 'item_name' in metrics
        # Grade-Brackets sollten entfernt werden
        assert 'Caphras Stone' in metrics['item_name']
        assert '[Grade 3]' not in metrics['item_name']
    
    # === Kombinierte Tests (Real OCR Scenarios) ===
    
    def test_extract_combined_real_ocr_buy_item(self):
        """Test: Vollständiger OCR-Text von echtem Buy-Item Detail-Fenster"""
        text = """2025.10.20 19.23 Powder of Flame
Balance 204,793,068,735
10,000 Warehouse Quantity"""
        
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None, "Metrics should not be None for real OCR text"
        assert 'balance' in metrics, "Balance should be extracted"
        assert metrics['balance'] == 204793068735, f"Balance mismatch: {metrics['balance']}"
        assert 'warehouse_qty' in metrics, "Warehouse should be extracted"
        assert metrics['warehouse_qty'] == 10000, f"Warehouse mismatch: {metrics['warehouse_qty']}"
        assert 'item_name' in metrics, "Item name should be extracted"
        assert 'Powder of Flame' in metrics['item_name'], f"Item name mismatch: {metrics['item_name']}"
    
    def test_extract_combined_real_ocr_sell_item(self):
        """Test: Vollständiger OCR-Text von echtem Sell-Item Detail-Fenster"""
        text = """2025.10.20 19.25 Crystal of Infinity - Assault
Balance 150,000,000
5 Warehouse Quantity"""
        
        metrics = self.tracker._extract_detail_window_metrics(text, 'sell_item')
        
        assert metrics is not None
        assert metrics['balance'] == 150000000
        assert metrics['warehouse_qty'] == 5
        assert 'item_name' in metrics
    
    def test_extract_balance_change_detection(self):
        """Test: Zwei aufeinanderfolgende Extractions zeigen Balance-Änderung"""
        # Erste Messung
        text1 = """2025.10.20 19.23 Powder of Flame
Balance 204,793,068,735
10,000 Warehouse Quantity"""
        
        metrics1 = self.tracker._extract_detail_window_metrics(text1, 'buy_item')
        
        # Zweite Messung nach Kauf (Balance -10,750,000)
        text2 = """2025.10.20 19.23 Powder of Flame
Balance 204,782,318,735
15,000 Warehouse Quantity"""
        
        metrics2 = self.tracker._extract_detail_window_metrics(text2, 'buy_item')
        
        assert metrics1 is not None
        assert metrics2 is not None
        
        # Prüfe ob Balance-Delta korrekt ist
        balance_delta = metrics2['balance'] - metrics1['balance']
        assert balance_delta == -10750000, f"Expected -10750000, got {balance_delta}"
        
        # Prüfe ob Warehouse-Delta korrekt ist
        warehouse_delta = metrics2['warehouse_qty'] - metrics1['warehouse_qty']
        assert warehouse_delta == 5000, f"Expected +5000, got {warehouse_delta}"
    
    # === Edge Cases ===
    
    def test_extract_no_balance(self):
        """Test: Ohne Balance sollte None zurückkommen"""
        text = "10,000 Warehouse Quantity\nPowder of Flame"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        # Balance ist Pflicht
        assert metrics is None, "Should return None without balance"
    
    def test_extract_empty_text(self):
        """Test: Leerer Text sollte None zurückgeben"""
        metrics = self.tracker._extract_detail_window_metrics('', 'buy_item')
        assert metrics is None
    
    def test_extract_garbage_text(self):
        """Test: Garbage-Text sollte None zurückgeben"""
        text = "asdlkjfh 123 xyz"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        assert metrics is None
    
    def test_extract_balance_only(self):
        """Test: Nur Balance (ohne Warehouse) sollte funktionieren"""
        text = "Balance 50,000,000"
        metrics = self.tracker._extract_detail_window_metrics(text, 'buy_item')
        
        assert metrics is not None, "Should work with balance only"
        assert 'balance' in metrics
        assert metrics['balance'] == 50000000
        # Warehouse ist optional
        assert 'warehouse_qty' not in metrics or metrics['warehouse_qty'] is None


if __name__ == "__main__":
    # Manuelle Ausführung für schnelles Testen
    import sys
    pytest.main([__file__, '-v', '--tb=short'] + sys.argv[1:])
