#!/usr/bin/env python3
"""Debug why Black Stone Powder is not saved"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tracker import MarketTracker

text = (
    "Central Market Warehouse Balance @ 64,689,571,502 Buy "
    "2025.10.12 15.12 2025.10.12 15.12 2025.10.12 15.12 "
    "Listed Black Stone Powder x100 for 470,000 Silver. "
    "Transaction of Black Stone Powder x88 worth 414,160 Silver has been completed. "
    "Withdrew Black Stone Powder x12 from market listing "
    "Items Listed 756 Sales Completed"
)

mt = MarketTracker(debug=True)
mt.process_ocr_text(text)

print("\n--- Expected ---")
print("SELL - 88x Black Stone Powder @ 414,160 Silver (sell_relist_partial)")
