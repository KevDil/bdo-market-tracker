"""
Debug window detection
"""
import sys
import os
import re
# Add project root (two levels up from scripts/utils/) to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

ocr_text = """Central Market Ww Warehouse Balance 74,153,643,082 2025.10.11 14.01 2025.10.11 14.01 2025.10.11 14.01 2025.10.11 14.01 Placed order of Spirit's Leaf x5,000 for 20,200,000 Silver Transaction of Spirit's Leaf x5,000 worth 20,300,000 Silver has been completed: Placed order of Grim Reaper's Elixir x2,000 for 418,000,000 Silver Withdrew order of Grim Reaper's Elixir xl,991 for 416,119,000 silver Manage Warehouse Warehouse Capacity 4,155.8 / 11,000 VT 31.590 Sell Pearl Item Selling Limit 0 / 35 Sell Buy Kfse KVeo Enter search term:  Enter a search term: Items Listed   556 Sales Completed Jceeel VT Traditional Mattress Registration Count Sales Completed 2024 04-26 16.02 690,000 Cancel Re-list"""

s = ocr_text.lower()
s_norm = re.sub(r"\s+", " ", s)

print("Normalized text (first 500 chars):")
print(s_norm[:500])
print()

sell_pat = re.compile(r"sa?les?\s+(?:comp(?:l|1|i)et(?:e|ed|ion)s?|pl?et(?:e|ed|ion)s?)", re.IGNORECASE)
buy_pat = re.compile(r"orders?\s+(?:comp(?:l|1|i)et(?:e|ed|ion)s?|pl?et(?:e|ed|ion)s?)", re.IGNORECASE)

sell_match = sell_pat.search(s_norm)
buy_match = buy_pat.search(s_norm)

print(f"sell_match: {sell_match}")
if sell_match:
    print(f"  Text: '{s_norm[sell_match.start():sell_match.end()]}'")
    print(f"  Position: {sell_match.start()}")
print(f"buy_match: {buy_match}")
print()

# Check if "orders" appears anywhere
if "orders" in s_norm:
    print("'orders' FOUND in text")
    orders_pos = s_norm.find("orders")
    print(f"  Context: ...{s_norm[max(0,orders_pos-20):orders_pos+50]}...")
else:
    print("'orders' NOT found in text")
print()

if sell_match and buy_match:
    print("BOTH matched!")
    print(f"sell_match position: {sell_match.start()}")
    print(f"buy_match position: {buy_match.start()}")
    print()
    
    # Check anchors
    placed_order = re.search(r"\b(placed\s+order)\b", s_norm, re.IGNORECASE)
    purchased = re.search(r"\b(purchased?)\b", s_norm, re.IGNORECASE)
    listed = re.search(r"\b(listed)\b", s_norm, re.IGNORECASE)
    
    print(f"'placed order' anchor: {placed_order}")
    print(f"'purchased' anchor: {purchased}")
    print(f"'listed' anchor: {listed}")
