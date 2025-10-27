"""
Integration test: Validates ROI-Diffing skip behavior in idle scenario.

This test simulates repeated scans of identical frames (no transactions)
and validates that ROI-Diffing achieves >80% skip rate after warm-up.

IMPORTANT:
- Images must be numpy arrays (BGR format), NOT PIL Images
- Patch utils.* functions, NOT tracker.* (imports are direct from utils)
"""

import sys
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from ._stubs import install_dependency_stubs  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from _stubs import install_dependency_stubs  # type: ignore

install_dependency_stubs()

from tracker import MarketTracker  # noqa: E402

DUMMY_LOG_ROI = (0, 0, 1100, 350)
DUMMY_METRICS_ROI = (0, 350, 1100, 700)
DUMMY_LABEL_ROI = (0, 0, 1100, 100)
DUMMY_SIG = ("hash", 12345)


class TestROIIdleSkip(unittest.TestCase):
    """Integration test for ROI-Diffing idle skip behavior."""

    def setUp(self):
        """Create test tracker with debug mode."""
        self.tracker = MarketTracker()
        self.tracker.debug = True
        # Initialize stable window state
        self.tracker._stable_window = 'sell_overview'
        self.tracker._window_detection_history = ['sell_overview', 'sell_overview']
        # Increase force-refresh threshold so skip counters can accumulate during tests
        self.tracker._roi_force_refresh_threshold = 999
        self.tracker._last_roi_signatures = {
            "log": DUMMY_SIG,
            "label": DUMMY_SIG,
            "metrics": DUMMY_SIG,
        }
        
    def test_idle_scenario_skip_rate(self):
        """Test: >80% skip rate with identical frames in idle scenario."""
        # Create a SINGLE mock image (1100x700 pixels) - reuse for all scans!
        # NOTE: Must be numpy array (BGR format) not PIL Image, matching mss.grab() output
        np.random.seed(42)  # Fixed seed for deterministic test
        img = np.random.randint(0, 255, (700, 1100, 3), dtype=np.uint8)  # BGR numpy array
        
        # Mock OCR to return stable "sell_overview" window
        mock_ocr_text = """
        Orders: 10
        Orders Completed: 5
        Remaining Price: 1,000,000 Silver
        """
        
        # CRITICAL: Patch utils.* not tracker.* because tracker imports directly from utils!
        def compare_side_effect(*_args, **_kwargs):
            # Simulate stable ROI (skip) by letting counters increment naturally
            return True

        with patch('utils.ocr_image_cached') as mock_ocr, \
             patch('utils.detect_window_type') as mock_detect_window, \
             patch('utils.detect_log_roi', return_value=DUMMY_LOG_ROI) as mock_detect_log, \
             patch('utils.detect_metrics_roi', return_value=DUMMY_METRICS_ROI) as mock_detect_metrics, \
             patch('utils.detect_window_label_roi', return_value=DUMMY_LABEL_ROI) as mock_detect_label, \
             patch('tracker.compute_roi_stats_signature', return_value=DUMMY_SIG), \
             patch('tracker.compare_roi_signatures', side_effect=compare_side_effect):
            
            # Configure mocks
            def ocr_side_effect(img, method, use_roi, preprocessed, fast_mode, roi, roi_label, cache_tag):
                # Return same text for all ROIs
                return mock_ocr_text, False, {"cache_size": 0, "cache_age": 0.0}
            
            mock_ocr.side_effect = ocr_side_effect
            mock_detect_window.return_value = 'sell_overview'
            mock_detect_log.return_value = DUMMY_LOG_ROI  # Stable ROI
            mock_detect_metrics.return_value = DUMMY_METRICS_ROI  # Stable ROI
            mock_detect_label.return_value = DUMMY_LABEL_ROI  # Stable label ROI
            
            # Run 20 scans with IDENTICAL frames (same img object)
            ocr_call_count = 0
            for i in range(20):
                # Process same image repeatedly (context must be string, not array)
                result = self.tracker._process_image(img, context='test_idle')
                
                # Count OCR calls
                ocr_call_count = mock_ocr.call_count
                
                # Debug: Print state after scan
                if i < 5 or i == 19:
                    print(f"Scan {i}: current_window={self.tracker.current_window}, stable={self.tracker._stable_window}, "
                          f"log_skips={self.tracker._roi_skip_counters.get('log', 0)}, "
                          f"metrics_skips={self.tracker._roi_skip_counters.get('metrics', 0)}, "
                          f"pending={self.tracker._pending_metrics_refresh}")
                
                # After scan 3, we should start seeing skips
                if i >= 3:
                    # Check that skip counters are incrementing
                    log_skips = self.tracker._roi_skip_counters.get("log", 0)
                    metrics_skips = self.tracker._roi_skip_counters.get("metrics", 0)
                    
                    # At least one ROI should be skipping
                    total_skips = log_skips + metrics_skips
                    self.assertGreater(total_skips, 0, 
                        f"Scan {i}: No ROI skips detected (log={log_skips}, metrics={metrics_skips})")
            
            # Calculate skip rate
            # Expected: ~3 ROIs per scan without skipping
            # 20 scans × 3 ROIs = 60 potential calls
            # With >80% skip rate after warm-up: expect <12 actual calls
            max_expected_calls = 60 * 0.20  # 20% actually executed = 12 calls
            
            self.assertLess(ocr_call_count, max_expected_calls,
                f"OCR called {ocr_call_count} times (expected <{max_expected_calls:.0f} with >80% skip rate)")
            
            # Verify skip counters show activity
            log_skips = self.tracker._roi_skip_counters.get("log", 0)
            label_skips = self.tracker._roi_skip_counters.get("label", 0)
            metrics_skips = self.tracker._roi_skip_counters.get("metrics", 0)
            
            total_skips = log_skips + label_skips + metrics_skips
            self.assertGreater(total_skips, 15,
                f"Expected >15 cumulative skips across all ROIs, got {total_skips}")
            
            print(f"\n✓ Idle scenario skip rate test passed:")
            print(f"  - OCR calls: {ocr_call_count}/60 ({100*(1-ocr_call_count/60):.1f}% skipped)")
            print(f"  - Log skips: {log_skips}")
            print(f"  - Label skips: {label_skips}")
            print(f"  - Metrics skips: {metrics_skips}")

    def test_window_transition_resets_hashes(self):
        """Test: Window transitions reset ROI hashes to prevent stale skips."""
        # NOTE: Must be numpy array (BGR format) not PIL Image
        np.random.seed(42)
        img = np.random.randint(0, 255, (700, 1100, 3), dtype=np.uint8)
        
        with patch('utils.ocr_image_cached') as mock_ocr, \
             patch('utils.detect_window_type') as mock_detect_window, \
             patch('utils.detect_log_roi', return_value=DUMMY_LOG_ROI) as mock_detect_log, \
             patch('utils.detect_metrics_roi', return_value=DUMMY_METRICS_ROI) as mock_detect_metrics, \
             patch('utils.detect_window_label_roi', return_value=DUMMY_LABEL_ROI) as mock_detect_label, \
             patch('tracker.compute_roi_stats_signature', return_value=DUMMY_SIG), \
             patch('tracker.compare_roi_signatures', return_value=True):
            
            # Setup mocks
            mock_ocr.return_value = ("Orders: 10", False, {"cache_size": 0, "cache_age": 0.0})
            mock_detect_log.return_value = (0, 0, 1100, 350)
            mock_detect_metrics.return_value = (0, 350, 1100, 700)
            mock_detect_label.return_value = (0, 0, 1100, 100)
            
            # Scan 1-3: sell_overview (build up skip counters)
            mock_detect_window.return_value = 'sell_overview'
            for i in range(3):
                self.tracker._process_image(img, context='test_transition')
            
            # Verify skips are accumulating
            log_skips_before = self.tracker._roi_skip_counters.get("log", 0)
            self.assertGreater(log_skips_before, 0, "Expected skip counters before transition")
            
            # Scan 4-5: Transition to buy_overview (requires 2 detections due to hysteresis)
            mock_detect_window.return_value = 'buy_overview'
            self.tracker._process_image(img, context='test_transition')
            self.tracker._process_image(img, context='test_transition')
            
            # Verify signatures were reset
            self.assertEqual(self.tracker._last_roi_signatures["log"], None,
                "Log signature should be reset after window transition")
            self.assertEqual(self.tracker._roi_skip_counters["log"], 0,
                "Log skip counter should be reset after window transition")

    def test_force_refresh_after_threshold(self):
        """Test: Force-refresh triggers after N consecutive skips."""
        # NOTE: Must be numpy array (BGR format) not PIL Image
        np.random.seed(42)
        img = np.random.randint(0, 255, (700, 1100, 3), dtype=np.uint8)
        
        def compare_side_effect(*_args, **_kwargs):
            return True

        with patch('utils.ocr_image_cached') as mock_ocr, \
             patch('utils.detect_window_type') as mock_detect_window, \
             patch('utils.detect_log_roi', return_value=DUMMY_LOG_ROI) as mock_detect_log, \
             patch('utils.detect_window_label_roi', return_value=DUMMY_LABEL_ROI) as mock_detect_label, \
             patch('utils.detect_metrics_roi', return_value=DUMMY_METRICS_ROI) as mock_detect_metrics, \
             patch('tracker.compute_roi_stats_signature', return_value=DUMMY_SIG), \
             patch('tracker.compare_roi_signatures', side_effect=compare_side_effect):
            
            mock_ocr.return_value = ("Orders: 10", False, {"cache_size": 0, "cache_age": 0.0})
            mock_detect_window.return_value = 'sell_overview'
            mock_detect_log.return_value = DUMMY_LOG_ROI
            mock_detect_label.return_value = DUMMY_LABEL_ROI
            mock_detect_metrics.return_value = DUMMY_METRICS_ROI
            
            # Run enough scans to exceed force-refresh threshold
            # Restore default-like behaviour for this specific test
            self.tracker._roi_force_refresh_threshold = 3
            threshold = self.tracker._roi_force_refresh_threshold
            for i in range(threshold + 5):
                self.tracker._process_image(img, context='test_force_refresh')
            
            # Check that force-refresh happened (skip counter reset)
            log_skips = self.tracker._roi_skip_counters.get("log", 0)
            self.assertLess(log_skips, threshold,
                f"Expected skip counter reset after {threshold} skips, got {log_skips}")


if __name__ == '__main__':
    unittest.main()
