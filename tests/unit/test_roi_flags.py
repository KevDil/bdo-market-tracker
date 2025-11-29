import datetime
import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from ._stubs import install_dependency_stubs  # type: ignore
except ImportError:  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).parent))
    from _stubs import install_dependency_stubs  # type: ignore

install_dependency_stubs()

import tracker  # noqa: E402


@pytest.fixture
def tracker_with_logs(monkeypatch):
    logs: list[str] = []

    monkeypatch.setattr(tracker, "log_debug", lambda message: logs.append(message))
    monkeypatch.setattr(tracker, "load_state", lambda key, default=None: default)
    monkeypatch.setattr(tracker, "save_state", lambda *args, **kwargs: None)
    monkeypatch.setattr(tracker, "easyocr_uses_gpu", lambda: False)
    monkeypatch.setattr(tracker, "get_easyocr_device_name", lambda: "cpu")
    monkeypatch.setattr(tracker, "PreorderManager", lambda debug=False: MagicMock())

    class _DummyCursor:
        def execute(self, *args, **kwargs):
            return None

        def fetchone(self):
            return (0,)

    monkeypatch.setattr(tracker, "get_cursor", lambda: _DummyCursor())

    mt = tracker.MarketTracker(debug=True)
    return mt, logs


def test_set_need_flag_toggles_and_logs(monkeypatch, tracker_with_logs):
    mt, logs = tracker_with_logs

    mt._needs_log_text = False
    mt._set_need_flag("log_text", True, "unit-test-enable")

    assert mt._needs_log_text is True
    assert any("[ROI-FLAG] log_text: ENABLED" in msg for msg in logs)

    logs.clear()
    mt._set_need_flag("log_text", True, "unit-test-no-change")
    assert logs == []  # no log output when value unchanged

    mt._set_need_flag("log_text", False, "unit-test-disable")
    assert mt._needs_log_text is False
    assert any("[ROI-FLAG] log_text: DISABLED" in msg for msg in logs)


def test_set_detail_metric_state_transitions_toggle_flags(monkeypatch, tracker_with_logs):
    mt, _ = tracker_with_logs

    calls: list[tuple[str, bool, str]] = []

    def _capture(flag_name: str, value: bool, reason: str = "") -> None:
        calls.append((flag_name, value, reason))

    monkeypatch.setattr(mt, "_set_need_flag", _capture)

    mt._detail_metric_state = "idle"
    mt._detail_window_type = "buy_item"

    mt._set_detail_metric_state("baseline", "unit-test-baseline")
    assert mt._detail_metric_state == "baseline"
    assert ("detail_balance", True, "detail_state_baseline") in calls
    assert ("detail_warehouse", True, "detail_state_baseline") in calls
    assert ("detail_inputs", True, "detail_state_baseline") in calls

    calls.clear()
    mt._set_detail_metric_state("delta", "unit-test-delta")
    assert mt._detail_metric_state == "delta"
    assert calls == []  # delta state does not toggle flags by default

    mt._set_detail_metric_state("idle", "unit-test-idle")
    assert mt._detail_metric_state == "idle"
    assert ("detail_balance", False, "detail_state_idle") in calls
    assert ("detail_warehouse", False, "detail_state_idle") in calls
    assert ("detail_inputs", False, "detail_state_idle") in calls

    calls.clear()
    mt._set_detail_metric_state("invalid", "unit-test-invalid")
    assert mt._detail_metric_state == "idle"  # unchanged
    assert calls == []


def test_schedule_metrics_refresh_respects_rate_limit(monkeypatch, tracker_with_logs):
    mt, _ = tracker_with_logs

    calls: list[tuple[str, bool, str]] = []

    def _capture(flag_name: str, value: bool, reason: str = "") -> None:
        calls.append((flag_name, value, reason))

    monkeypatch.setattr(mt, "_set_need_flag", _capture)

    mt._burst_until = None
    mt._request_immediate_rescan = 0
    mt._last_metrics_refresh_time = None

    mt._schedule_metrics_refresh("initial")
    assert calls == [("metrics_text", True, "initial")]

    calls.clear()
    mt._burst_until = None
    mt._request_immediate_rescan = 0
    mt._last_metrics_refresh_time = datetime.datetime.now()
    mt._pending_metrics_refresh = False

    mt._schedule_metrics_refresh("rate-limited")
    assert calls == [("metrics_text", True, "metrics_refresh_rate_limited")]
    assert mt._pending_metrics_refresh is True

    mt._burst_until = datetime.datetime.now() + datetime.timedelta(seconds=2)
    mt._pending_metrics_refresh = False
    calls.clear()
    mt._schedule_metrics_refresh("burst")
    assert calls == [("metrics_text", True, "burst")]
    assert mt._pending_metrics_refresh is True


