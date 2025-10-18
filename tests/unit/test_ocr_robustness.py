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

from parsing import extract_details_from_entry


def test_silver_keyword_variants_are_normalized():
    cases = [
        ("10.13 22:06", "Transaction of Birch Sap x5000 worth 585,585,000 Silve_"),
        ("10.13 22:06", "Sold Magical Shard x10 worth 23,000,000 Silve "),
        ("10.14 00:03", "Transaction of Concentrated Magical Black Stone xl3O worth 859,301,625 Silv:"),
    ]

    for ts_text, entry_text in cases:
        details = extract_details_from_entry(ts_text, entry_text)
        assert details.get("price"), f"Price missing for entry: {entry_text}"


def test_transaction_price_priority_when_qty_missing():
    tx_entry = extract_details_from_entry(
        "10.13 22:06",
        "Transaction of Birch Sap worth 585,585,000 Silver",
    )
    listed_entry = extract_details_from_entry(
        "10.13 22:06",
        "Listed Birch Sap x5000 for 650,000,000 Silver",
    )

    assert tx_entry["price"] == 585_585_000
    assert tx_entry["qty"] is None
    assert listed_entry["qty"] == 5000


def test_silver_pattern_edge_cases():
    cases = [
        ("10.13 22:06", "Transaction of Item x10 worth 1,000,000 SILVER"),
        ("10.13 22:06", "Transaction of Item x10 worth 1,000,000 silver"),
        ("10.13 22:06", "Transaction of Item x10 worth 1,000,000 SiLvEr"),
    ]

    for ts_text, entry_text in cases:
        details = extract_details_from_entry(ts_text, entry_text)
        assert details.get("price"), f"Price missing for entry: {entry_text}"
