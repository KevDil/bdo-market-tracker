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

from parsing import split_text_into_log_entries

_SAMPLE_TEXT = (
    "Central Market Warehouse Balance 62,412,378,665\n"
    "2025.10.14 13.09 2025.10.14 13.09 2025.10.14 11.46 2025.10.14 11.30\n"
    "Placed order of Powder of Time x1,590 for 6,375,900 Silver\n"
    "Transaction of Powder of Time x1,590 worth 6,375,900 Silver has been completed\n"
    "Transaction of Black Stone Powder x1,111 worth 5,066,160 Silver has been completed\n"
    "Placed order of Sealed Black Magic Crystal x432 for 1,136,160,000 Silver\n"
    "Transaction of Sealed Black Magic Crystal x765 worth 050,200,000 Silver has been completed\n"
    "Powder of Time Orders 1590 Orders Completed 1590 Collect Re-list\n"
    "Black Stone Powder Orders 1111 Orders Completed 1111 Collect Re-list\n"
)

_EXPECTED_TS = [
    "2025.10.14 13.09",
    "2025.10.14 13.09",
    "2025.10.14 11.46",
    "2025.10.14 11.30",
    "2025.10.14 11.30",
]
_EXPECTED_SNIPPETS = [
    "Placed order of Powder of Time",
    "Transaction of Powder of Time",
    "Transaction of Black Stone Powder",
    "Placed order of Sealed Black Magic Crystal",
    "Transaction of Sealed Black Magic Crystal",
]


def test_collect_ui_blocks_not_saved():
    entries = split_text_into_log_entries(_SAMPLE_TEXT)

    ui_entries = [snippet for _, _, snippet in entries if "Collect" in snippet]
    assert not ui_entries, "UI Collect blocks should be filtered out"

    ts_values = [ts for _, ts, _ in entries]
    assert ts_values == _EXPECTED_TS

    for expected in _EXPECTED_SNIPPETS:
        assert any(expected in snippet for _, _, snippet in entries), f"Missing entry containing '{expected}'"
