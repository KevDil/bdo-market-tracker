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

from parsing import extract_details_from_entry, split_text_into_log_entries


OCR_TEXT = (
    "Central Market W Buy Warehouse Balance 78,480,390,882 Manage Warehouse "
    "Warehouse Capacity 4,829.6 / 11,000 VT 2025.10.11 23.10 2025.10.11 23.10 "
    "2025.10.11 23.07 2025.10.11 23.07 Placed order of Wild Grass x1111 for "
    "8,700,000 Silver Transaction of Wild Grass x1,111 worth 8,943,550 Silver "
    "has been completed: Placed order of Sealed Black Magic Crystal x765 for "
    "2,111,400,000 Silver Withdrew order of Sealed Black Magic Crystal x365 for "
    "1,003,750,000 silver Transaction of Sealed Black Magic Crystal x468 worth "
    "1,287,000,000 Silver ha_ Transaction of Crystal of Void Destruction xl "
    "worth 1,765,627,500 Silver ' has b: 31.590"
)


def test_crystal_of_void_destruction_transaction_is_parsed():
    entries = split_text_into_log_entries(OCR_TEXT)
    details = [
        extract_details_from_entry(ts_text, snippet)
        for _, ts_text, snippet in entries
    ]

    crystal_entries = [
        ent for ent in details
        if ent
        and ent.get("type") == "transaction"
        and (ent.get("item") or "").lower() == "crystal of void destruction"
    ]

    assert crystal_entries, "Crystal of Void Destruction transaction missing"

    crystal = crystal_entries[0]
    assert crystal["qty"] == 1
    assert crystal["price"] == 1_765_627_500
