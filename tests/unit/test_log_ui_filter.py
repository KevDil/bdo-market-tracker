import datetime
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsing import split_text_into_log_entries  # noqa: E402


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
