import datetime
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from ._stubs import install_dependency_stubs  # type: ignore
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from _stubs import install_dependency_stubs  # type: ignore

install_dependency_stubs()

from parsing import extract_details_from_entry


def test_ts_text_takes_precedence_over_inline_timestamp():
    ts_text = "2025.10.18 12.51"
    entry = (
        "Transaction of Black Stone xl,111 worth 145,541,000 Silver has been complet: "
        "2025.10.18 13.12 2025.10.18 12.51 Warehouse Capacity 7,795.3 / 11,000 VT"
    )

    details = extract_details_from_entry(ts_text, entry)
    assert details["timestamp"] == datetime.datetime(2025, 10, 18, 12, 51)


def test_inline_timestamp_used_when_ts_text_missing():
    ts_text = None
    entry = (
        "Transaction of Magical Shard x200 worth 585,585,000 Silver has been complet___ "
        "2025.10.18 13.12"
    )

    details = extract_details_from_entry(ts_text, entry)
    assert details["timestamp"] == datetime.datetime(2025, 10, 18, 13, 12)
