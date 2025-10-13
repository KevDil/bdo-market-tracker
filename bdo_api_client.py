#!/usr/bin/env python3
"""
BDO Market API Client

Fetches current min/max prices from BDO EU Trade Market API.
Uses item IDs from market.json to query prices.

API: POST GetWorldMarketSubList
Endpoint: https://eu-trade.naeu.playblackdesert.com/Trademarket/GetWorldMarketSubList

Response format (comma-separated string):
0 - Item ID
1 - Enhancement range - min
2 - Enhancement range - max
3 - Base price
4 - Current stock
5 - Total trades
6 - Price hard cap - min (minimum price)
7 - Price hard cap - max (maximum price)
8 - Last sale price
9 - Last sale time
"""

import requests
from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
import time
from functools import wraps

from market_json_manager import get_item_id_by_name

# API Configuration
BDO_API_URL = "https://eu-trade.naeu.playblackdesert.com/Trademarket/GetWorldMarketSubList"
BDO_API_HEADERS = {
    "User-Agent": "BlackDesert",
    "Content-Type": "application/json"
}

# Cache configuration
# Prices only change weekly on game patch day, so we can cache for 1 week
_price_cache: Dict[str, dict] = {}
_cache_duration = timedelta(days=7)  # Cache prices for 1 week (until next patch)

# Retry configuration for API calls
MAX_RETRIES = 3  # Maximum number of retry attempts
BACKOFF_FACTOR = 1.5  # Exponential backoff multiplier
RETRY_DELAY_BASE = 0.5  # Base delay in seconds