def test_detail_roi_ocr_respects_need_flags(monkeypatch, tracker_with_logs):
    mt, _ = tracker_with_logs

    # Stub heavy dependencies to keep test lightweight
    monkeypatch.setattr(tracker, "preprocess", lambda img, **_: img)
    monkeypatch.setattr(tracker, "get_preprocessed_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(tracker, "set_preprocessed_frame", lambda *args, **kwargs: None)
    monkeypatch.setattr(tracker, "compute_roi_stats_signature", lambda proc, roi: (roi, 1, 1))
    monkeypatch.setattr(tracker, "compare_roi_signatures", lambda current, last: False)

    monkeypatch.setattr(tracker, "detect_window_label_roi", lambda img: (0, 0, 10, 10))
    monkeypatch.setattr(tracker, "detect_log_roi", lambda img: (0, 0, 10, 10))
    monkeypatch.setattr(tracker, "detect_metrics_roi", lambda img: None)
    monkeypatch.setattr(tracker, "detect_detail_item_name_roi", lambda proc, wtype: (0, 0, 5, 5))
    monkeypatch.setattr(tracker, "detect_detail_balance_roi", lambda proc, wtype: (0, 0, 5, 5))
    monkeypatch.setattr(tracker, "detect_detail_warehouse_roi", lambda proc, wtype: (0, 0, 5, 5))

    labels_seen: list[str] = []

    def fake_ocr(*args, **kwargs):
        label = kwargs.get("roi_label", "")
        labels_seen.append(label)
        if label == "label":
            return ("Set Price", False, {"cache_age": 0})
        if label == "detail_item_name":
            return ("Test Item", False, {})
        if label == "detail_balance":
            return ("Balance 123", False, {})
        if label == "detail_warehouse":
            return ("Warehouse 456", False, {})
        return ("", False, {})

    monkeypatch.setattr(tracker, "ocr_image_cached", fake_ocr)

    test_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

    # Scenario 1: Flags disabled -> no detail OCR
    mt._needs_detail_balance = False
    mt._needs_detail_warehouse = False
    mt._needs_log_text = False

    labels_seen.clear()
    mt._process_image(test_frame, context="unit", metrics={})

    assert "detail_balance" not in labels_seen
    assert "detail_warehouse" not in labels_seen
    assert mt._roi_usage_last_scan["detail_balance"] in {"skipped", "not_run"}
    assert mt._roi_usage_last_scan["detail_warehouse"] in {"skipped", "not_run"}

    # Scenario 2: Flags enabled -> detail OCR is executed
    mt._needs_detail_balance = True
    mt._needs_detail_warehouse = True
    mt._detail_window_item = None

    labels_seen.clear()
    mt._process_image(test_frame, context="unit", metrics={})

    assert "detail_balance" in labels_seen
    assert "detail_warehouse" in labels_seen
    assert mt._roi_usage_last_scan["detail_balance"] == "ocr"
    assert mt._roi_usage_last_scan["detail_warehouse"] == "ocr"
    assert mt._needs_detail_balance is False
    assert mt._needs_detail_warehouse is False


def test_detail_delta_idle_timeout_returns_to_baseline(monkeypatch, tracker_with_logs):
    mt, _ = tracker_with_logs

    # Setup detail window state
    base_balance = 1_000_000
    base_warehouse = 0
    mt._detail_window_active = True
    mt._detail_window_type = "buy_item"
    mt._detail_baseline_captured = True
    mt._detail_metric_state = "delta"
    mt._detail_baseline_balance = base_balance
    mt._detail_baseline_warehouse = base_warehouse
    mt._detail_last_metrics = {"balance": base_balance, "warehouse_qty": base_warehouse}
    mt._detail_window_item = "Test Item"
    mt._detail_needs_baseline_capture = False
    mt._force_detail_metric_refresh = False
    mt._burst_until = None
    mt._request_immediate_rescan = 0
    mt._detail_last_delta_activity = datetime.datetime.now() - datetime.timedelta(seconds=mt.DETAIL_DELTA_IDLE_TIMEOUT + 0.5)

    monkeypatch.setattr(
        mt,
        "_extract_detail_window_metrics",
        lambda ocr_text, window_type: {
            "balance": base_balance,
            "warehouse_qty": base_warehouse,
            "item_name": "Test Item",
        },
    )

    state_transitions: list[tuple[str, str]] = []
    original_set_state = mt._set_detail_metric_state

    def _capture_state(state: str, reason: str = "") -> None:
        state_transitions.append((state, reason))
        original_set_state(state, reason)

    monkeypatch.setattr(mt, "_set_detail_metric_state", _capture_state)

    mt._monitor_detail_window("buy_item", "dummy text")

    assert mt._detail_metric_state == "baseline"
    assert mt._detail_needs_baseline_capture is True
    assert mt._force_detail_metric_refresh is True


def test_monitor_detail_window_sets_baseline_and_delta(monkeypatch, tracker_with_logs):
    mt, _ = tracker_with_logs

    initial_balance = 1_234_567
    initial_warehouse = 0

    monkeypatch.setattr(mt, "_extract_detail_window_metrics", lambda ocr_text, window_type: {
        "balance": initial_balance,
        "warehouse_qty": initial_warehouse,
        "item_name": "Test Item",
    })
    monkeypatch.setattr(mt, "_extract_preorder_input_fields", lambda *_, **__: None)
    monkeypatch.setattr(mt, "_safe_correct_item_name", lambda raw_name, min_score=86: (raw_name, True))

    mt._detail_window_active = False
    mt._detail_window_type = "buy_item"
    mt._needs_detail_balance = False
    mt._needs_detail_warehouse = False
    mt._needs_detail_inputs = False

    mt._set_detail_metric_state("baseline", "unit-test-baseline")

    mt._monitor_detail_window("buy_item", "dummy text")

    assert mt._detail_window_active is True
    assert mt._detail_metric_state == "delta"
    assert mt._detail_baseline_captured is True
    assert mt._detail_baseline_balance == initial_balance
    assert mt._detail_baseline_warehouse == initial_warehouse
    assert mt._detail_window_item == "Test Item"
    assert mt._needs_detail_balance is True
    assert mt._needs_detail_warehouse is True
    assert mt._needs_detail_inputs is True
    assert mt._detail_last_delta_activity is not None
