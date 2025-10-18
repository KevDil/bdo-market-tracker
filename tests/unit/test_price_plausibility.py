"""
Unit tests for price plausibility checks.

These tests avoid heavy runtime dependencies (cv2, easyocr, etc.) by
installing lightweight stubs before importing the production modules.
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


try:
    from ._stubs import install_dependency_stubs
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from _stubs import install_dependency_stubs  # type: ignore


install_dependency_stubs()

import utils  # noqa: E402
from utils import MARKET_SELL_NET_FACTOR, check_price_plausibility  # noqa: E402


def _fake_market_data(base_price: int = 3_390_000) -> dict[str, int]:
    """Provide static API data without touching the network."""
    return {
        "item_id": "44195",
        "base_price": base_price,
        "min_price": int(base_price * 0.9),
        "max_price": int(base_price * 1.1),
        "current_stock": 0,
        "total_trades": 0,
        "last_sale_price": base_price,
        "timestamp": None,
    }


def _install_fake_market_data():
    original = utils.get_item_price_range

    def _fake_get_item_price_range(item_id: str, use_cache: bool = True):
        return _fake_market_data()

    utils.get_item_price_range = _fake_get_item_price_range
    return original


def test_sell_plausibility_accepts_net_totals():
    original = _install_fake_market_data()
    try:
        qty = 129
        gross_total = 3_390_000 * qty
        net_total = int(round(gross_total * MARKET_SELL_NET_FACTOR))

        result = check_price_plausibility("Magical Shard", qty, net_total, tx_side="sell")

        assert result["plausible"], result
        assert result["reason"] in ("ok", "ok_net")
        assert result["expected_min_net"] <= net_total <= result["expected_max_net"]
    finally:
        utils.get_item_price_range = original


def test_buy_plausibility_rejects_net_totals():
    original = _install_fake_market_data()
    try:
        qty = 129
        gross_total = 3_390_000 * qty
        net_total = int(round(gross_total * MARKET_SELL_NET_FACTOR))

        result = check_price_plausibility("Magical Shard", qty, net_total, tx_side="buy")
        assert not result["plausible"]
        assert result["reason"] == "too_low"
    finally:
        utils.get_item_price_range = original


def test_sell_plausibility_rejects_extremely_low_totals():
    original = _install_fake_market_data()
    try:
        qty = 129
        result = check_price_plausibility("Magical Shard", qty, 100_000, tx_side="sell")
        assert not result["plausible"]
        assert result["reason"] == "too_low"
    finally:
        utils.get_item_price_range = original
