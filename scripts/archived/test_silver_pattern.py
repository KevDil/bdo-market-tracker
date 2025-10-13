"""Test the silver pattern matching"""

import re

# The pattern from parsing.py
silver_pat = r's\s*[iIl1]\s*[lIl1]\s*[vV]\s*[eE]\s*[rR]'

test_cases = [
    "Silver",
    "SILVER",
    "silver",
    "SiLvEr",
    "S ilver",  # space variant
    "S1lver",  # OCR error
]

print("Testing silver pattern:")
print(f"Pattern: {silver_pat}\n")

for test in test_cases:
    m = re.search(silver_pat, test, re.IGNORECASE)
    status = "✅" if m else "❌"
    print(f"{status} '{test}' -> {m.group() if m else 'NO MATCH'}")
