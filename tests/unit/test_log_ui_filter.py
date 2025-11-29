import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsing import extract_details_from_entry, split_text_into_log_entries  # noqa: E402


def test_split_text_filters_metrics_blocks():
    text = (
        "Items Listed 2519 Sales Completed 179\n"
        "Registration Count 764 Sales Completed\n"
        "2025.10.19 20.55 Transaction of Magical Shard x127 worth 379,734,127 Silver has been completed\n"
        "2025.10.19 20.56 Transaction of Sealed Black Magic Crystal x148 worth 441,040,000 Silver has been completed\n"
        "Collect Re-list\n"
        "Registration Count 2025 09-09 20.03 1,860,000 Cancel Re-list\n"
    )

    entries = split_text_into_log_entries(text)

    assert len(entries) == 2
    snippets = [snippet for _, _, snippet in entries]
    assert all("Transaction of" in snip for snip in snippets)
    assert not any("Registration Count" in snip for snip in snippets)


def test_split_text_handles_listed_and_transaction_combination():
    text = (
        "Items Listed 2519 Sales Completed 179\n"
        "2025.10.19 20.55 Listed Trace of Nature x2OO for 27,500,000 Silver\n"
        "2025.10.19 20.56 Transaction of Trace of Nature x80 worth 9,120,000 Silver has been completed\n"
    )

    entries = split_text_into_log_entries(text)

    assert len(entries) == 2
    details = [extract_details_from_entry(ts_text, snippet) for _, ts_text, snippet in entries]

    listed_entry = next(d for d in details if d["type"] == "listed")
    assert listed_entry["item"] and "trace" in listed_entry["item"].lower()
    assert listed_entry["qty"] == 200

    transaction_entry = next(d for d in details if d["type"] == "transaction")
    assert transaction_entry["item"] and "trace" in transaction_entry["item"].lower()
    assert transaction_entry["qty"] == 80
    assert transaction_entry["price"] == 9_120_000
