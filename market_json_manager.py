#!/usr/bin/env python3
"""
Market JSON Manager - Central item database using market.json

Replaces market_data.csv with market.json as the single source of truth.
Provides:
- Whitelist validation
- Item name correction
- Item name <-> Item ID translation
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple
from rapidfuzz import process, fuzz

# Singleton pattern for cached data
_market_items: Optional[Dict[str, dict]] = None
_item_name_to_id: Optional[Dict[str, str]] = None
_item_id_to_name: Optional[Dict[str, str]] = None


def load_market_json(force_reload: bool = False) -> Dict[str, dict]:
    """
    Load market.json and return items dict.
    Uses singleton caching for performance.
    
    Args:
        force_reload: Force reload from disk (clears cache)
        
    Returns:
        Dict mapping item_id -> item_data
    """
    global _market_items, _item_name_to_id, _item_id_to_name
    
    if not force_reload and _market_items is not None:
        return _market_items
    
    market_json_path = Path(__file__).parent / "config" / "market.json"
    
    if not market_json_path.exists():
        raise FileNotFoundError(f"market.json not found at {market_json_path}")
    
    with open(market_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if 'items' not in data:
        raise ValueError("market.json missing 'items' key")
    
    _market_items = data['items']
    
    # Build reverse lookup dicts
    _item_name_to_id = {}
    _item_id_to_name = {}
    
    for item_id, item_data in _market_items.items():
        name = item_data.get('name')
        if name:
            # Normalize name (lowercase for matching)
            name_lower = name.lower()
            _item_name_to_id[name_lower] = item_id
            _item_id_to_name[item_id] = name
    
    print(f"✅ Loaded {len(_market_items)} items from market.json")
    return _market_items


def get_item_by_id(item_id: str) -> Optional[dict]:
    """
    Get item data by item ID.
    
    Args:
        item_id: BDO item ID (as string)
        
    Returns:
        Item data dict or None if not found
    """
    items = load_market_json()
    return items.get(str(item_id))


def get_item_id_by_name(item_name: str, fuzzy: bool = True, min_score: int = 86) -> Optional[str]:
    """
    Get item ID by item name with optional fuzzy matching.
    
    Args:
        item_name: Item name to search for
        fuzzy: Enable fuzzy matching if exact match fails
        min_score: Minimum fuzzy match score (0-100)
        
    Returns:
        Item ID (as string) or None if not found
    """
    load_market_json()  # Ensure data is loaded
    
    if _item_name_to_id is None:
        return None
    
    # Try exact match (case-insensitive)
    item_name_lower = item_name.lower()
    if item_name_lower in _item_name_to_id:
        return _item_name_to_id[item_name_lower]
    
    # Try fuzzy matching with WRatio (faster and more robust for OCR errors)
    if fuzzy:
        matches = process.extract(
            item_name_lower,
            _item_name_to_id.keys(),
            scorer=fuzz.WRatio,  # WRatio: faster and better for OCR errors than token_set_ratio
            limit=1
        )
        
        if matches and matches[0][1] >= min_score:
            matched_name = matches[0][0]
            return _item_name_to_id[matched_name]
    
    return None


def get_item_name_by_id(item_id: str) -> Optional[str]:
    """
    Get item name by item ID.

    Args:
        item_id: BDO item ID (as string)
        
    Returns:
        Item name or None if not found
    """
    load_market_json()  # Ensure data is loaded
    
    if _item_id_to_name is None:
        return None

    return _item_id_to_name.get(str(item_id))


def get_base_price_from_cache(item_name: str, min_score: int = 86) -> Optional[int]:
    """
    Resolve an item's base price using the local market.json cache.

    Args:
        item_name: Item name to search for
        min_score: Minimum fuzzy-match score when resolving the name

    Returns:
        Base price (pre-tax) if found, else None.
    """
    if not item_name:
        return None

    items = load_market_json()
    if not items:
        return None

    candidates: list[str] = []
    name_lower = item_name.lower()
    if _item_name_to_id and name_lower in _item_name_to_id:
        candidates.append(_item_name_to_id[name_lower])

    if not candidates:
        resolved_id = get_item_id_by_name(item_name, fuzzy=True, min_score=min_score)
        if resolved_id:
            candidates.append(resolved_id)

    if not candidates:
        corrected_name, is_valid = correct_item_name(item_name, min_score=min_score)
        if corrected_name:
            corrected_lower = corrected_name.lower()
            if _item_name_to_id and corrected_lower in _item_name_to_id:
                candidates.append(_item_name_to_id[corrected_lower])
        if not is_valid and _item_name_to_id and name_lower in _item_name_to_id:
            candidates.append(_item_name_to_id[name_lower])

    for candidate_id in candidates:
        data = items.get(str(candidate_id))
        if not data:
            continue
        sub_items = data.get('sub_items') or []
        fallback_price = None
        for sub in sub_items:
            try:
                price = int(sub.get('price') or 0)
            except (TypeError, ValueError):
                continue
            if price <= 0:
                continue
            sub_key = sub.get('sub_key')
            if sub_key == 0 or sub_key == '0':
                return price
            if fallback_price is None or price < fallback_price:
                fallback_price = price
        if fallback_price is not None:
            return fallback_price

    return None


def correct_item_name(raw_name: str, min_score: int = 86) -> Tuple[str, bool]:
    """
    Correct OCR'd item name using market.json as whitelist.
    Uses RapidFuzz WRatio scorer for optimal OCR error handling.
    
    Performance: 10-50x faster than difflib.SequenceMatcher
    
    Args:
        raw_name: Raw item name from OCR
        min_score: Minimum fuzzy match score (0-100)
        
    Returns:
        Tuple of (corrected_name, is_valid)
        - corrected_name: Best match from market.json
        - is_valid: True if item found in whitelist
    """
    load_market_json()  # Ensure data is loaded
    
    if _item_name_to_id is None:
        return raw_name, False
    
    # Try exact match (case-insensitive)
    raw_lower = raw_name.lower()
    if raw_lower in _item_name_to_id:
        item_id = _item_name_to_id[raw_lower]
        correct_name = _item_id_to_name[item_id]
        return correct_name, True
    
    # Try fuzzy matching with WRatio (faster and more robust for OCR errors)
    matches = process.extract(
        raw_lower,
        _item_name_to_id.keys(),
        scorer=fuzz.WRatio,  # WRatio: weighted ratio, best for OCR errors
        limit=1
    )
    
    if matches and matches[0][1] >= min_score:
        matched_name_lower = matches[0][0]
        item_id = _item_name_to_id[matched_name_lower]
        correct_name = _item_id_to_name[item_id]
        return correct_name, True
    
    # Not found in whitelist
    return raw_name, False


def is_valid_item(item_name: str, min_score: int = 86) -> bool:
    """
    Check if item name exists in market.json whitelist.
    
    Args:
        item_name: Item name to validate
        min_score: Minimum fuzzy match score (0-100)
        
    Returns:
        True if item is in whitelist (exact or fuzzy match)
    """
    _, is_valid = correct_item_name(item_name, min_score)
    return is_valid


def get_all_item_names() -> list[str]:
    """
    Get list of all item names from market.json.
    
    Returns:
        List of all item names
    """
    load_market_json()
    
    if _item_id_to_name is None:
        return []

    return sorted(_item_id_to_name.values())


def get_item_registry() -> Dict[str, str]:
    """Return mapping of canonical item name to item ID from market.json."""
    load_market_json()

    if _item_id_to_name is None:
        return {}

    return {name: item_id for item_id, name in _item_id_to_name.items()}


def get_item_count() -> int:
    """
    Get total count of items in market.json.
    
    Returns:
        Number of items
    """
    items = load_market_json()
    return len(items)


def search_items(query: str, limit: int = 10, min_score: int = 60) -> list[Tuple[str, str, int]]:
    """
    Search for items by name (fuzzy search).
    
    Args:
        query: Search query
        limit: Maximum number of results
        min_score: Minimum fuzzy match score (0-100)
        
    Returns:
        List of tuples: (item_id, item_name, match_score)
    """
    load_market_json()
    
    if _item_name_to_id is None:
        return []
    
    matches = process.extract(
        query.lower(),
        _item_name_to_id.keys(),
        scorer=fuzz.WRatio,  # WRatio: weighted ratio for better OCR matching
        limit=limit
    )
    
    results = []
    for matched_name_lower, score, _ in matches:
        if score >= min_score:
            item_id = _item_name_to_id[matched_name_lower]
            item_name = _item_id_to_name[item_id]
            results.append((item_id, item_name, score))
    
    return results


# Initialize on module import
try:
    load_market_json()
except Exception as e:
    print(f"Warning: Could not load market.json: {e}")
