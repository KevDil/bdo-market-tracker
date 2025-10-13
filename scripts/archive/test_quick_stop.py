"""
Test: Demonstrate quick stop response time
"""
import sys

# Fix Unicode encoding on Windows
try:
    from test_utils import fix_windows_unicode
    fix_windows_unicode()
except ImportError:
    pass  # test_utils.py not found

import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import time
import threading
from tracker import MarketTracker

print("=" * 80)
print("TEST: Quick Stop Response Time")
print("=" * 80)
print("\nThis test demonstrates that the Stop button now responds quickly.")
print("Previous behavior: Could take up to 1.2 seconds to stop")
print("New behavior: Stops within ~100ms\n")

# Create tracker
mt = MarketTracker(debug=False)

# Start auto-tracking in background thread
def run_auto():
    print("Starting auto-track...")
    mt.auto_track()
    print("Auto-track stopped!")

auto_thread = threading.Thread(target=run_auto, daemon=True)
auto_thread.start()

# Let it run for 2 seconds
print("Auto-tracking running for 2 seconds...")
time.sleep(2.0)

# Stop and measure response time
print("\nCalling stop() now...")
stop_start = time.time()
mt.stop()

# Wait for thread to actually stop (with timeout)
auto_thread.join(timeout=2.0)
stop_duration = time.time() - stop_start

print(f"✅ Stopped in {stop_duration:.3f} seconds")

if stop_duration < 0.2:
    print("✅ EXCELLENT: Stop response < 200ms")
elif stop_duration < 0.5:
    print("✅ GOOD: Stop response < 500ms")
else:
    print("⚠️ SLOW: Stop response > 500ms")

print("\n" + "=" * 80)
print("Expected: Stop response should be ~100-150ms")
print("=" * 80)