def retry_with_backoff(max_retries=MAX_RETRIES, backoff_factor=BACKOFF_FACTOR, base_delay=RETRY_DELAY_BASE):
    """
    Decorator to retry a function with exponential backoff on failure.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for exponential backoff
        base_delay: Base delay in seconds before first retry
    
    Returns:
        Decorated function that retries on RequestException
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    # If function returned None due to API error, retry
                    if result is None and attempt < max_retries - 1:
                        wait_time = base_delay * (backoff_factor ** attempt)
                        if attempt > 0:  # Don't log on first attempt
                            print(f"[API-RETRY] Attempt {attempt + 1}/{max_retries} failed, retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue
                    return result
                except requests.RequestException as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        wait_time = base_delay * (backoff_factor ** attempt)
                        print(f"[API-RETRY] Request failed (attempt {attempt + 1}/{max_retries}): {e}")
                        print(f"[API-RETRY] Retrying in {wait_time:.1f}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"[API-RETRY] All {max_retries} attempts failed for {func.__name__}")
                        raise
                except Exception as e:
                    # For non-network exceptions, don't retry
                    print(f"[API-ERROR] Non-retryable error in {func.__name__}: {e}")
                    raise
            
            # If we exhausted retries
            if last_exception:
                raise last_exception
            return None
        
        return wrapper
    return decorator


@retry_with_backoff(max_retries=3, backoff_factor=1.5, base_delay=0.5)
def get_item_price_range(item_id: str, use_cache: bool = True) -> Optional[Dict[str, int]]:
    """
    Get current min/max price range for an item from BDO API.
    
    Uses POST GetWorldMarketSubList endpoint.
    Response format: comma-separated values
    0=ItemID, 1=EnhMin, 2=EnhMax, 3=BasePrice, 4=Stock, 5=Trades,
    6=MinPrice, 7=MaxPrice, 8=LastSalePrice, 9=LastSaleTime
    
    Args:
        item_id: BDO item ID (as string)
        use_cache: Use cached prices if available and fresh
        
    Returns:
        Dict with keys:
            - min_price: Minimum market price (hard cap)
            - max_price: Maximum market price (hard cap)
            - base_price: Base price
            - last_sale_price: Last sale price
            - current_stock: Current stock
            - total_trades: Total trades
            - timestamp: When data was fetched
        Returns None if API request fails
    """
    # Check cache first
    if use_cache and item_id in _price_cache:
        cached = _price_cache[item_id]
        cache_age = datetime.now() - cached['timestamp']
        
        if cache_age < _cache_duration:
            return cached
    
    try:
        # POST request with JSON body
        payload = {
            "keyType": 0,
            "mainKey": int(item_id)
        }
        
        response = requests.post(
            BDO_API_URL,
            json=payload,
            headers=BDO_API_HEADERS,
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"⚠️  API returned status {response.status_code} for item {item_id}")
            return None
        
        data = response.json()
        
        # Check result code
        if not data or data.get('resultCode') != 0:
            result_code = data.get('resultCode', 'unknown') if data else 'no response'
            print(f"⚠️  API error for item {item_id}: resultCode={result_code}")
            return None
        
        # Parse resultMsg - ACTUAL format: hyphen-separated values, trailing '|'
        # Example: 821182-0-0-39500000-828-564823-12500000-50000000-40400000-1760267134|
        result_msg = data.get('resultMsg', '')
        if not result_msg:
            print(f"⚠️  Empty resultMsg for item {item_id}")
            return None
        
        # Remove trailing '|' if present, then split by '-'
        # Format: itemId-enhMin-enhMax-basePrice-stock-trades-minPrice-maxPrice-lastSalePrice-lastSaleTime
        result_msg = result_msg.rstrip('|')
        parts = result_msg.split('-')
        
        if len(parts) < 10:
            print(f"⚠️  Invalid resultMsg format for item {item_id}: {result_msg}")
            return None
        
        try:
            price_data = {
                'item_id': parts[0],
                'enh_min': int(parts[1]),
                'enh_max': int(parts[2]),
                'base_price': int(parts[3]),
                'current_stock': int(parts[4]),
                'total_trades': int(parts[5]),
                'min_price': int(parts[6]),      # Price hard cap - min
                'max_price': int(parts[7]),      # Price hard cap - max
                'last_sale_price': int(parts[8]),
                'last_sale_time': parts[9],
                'timestamp': datetime.now()
            }
            
            # Update cache
            _price_cache[item_id] = price_data
            
            return price_data
            
        except (ValueError, IndexError) as e:
            print(f"⚠️  Failed to parse price data for item {item_id}: {e}")
            return None
        
    except requests.RequestException as e:
        print(f"⚠️  API request failed for item {item_id}: {e}")
        return None
    except Exception as e:
        print(f"⚠️  Unexpected error for item {item_id}: {e}")
        return None


def get_item_price_range_by_name(
    item_name: str,
    *,
    use_cache: bool = True,
    fuzzy: bool = True,
    min_score: int = 86,
) -> Optional[Dict[str, int]]:
    """Resolve an item name via market.json and fetch its price range from the API."""
    item_id = get_item_id_by_name(item_name, fuzzy=fuzzy, min_score=min_score)
    if not item_id:
        return None
    return get_item_price_range(str(item_id), use_cache=use_cache)


def get_multiple_item_prices(item_ids: list[str], use_cache: bool = True, delay: float = 0.5) -> Dict[str, dict]:
    """
    Get price ranges for multiple items.
    
    Args:
        item_ids: List of BDO item IDs
        use_cache: Use cached prices if available
        delay: Delay between API requests (seconds) to avoid rate limiting
        
    Returns:
        Dict mapping item_id -> price_data
        Items with failed requests will be omitted
    """
    results = {}
    
    for i, item_id in enumerate(item_ids):
        price_data = get_item_price_range(item_id, use_cache=use_cache)
        
        if price_data:
            results[item_id] = price_data
        
        # Add delay between requests (except for last one)
        if i < len(item_ids) - 1 and delay > 0:
            time.sleep(delay)
    
    return results


def format_price(price: int) -> str:
    """
    Format price with thousand separators.
    
    Args:
        price: Price in silver
        
    Returns:
        Formatted string (e.g., "39,700,000")
    """
    return f"{price:,}"


def clear_price_cache():
    """Clear the price cache."""
    global _price_cache
    _price_cache = {}


def get_cache_stats() -> Dict[str, int]:
    """
    Get cache statistics.
    
    Returns:
        Dict with cache info:
            - total_entries: Number of cached items
            - fresh_entries: Number of fresh cached items
            - stale_entries: Number of stale cached items
    """
    now = datetime.now()
    fresh = 0
    stale = 0
    
    for cached in _price_cache.values():
        cache_age = now - cached['timestamp']
        if cache_age < _cache_duration:
            fresh += 1
        else:
            stale += 1
    
    return {
        'total_entries': len(_price_cache),
        'fresh_entries': fresh,
        'stale_entries': stale
    }
