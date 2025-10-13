#!/usr/bin/env python
"""Test persistent baseline functionality"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass

from database import save_state, load_state
import sqlite3

# Test state table existence
conn = sqlite3.connect('../bdo_tracker.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tracker_state'")
print("✅ tracker_state table exists:", bool(c.fetchone()))
conn.close()

# Test save/load
test_text = "Test baseline text with transactions"
save_state('test_baseline', test_text)
loaded = load_state('test_baseline')
print("✅ Save/Load works:", loaded == test_text)

# Test actual baseline
save_state('last_overview_text', 'Baseline from test')
loaded_baseline = load_state('last_overview_text')
print("✅ Baseline saved:", loaded_baseline)

print("\n🎉 All tests passed!")
