#!/usr/bin/env python3
"""
Test BDO API Client with real API calls
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bdo_api_client import (
    get_item_price_range,
    get_multiple_item_prices,
    format_price,
    clear_price_cache,
    get_cache_stats
)
from market_json_manager import get_item_name_by_id


def test_single_item():
    """Test API call for a single item (Gem of Void)"""
    print("\n" + "="*60)
    print("TEST 1: Single Item Price Lookup (Gem of Void)")
    print("="*60)
    
    item_id = "821182"
    item_name = get_item_name_by_id(item_id)
    
    print(f"\n🔍 Fetching price data for: {item_name} (ID: {item_id})")
    
    price_data = get_item_price_range(item_id, use_cache=False)
    
    if price_data:
        print(f"\n✅ API Response:")
        print(f"   Item ID: {price_data['item_id']}")
        print(f"   Base Price: {format_price(price_data['base_price'])} Silver")
        print(f"   Min Price (Hard Cap): {format_price(price_data['min_price'])} Silver")
        print(f"   Max Price (Hard Cap): {format_price(price_data['max_price'])} Silver")
        print(f"   Last Sale Price: {format_price(price_data['last_sale_price'])} Silver")
        print(f"   Current Stock: {price_data['current_stock']:,} units")
        print(f"   Total Trades: {price_data['total_trades']:,}")
        print(f"   Enhancement Range: {price_data['enh_min']}-{price_data['enh_max']}")
        print(f"   Last Sale Time: {price_data['last_sale_time']}")
        print(f"   Fetched: {price_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Verify price range makes sense
        assert price_data['min_price'] < price_data['max_price'], "Min price should be less than max price"
        assert price_data['min_price'] > 0, "Min price should be positive"
        
        print(f"\n✅ Price data validation passed")
        return True
    else:
        print(f"\n❌ Failed to fetch price data")
        return False


def test_multiple_items():
    """Test API calls for multiple items"""
    print("\n" + "="*60)
    print("TEST 2: Multiple Items Price Lookup")
    print("="*60)
    
    # Test with all 3 void items
    test_items = [
        ("821182", "Gem of Void"),
        ("15279", "Crystal of Void - Ah'krad"),
        ("15280", "Crystal of Void Destruction")
    ]
    
    item_ids = [item_id for item_id, _ in test_items]
    
    print(f"\n🔍 Fetching price data for {len(item_ids)} items...")
    
    results = get_multiple_item_prices(item_ids, use_cache=False, delay=0.5)
    
    print(f"\n📊 Results: {len(results)}/{len(item_ids)} items fetched successfully")
    
    for item_id, expected_name in test_items:
        if item_id in results:
            price_data = results[item_id]
            print(f"\n✅ {expected_name} (ID: {item_id})")
            print(f"   Price Range: {format_price(price_data['min_price'])} - {format_price(price_data['max_price'])} Silver")
            print(f"   Current Stock: {price_data['current_stock']:,} units")
        else:
            print(f"\n❌ {expected_name} (ID: {item_id}) - Failed to fetch")
    
    return len(results) > 0


def test_cache():
    """Test price caching functionality"""
    print("\n" + "="*60)
    print("TEST 3: Price Cache Testing")
    print("="*60)
    
    item_id = "821182"
    
    # Clear cache first
    clear_price_cache()
    print("✅ Cache cleared")
    
    # First call - should hit API
    print(f"\n🔍 First call (should hit API)...")
    import time
    start = time.time()
    price_data_1 = get_item_price_range(item_id, use_cache=True)
    time_1 = time.time() - start
    
    if not price_data_1:
        print("❌ First API call failed")
        return False
    
    print(f"✅ First call completed in {time_1:.3f}s")
    
    # Check cache stats
    stats = get_cache_stats()
    print(f"\n📊 Cache stats after first call:")
    print(f"   Total entries: {stats['total_entries']}")
    print(f"   Fresh entries: {stats['fresh_entries']}")
    print(f"   Stale entries: {stats['stale_entries']}")
    
    # Second call - should use cache
    print(f"\n🔍 Second call (should use cache)...")
    start = time.time()
    price_data_2 = get_item_price_range(item_id, use_cache=True)
    time_2 = time.time() - start
    
    if not price_data_2:
        print("❌ Second call failed")
        return False
    
    print(f"✅ Second call completed in {time_2:.3f}s")
    
    # Cache should be MUCH faster
    speedup = time_1 / time_2 if time_2 > 0 else 0
    print(f"\n⚡ Cache speedup: {speedup:.1f}x faster")
    
    # Verify data is identical
    assert price_data_1['min_price'] == price_data_2['min_price'], "Cached prices should match"
    assert price_data_1['max_price'] == price_data_2['max_price'], "Cached prices should match"
    
    print(f"✅ Cache validation passed")
    
    return True


def test_invalid_item():
    """Test API behavior with invalid item ID"""
    print("\n" + "="*60)
    print("TEST 4: Invalid Item ID Handling")
    print("="*60)
    
    invalid_id = "999999999"
    
    print(f"\n🔍 Fetching price data for invalid ID: {invalid_id}")
    
    price_data = get_item_price_range(invalid_id, use_cache=False)
    
    if price_data is None:
        print(f"✅ Correctly returned None for invalid item ID")
        return True
    else:
        print(f"❌ Should have returned None for invalid item ID")
        return False


def run_api_tests():
    """Run all API tests"""
    print("\n" + "="*60)
    print("🧪 TESTING: BDO API Client")
    print("="*60)
    print("\n⚠️  NOTE: These tests require internet connection and BDO API access")
    
    results = {
        'Single Item': False,
        'Multiple Items': False,
        'Cache': False,
        'Invalid Item': False
    }
    
    try:
        results['Single Item'] = test_single_item()
        results['Multiple Items'] = test_multiple_items()
        results['Cache'] = test_cache()
        results['Invalid Item'] = test_invalid_item()
        
        print("\n" + "="*60)
        print("📊 TEST RESULTS SUMMARY")
        print("="*60)
        
        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"   {test_name}: {status}")
        
        all_passed = all(results.values())
        
        if all_passed:
            print("\n✅ ALL API TESTS PASSED!")
            print("\n🎉 BDO API Client is working correctly!")
        else:
            failed = [name for name, passed in results.items() if not passed]
            print(f"\n❌ {len(failed)} TEST(S) FAILED: {', '.join(failed)}")
        
        return all_passed
        
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_api_tests()
    sys.exit(0 if success else 1)
