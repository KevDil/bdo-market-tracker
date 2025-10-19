import datetime
import sys
from pathlib import Path
from typing import Any, Optional

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
from utils import detect_window_type  # noqa: E402


SELL_ITEM_SNAPSHOT = (
    "Se11 Interface Set Pr1ce MAX 3,400,000,000 MIN 3,200,000,000 Register Quant1ty 1 "
    "Total Pr1ce 3,410,000,000 Base Price 3,390,000,000 Sell Confirm Button"
)

SELL_ITEM_FIXED_QUANTITY = (
    "Sell Interface Set Price MAX 1,200,000,000 M1N 1,180,000,000 Total Price 1,200,000,000 "
    "Confirm Sell Fixed Quantity Item (1 ea)"
)

SELL_ITEM_OCR_VARIANTS = (
    "Set Prlce M4X 2,500,000,000 rnax charts M1N 2,100,000,000 Register Quantity display hidden"
)

BUY_ITEM_SNAPSHOT = (
    "Purcha5e Desired Pr1ce 123,000,000 MAX 150,000,000 MIN 90,000,000 Desired Am0unt 2 "
    "Total C0st 246,000,000 Confirm Purchase"
)

BUY_ITEM_FIXED_AMOUNT = (
    "Purchase Desired Price 580,000,000 M4X 600,000,000 M1N 560,000,000 Total Cost 580,000,000 "
    "Confirm Purchase This item can only be bought one at a time"
)

BUY_ITEM_OCR_VARIANTS = (
    "Purchase Des1red Pr1ce rnax 77,000,000 mln 55,000,000 Total Cost 66,000,000 Confirm Purchase"
)


def test_detect_window_type_sell_item_partial_keywords():
    result = detect_window_type(SELL_ITEM_SNAPSHOT)
    assert result == "sell_item"


def test_detect_window_type_sell_item_handles_ocr_variants():
    result = detect_window_type(SELL_ITEM_OCR_VARIANTS)
    assert result == "sell_item"


def test_detect_window_type_sell_item_without_quantity():
    result = detect_window_type(SELL_ITEM_FIXED_QUANTITY)
    assert result == "sell_item"


def test_detect_window_type_buy_item_partial_keywords():
    result = detect_window_type(BUY_ITEM_SNAPSHOT)
    assert result == "buy_item"


def test_detect_window_type_buy_item_handles_ocr_variants():
    result = detect_window_type(BUY_ITEM_OCR_VARIANTS)
    assert result == "buy_item"


def test_detect_window_type_buy_item_without_amount():
    result = detect_window_type(BUY_ITEM_FIXED_AMOUNT)
    assert result == "buy_item"


def test_tracker_drops_sell_item_snapshot(monkeypatch):
    saved: list[dict[str, Any]] = []

    def fake_store(self, tx: dict[str, Any]) -> bool:
        saved.append(tx.copy())
        return True

    monkeypatch.setattr(tracker.MarketTracker, "store_transaction_db", fake_store)

    mt = tracker.MarketTracker(debug=False)
    mt.process_ocr_text(SELL_ITEM_SNAPSHOT)
    assert not saved


def test_tracker_drops_buy_item_snapshot(monkeypatch):
    saved: list[dict[str, Any]] = []

    def fake_store(self, tx: dict[str, Any]) -> bool:
        saved.append(tx.copy())
        return True

    monkeypatch.setattr(tracker.MarketTracker, "store_transaction_db", fake_store)

    mt = tracker.MarketTracker(debug=False)
    mt.process_ocr_text(BUY_ITEM_SNAPSHOT)
    assert not saved
