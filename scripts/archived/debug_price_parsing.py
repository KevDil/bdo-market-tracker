"""Debug script to trace price extraction issue with '585,585,OO0 Silver'"""

import sys
import os
import re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import normalize_numeric_str

# Test the problematic pattern
entry_text = "Transaction of Ancient Mushroom x5 worth 585,585,OO0 Silver"
print(f"Testing entry: {entry_text}")
print()

# Test the silver pattern
silver_pat = r's\s*[iIl1]\s*[lIl1]\s*[vV]\s*[eE]\s*[rR]'
silver_sep = r'(?:\s|[^A-Za-z0-9]{1,3})*'

# Test pattern from line 417
pattern = fr'worth\s+([0-9OolI\|,\.\s]{{3,}}?){silver_sep}{silver_pat}'
print(f"Pattern: {pattern}")
print()

m = re.search(pattern, entry_text, re.IGNORECASE)
if m:
    print(f"✅ Pattern matched!")
    print(f"   Captured group 1: '{m.group(1)}'")
    print()
    
    # Try to normalize
    raw_num = m.group(1)
    normalized = normalize_numeric_str(raw_num)
    print(f"   normalize_numeric_str('{raw_num}') = {normalized}")
else:
    print(f"❌ Pattern did NOT match")
    print()
    
    # Try simpler patterns
    print("Testing simpler patterns:")
    
    # Just the worth part
    m2 = re.search(r'worth\s+([0-9OolI\|,\.\s]{3,})', entry_text, re.IGNORECASE)
    if m2:
        print(f"  ✅ 'worth <num>' matched: '{m2.group(1)}'")
    else:
        print(f"  ❌ 'worth <num>' did NOT match")
    
    # Just silver
    m3 = re.search(silver_pat, entry_text, re.IGNORECASE)
    if m3:
        print(f"  ✅ 'Silver' pattern matched: '{m3.group()}'")
    else:
        print(f"  ❌ 'Silver' pattern did NOT match")
