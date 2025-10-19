"""
Test Async Pipeline Controller
Validates that async mode works correctly and responsively.
"""
import pytest
import sys
import os
import time
import threading

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from tracker import MarketTracker
from config import USE_ASYNC_PIPELINE, ASYNC_QUEUE_MAXSIZE


def test_async_pipeline_enabled():
    """Verify async pipeline is enabled in config."""
    assert USE_ASYNC_PIPELINE == True, "USE_ASYNC_PIPELINE should be True for Phase 2"
    assert ASYNC_QUEUE_MAXSIZE == 1, "Queue size should be 1 for real-time tracking"


def test_async_controller_initialization():
    """Test that AsyncPipelineController can be instantiated."""
    tracker = MarketTracker(debug=False)
    
    # Verify tracker has async controller attribute
    assert hasattr(tracker, '_async_controller'), "Tracker should have _async_controller attribute"
    
    # Cleanup
    if tracker.running:
        tracker.stop()


def test_async_stop_responsiveness():
    """Test that stop() responds within 2 seconds in async mode."""
    if not USE_ASYNC_PIPELINE:
        pytest.skip("Async pipeline not enabled")
    
    tracker = MarketTracker(debug=False)
    
    # Start auto-track in background thread
    def run_tracker():
        tracker.auto_track()
    
    thread = threading.Thread(target=run_tracker, daemon=True)
    thread.start()
    
    # Wait for startup
    time.sleep(0.5)
    
    # Measure stop time
    start = time.perf_counter()
    tracker.stop()
    elapsed = time.perf_counter() - start
    
    # Wait for thread to finish
    thread.join(timeout=3.0)
    
    # Verify stop was fast
    assert elapsed < 2.0, f"Stop took {elapsed:.2f}s, expected <2s (async should be responsive)"
    print(f"✅ Stop latency: {elapsed*1000:.1f}ms (target: <2000ms)")


def test_async_single_scan():
    """Test that single_scan works in async mode."""
    tracker = MarketTracker(debug=False)
    
    # This should work regardless of async mode
    try:
        tracker.single_scan()
        # No assertion needed - just verify it doesn't crash
        print("✅ Single scan completed without errors")
    except Exception as e:
        # If focus check fails, that's OK (we're not in game)
        if "focus" not in str(e).lower() and "window" not in str(e).lower():
            raise


def test_async_mode_uses_controller():
    """Verify that async mode actually instantiates AsyncPipelineController."""
    if not USE_ASYNC_PIPELINE:
        pytest.skip("Async pipeline not enabled")
    
    tracker = MarketTracker(debug=False)
    
    # Start tracking briefly
    def run_tracker():
        tracker.auto_track()
    
    thread = threading.Thread(target=run_tracker, daemon=True)
    thread.start()
    
    # Give it time to initialize
    time.sleep(0.3)
    
    # Check that controller was created
    assert tracker._async_controller is not None, "AsyncPipelineController should be instantiated in async mode"
    
    # Cleanup
    tracker.stop()
    thread.join(timeout=3.0)


if __name__ == "__main__":
    print("Running Async Pipeline Tests...")
    print("=" * 60)
    
    test_async_pipeline_enabled()
    print("✅ Config validation passed")
    
    test_async_controller_initialization()
    print("✅ Controller initialization passed")
    
    test_async_single_scan()
    print("✅ Single scan passed")
    
    test_async_stop_responsiveness()
    print("✅ Stop responsiveness passed")
    
    test_async_mode_uses_controller()
    print("✅ Controller usage passed")
    
    print("=" * 60)
    print("🎉 All async pipeline tests passed!")
