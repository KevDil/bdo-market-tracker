"""Debug script to trace full extract_details_from_entry"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsing import extract_details_from_entry

# Test the problematic entry
ts_text = "10.13 22:06"
entry_text = "Transaction of Ancient Mushroom x5 worth 585,585,OO0 Silver"

print(f"ts_text: {ts_text}")
print(f"entry_text: {entry_text}")
print()

details = extract_details_from_entry(ts_text, entry_text)

print("Extracted details:")
for key, value in details.items():
    print(f"  {key}: {value}")
