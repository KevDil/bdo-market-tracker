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


POWDER_SNAPSHOT = (
    "Central Market Warehouse Balance 44,806,841,936 W Buy 2025.10.17 17.40 "
    "Transaction of Powder of Darkness x577 worth 609,830 Silver has been com "
    "2025.10.17 17.40 Placed order of Pine Sap x5,000 for 45,750,000 Silver "
    "2025.10.17 17.40 Withdrew order of Pine Sap x4,387 for 39,702,350 silver "
    "Warelouse Lzoacivy Sell Pearl Item Selling Limit 31.590 2025.10.17 17.40 "
    "1comp0Z Transaction of Pine Sap x613 worth 5,547,650 Silver has been Buy "
    "FCSUO Enter search term. 0 / 35 Sell Enter search term: Orders   99539 "
    "Orders Completed 7222 Collect AII VT Birch Sap Orders 5000 Orders "
    "Completed 5000 Collect Re-list 2776 5CCO SCCO 3038 Spirit's Leaf Orders "
    "1111 Orders Completed 1111 Collect JC01 696 1689 SCO 1407 Re-list 1036 "
    "ICCO 891 Powder of Darkness Orders : 533 Orders Completed Cancel "
    "1,487,070 Re-list 189 166 Legendary Beast's Blood Orders 1117 Ordere "
    "Comnleted . 1117 Collect"
)


def test_powder_transaction_price_and_qty():
    entries = split_text_into_log_entries(POWDER_SNAPSHOT)
    powder_details = None
    for _, ts_text, snippet in entries:
        details = extract_details_from_entry(ts_text, snippet)
        if details['type'] == 'transaction' and (details['item'] or '').lower() == 'powder of darkness':
            powder_details = details
            break

    assert powder_details is not None, "Powder of Darkness transaction not parsed"
    assert powder_details['qty'] == 577
    assert powder_details['price'] == 609830
