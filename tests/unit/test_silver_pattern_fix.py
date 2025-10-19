"""
Test: Silver-Pattern Fix für unvollständige OCR-Erkennungen (Si__, Si_, Sil, etc.)

Bug: "Transaction of Concentrated Magical Black Stone x443 worth 2,908,582,950 Si__"
wurde nicht korrekt geparst, weil "Si__" nicht als "Silver" erkannt wurde.

Fix: Robusteres Silver-Pattern, das auch unvollständige Suffixe akzeptiert.
"""

import re
import sys
from pathlib import Path

# Add repo root to path for imports
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

import pytest
from parsing import extract_details_from_entry


def test_silver_pattern_with_underscores():
    """Test that 'Si__' is recognized as a valid Silver suffix."""
    ts_text = "2025.10.19 22.56"
    entry_text = "Transaction of Concentrated Magical Black Stone x443 worth 2,908,582,950 Si__"
    
    result = extract_details_from_entry(ts_text, entry_text)
    
    assert result is not None, "Entry should be parsed"
    assert result['type'] == 'transaction', f"Expected 'transaction', got '{result['type']}'"
    assert result['item'] == 'Concentrated Magical Black Stone', f"Expected 'Concentrated Magical Black Stone', got '{result['item']}'"
    assert result['qty'] == 443, f"Expected qty=443, got {result['qty']}"
    assert result['price'] == 2908582950, f"Expected price=2908582950, got {result['price']}"


def test_silver_pattern_variations():
    """Test various OCR errors for Silver suffix."""
    test_cases = [
        # (suffix, expected_to_match)
        ("Silver", True),  # Normal
        ("Si__", True),    # Double underscore (Bug-Fall)
        ("Si_", True),     # Single underscore
        ("Sil", True),     # Truncated after 'l'
        ("Silv", True),    # Truncated after 'v'
        ("Silve", True),   # Truncated after 'e'
        ("Si", True),      # Minimal match
        ("S", False),      # Too short - should NOT match
    ]
    
    for suffix, should_match in test_cases:
        ts_text = "2025.10.19 22.56"
        entry_text = f"Transaction of Test Item x100 worth 1,000,000 {suffix}"
        
        result = extract_details_from_entry(ts_text, entry_text)
        
        if should_match:
            assert result is not None, f"'{suffix}' should be recognized as Silver variant"
            assert result['price'] == 1000000, f"Price should be extracted for '{suffix}' variant"
        else:
            # For 'S' alone, we might still parse but without price - that's OK
            # The important thing is we DON'T crash
            pass


def test_silver_pattern_in_tracker_hint():
    """Test that price hints with Si__ variants are extracted correctly."""
    from tracker import MarketTracker
    
    tracker = MarketTracker(debug=False)
    
    # Simulate entry with Si__ suffix
    entry = {
        'raw': 'Transaction of Concentrated Magical Black Stone x443 worth 2,908,582,950 Si__',
        'type': 'transaction',
        'item': 'Concentrated Magical Black Stone',
        'qty': 443,
        'price': None  # Initially None (bug scenario)
    }
    
    hint_value, hint_digits = tracker._extract_price_hint(entry)
    
    assert hint_value is not None, "Price hint should be extracted from 'Si__' suffix"
    assert hint_value == 2908582950, f"Expected 2908582950, got {hint_value}"
    assert hint_digits is not None, "Hint digits should be extracted"


def test_silver_pattern_regex_directly():
    """Test the Silver pattern regex directly."""
    # Import the updated pattern
    from parsing import _SILVER_PATTERN_RAW
    
    silver_pattern = re.compile(_SILVER_PATTERN_RAW, re.IGNORECASE)
    
    test_strings = [
        ("Silver", True),
        ("Si__", True),
        ("Si_", True),
        ("Sil", True),
        ("Silv", True),
        ("Silve", True),
        ("Si", True),
        ("s1lver", True),  # OCR error: 1 instead of i
        ("sllver", True),  # OCR error: ll instead of i
        ("S", False),      # Too short
    ]
    
    for text, should_match in test_strings:
        match = silver_pattern.search(text)
        if should_match:
            assert match is not None, f"Pattern should match '{text}'"
        else:
            assert match is None, f"Pattern should NOT match '{text}'"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
