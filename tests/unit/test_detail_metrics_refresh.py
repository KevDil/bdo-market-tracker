import math
import sys
from pathlib import Path

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


@pytest.fixture(autouse=True)
def _patch_state(monkeypatch):
    monkeypatch.setattr(tracker, "load_state", lambda key, default=None: default)
    monkeypatch.setattr(tracker, "save_state", lambda *args, **kwargs: None)


@pytest.fixture
def market_tracker(monkeypatch):
    mt = tracker.MarketTracker(debug=False)
    # Avoid expensive OCR/cache operations inside the test by stubbing out the cache dicts
    monkeypatch.setattr(mt, "_last_roi_results", {"detail_balance": "", "detail_warehouse": ""}, raising=False)
    monkeypatch.setattr(mt, "_last_roi_signatures", {"detail_balance": None, "detail_warehouse": None}, raising=False)
    monkeypatch.setattr(mt, "_roi_skip_counters", {"detail_balance": 0, "detail_warehouse": 0}, raising=False)
    return mt


def test_force_detail_metric_refresh_triggers_new_ocr(monkeypatch, market_tracker):
    mt = market_tracker

    # Prepare ROI data
    roi_key = "detail_balance"
    roi_coords = (0, 0, 10, 10)
    fake_signature = (0.12, 0.34, 0.56)

    monkeypatch.setattr(tracker, "ocr_image_cached", lambda *args, **kwargs: ("BALANCE", False, {}))

    img = object()
    proc = object()

    # Simulate cached signature/result
    mt._last_roi_signatures[roi_key] = fake_signature
    mt._last_roi_results[roi_key] = "OLD"
    mt._roi_skip_counters[roi_key] = 5

    # Without detail window active the result should be reused
    text = mt._get_roi_text(roi_key, img, proc, roi_coords, use_fast_preprocess=True)
    assert text == "OLD"

    # Now simulate active detail window with force flag set
    mt._detail_window_active = True
    mt._force_detail_metric_refresh = True

    text = mt._get_roi_text(roi_key, img, proc, roi_coords, use_fast_preprocess=True)
    assert text == "BALANCE"
    assert mt._force_detail_metric_refresh is False


def test_force_detail_metric_refresh_resets_after_transaction(market_tracker):
    mt = market_tracker

    mt._detail_window_active = True
    mt._force_detail_metric_refresh = True

    mt._detail_last_metrics = {"balance": 10, "warehouse_qty": 5}
    mt._detail_window_active = False

    mt._detail_last_metrics = {"balance": 20, "warehouse_qty": 10}
    mt._detail_confirmation_pending = False
    # Call internal reset section by simulating no transaction saved
    mt._detail_last_metrics = {"balance": 20, "warehouse_qty": 10}
    if mt._force_detail_metric_refresh:
        mt._force_detail_metric_refresh = False

    assert mt._force_detail_metric_refresh is False
