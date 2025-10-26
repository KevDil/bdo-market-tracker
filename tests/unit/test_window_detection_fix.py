#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Integration-Test für Window Detection Fix
Tests die abgeänderte Option 1: Core-Keyword + (MIN ODER MAX)
"""

from utils import detect_window_type

def test_buy_item_with_max_only():
    """Buy-Item sollte mit Desired Price + MAX erkannt werden (ohne MIN)"""
    ocr_text = """
    378 198 9720 10/10 10/20 9/30 Arders ated 500 Urde 
    Desired Price 
    Juse Capacity 169.8 / 11,000 VT 
    MAX 2,370 
    Desired Amount
    """
    result = detect_window_type(ocr_text)
    print(f"✅ Test 1: Buy-Item mit MAX only → '{result}' (expected: 'buy_item')")
    assert result == 'buy_item', f"Expected 'buy_item', got '{result}'"

def test_buy_item_with_min_only():
    """Buy-Item sollte mit Desired Price + MIN erkannt werden (ohne MAX)"""
    ocr_text = """
    Desired Price 
    MIN 1,500
    Desired Amount
    """
    result = detect_window_type(ocr_text)
    print(f"✅ Test 2: Buy-Item mit MIN only → '{result}' (expected: 'buy_item')")
    assert result == 'buy_item', f"Expected 'buy_item', got '{result}'"

def test_buy_item_with_both():
    """Buy-Item sollte mit Desired Price + MAX + MIN erkannt werden"""
    ocr_text = """
    Desired Price 
    MAX 2,370
    MIN 1,500
    Desired Amount
    """
    result = detect_window_type(ocr_text)
    print(f"✅ Test 3: Buy-Item mit MAX+MIN → '{result}' (expected: 'buy_item')")
    assert result == 'buy_item', f"Expected 'buy_item', got '{result}'"

def test_sell_item_with_max_only():
    """Sell-Item sollte mit Set Price + MAX erkannt werden (ohne MIN)"""
    ocr_text = """
    Set Price
    MAX 10,000
    Register Quantity
    """
    result = detect_window_type(ocr_text)
    print(f"✅ Test 4: Sell-Item mit MAX only → '{result}' (expected: 'sell_item')")
    assert result == 'sell_item', f"Expected 'sell_item', got '{result}'"

def test_sell_item_with_min_only():
    """Sell-Item sollte mit Set Price + MIN erkannt werden (ohne MAX)"""
    ocr_text = """
    Set Price
    MIN 1,000
    Register Quantity
    """
    result = detect_window_type(ocr_text)
    print(f"✅ Test 5: Sell-Item mit MIN only → '{result}' (expected: 'sell_item')")
    assert result == 'sell_item', f"Expected 'sell_item', got '{result}'"

def test_buy_item_no_scale_fields():
    """Buy-Item sollte NICHT erkannt werden ohne MIN/MAX"""
    ocr_text = """
    Desired Price 
    Desired Amount
    """
    result = detect_window_type(ocr_text)
    print(f"✅ Test 6: Buy-Item ohne MIN/MAX → '{result}' (expected: NOT 'buy_item')")
    assert result != 'buy_item', f"Should not detect buy_item without MIN/MAX, got '{result}'"

def test_sell_item_no_scale_fields():
    """Sell-Item sollte NICHT erkannt werden ohne MIN/MAX"""
    ocr_text = """
    Set Price
    Register Quantity
    """
    result = detect_window_type(ocr_text)
    print(f"✅ Test 7: Sell-Item ohne MIN/MAX → '{result}' (expected: NOT 'sell_item')")
    assert result != 'sell_item', f"Should not detect sell_item without MIN/MAX, got '{result}'"

def test_real_ocr_from_logs():
    """Test mit echtem OCR-Text aus den Logs (Powder of Flame Käufe)"""
    # Dieser Text führte zum Bug (kein MIN, aber MAX vorhanden)
    ocr_text = """
    378 198 9720 10/10 10/20 9/30 Arders ated 500 Urde 
    Desired Price 
    Juse Capacity 169.8 / 11,000 VT 
    MAX 2,370| 
    Desired Amount
    """
    result = detect_window_type(ocr_text)
    print(f"✅ Test 8: Real OCR (Powder of Flame) → '{result}' (expected: 'buy_item')")
    assert result == 'buy_item', f"Expected 'buy_item', got '{result}'"

if __name__ == "__main__":
    print("=" * 80)
    print("WINDOW DETECTION FIX - Integration Tests")
    print("Abgeänderte Option 1: Core-Keyword + (MIN ODER MAX)")
    print("=" * 80)
    print()
    
    tests = [
        test_buy_item_with_max_only,
        test_buy_item_with_min_only,
        test_buy_item_with_both,
        test_sell_item_with_max_only,
        test_sell_item_with_min_only,
        test_buy_item_no_scale_fields,
        test_sell_item_no_scale_fields,
        test_real_ocr_from_logs,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {e}")
            failed += 1
    
    print()
    print("=" * 80)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 80)
    
    if failed == 0:
        print("✅ ALL TESTS PASSED - FIX SUCCESSFUL!")
    else:
        print(f"❌ {failed} TEST(S) FAILED")
        exit(1)
