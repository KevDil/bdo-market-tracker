"""
Test for fast action timing & mixed context detection.

Scenario:
- User relists Lion Blood (263x for 3,918,700) on buy_overview
- User relists Grim Reaper's Elixir (128x for 26,752,000) on buy_overview
- OCR scan happens AFTER user switched to sell_overview
- Lion Blood transaction line already pushed out of visible log
- Expected: Both transactions should be tracked (Lion Blood via UI inference, Grim via full context)
"""

import sys
sys.path.insert(0, 'c:/Users/kdill/Desktop/market_tracker')

from tracker import MarketTracker

def test_fast_action_timing():
    """Test mixed context detection and single placed inference."""
    
    # Simulate the actual OCR text from the log (01:32:06 scan on sell_overview)
    # This contains:
    # - Grim Reaper's Elixir: Placed + Withdrew + Transaction (full context)
    # - Lion Blood: Only Placed (transaction line already gone)
    # - Window detected as sell_overview (but contains buy events)
    text = (
        "Central Market W Buy Warehouse Balance 77,007,112,302 Manage Warehouse "
        "2025.10.12 01.31 2025.10.12 01.31 2025.10.12 01.31 2025.10.12 01.31 "
        "Placed order of Grim Reaper's Elixir X2,000 for 420,000,000 Silver "
        "Withdrew order of Grim Reaper's Elixir xl,872 for 391,248,000 silver "
        "Transaction of Grim Reaper's Elixir xl28 worth 26,752,000 Silver has been "
        "Placed order of Lion Blood x5,0O0 for 75,000,000 Silver "
        "Warehouse Capacity 5,929.9 / 11,000 VT 31.590 Sell Pearl Item Selling Limit 0 / 35 "
        "Sell Enter search term Enter a search term: Items Listed   555 Sales Completed VT "
        # Add UI metrics for Lion Blood to simulate what would be visible
        "Lion Blood Orders 5000 Orders Completed : 263 Collect 70,581,300 Re-list "
        "Grim Reaper's Elixir Orders 2000 Orders Completed : 128 Collect 391,248,000 Re-list"
    )
    
    mt = MarketTracker(debug=True)
    mt.process_ocr_text(text)
    
    # Check if both transactions were saved
    from database import get_cursor
    cur = get_cursor()
    
    # Check Lion Blood (should be inferred from placed + UI metrics)
    cur.execute("""
        SELECT item_name, quantity, price, transaction_type, tx_case 
        FROM transactions 
        WHERE item_name LIKE '%Lion Blood%' 
        ORDER BY timestamp DESC LIMIT 1
    """)
    lion = cur.fetchone()
    
    # Check Grim Reaper's Elixir (should have full context)
    cur.execute("""
        SELECT item_name, quantity, price, transaction_type, tx_case 
        FROM transactions 
        WHERE item_name LIKE '%Grim Reaper%Elixir%' 
        ORDER BY timestamp DESC LIMIT 1
    """)
    grim = cur.fetchone()
    
    print("\n" + "="*60)
    print("FAST ACTION TIMING TEST RESULTS")
    print("="*60)
    
    if lion:
        print(f"\n✅ Lion Blood tracked:")
        print(f"   Item: {lion[0]}")
        print(f"   Quantity: {lion[1]}")
        print(f"   Price: {lion[2]:,}")
        print(f"   Type: {lion[3]}")
        print(f"   Case: {lion[4]}")
        
        # Verify expected values (263x @ ~14,900 per unit = ~3,918,700)
        expected_qty = 263
        expected_price_range = (3_800_000, 4_000_000)  # Allow some variance
        
        if lion[1] == expected_qty:
            print(f"   ✅ Quantity correct: {lion[1]} == {expected_qty}")
        else:
            print(f"   ❌ Quantity mismatch: {lion[1]} != {expected_qty}")
        
        if expected_price_range[0] <= lion[2] <= expected_price_range[1]:
            print(f"   ✅ Price in range: {expected_price_range[0]:,} <= {lion[2]:,} <= {expected_price_range[1]:,}")
        else:
            print(f"   ❌ Price out of range: {lion[2]:,} not in {expected_price_range}")
        
        if lion[3] == 'buy':
            print(f"   ✅ Type correct: buy")
        else:
            print(f"   ❌ Type wrong: {lion[3]}")
    else:
        print(f"\n❌ Lion Blood NOT tracked!")
        print("   This is the bug we're trying to fix.")
    
    if grim:
        print(f"\n✅ Grim Reaper's Elixir tracked:")
        print(f"   Item: {grim[0]}")
        print(f"   Quantity: {grim[1]}")
        print(f"   Price: {grim[2]:,}")
        print(f"   Type: {grim[3]}")
        print(f"   Case: {grim[4]}")
        
        # Verify expected values (128x @ ~208,875 per unit = ~26,752,000)
        expected_qty = 128
        expected_price = 26_752_000
        
        if grim[1] == expected_qty:
            print(f"   ✅ Quantity correct: {grim[1]} == {expected_qty}")
        else:
            print(f"   ❌ Quantity mismatch: {grim[1]} != {expected_qty}")
        
        if grim[2] == expected_price:
            print(f"   ✅ Price correct: {grim[2]:,} == {expected_price:,}")
        else:
            print(f"   ❌ Price mismatch: {grim[2]:,} != {expected_price:,}")
        
        if grim[3] == 'buy':
            print(f"   ✅ Type correct: buy")
        else:
            print(f"   ❌ Type wrong: {grim[3]}")
    else:
        print(f"\n❌ Grim Reaper's Elixir NOT tracked!")
    
    print("\n" + "="*60)
    
    # Overall test result
    if lion and grim:
        print("✅ TEST PASSED: Both transactions tracked despite timing issues")
        return True
    else:
        print("❌ TEST FAILED: Some transactions missing")
        return False

if __name__ == '__main__':
    try:
        success = test_fast_action_timing()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
