import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tracker import MarketTracker


HELIX_SNAPSHOT = (
    "Central Market W Buy Warehouse Balance 22,517,116,664 "
    "2025.10.17 18.07 Placed order of Helix Elixir x500 for 82,000,000 Silver "
    "2025.10.17 18.07 Transaction of Helix Elixir x500 worth 82,000,000 Silver has been completed "
    "2025.10.17 17.59 Placed order of Pine Sap x3,835 for 35,090,250 Silver "
    "2025.10.17 17.59 Withdrew order of Pine Sap x3,835 for 35,090,250 silver "
    "Sell Pearl Item Selling Limit 0 / 35 Sell Enter search term: Enter search term: Orders   90563 Orders Completed   11776 Collect "
    "2025.10.17 18.31 Placed order of Rhino Blood x5,000 for 74,000,000 Silver "
    "2025.10.17 18.31 Transaction of Rhino Blood x4,554 worth 68,310,000 Silver has been completed"
)


def reset_recent():
    conn = sqlite3.connect('bdo_tracker.db')
    cur = conn.cursor()
    cur.execute("DELETE FROM transactions WHERE timestamp >= '2025-10-17 18:00:00'")
    conn.commit()
    conn.close()


def fetch_transactions():
    conn = sqlite3.connect('bdo_tracker.db')
    cur = conn.cursor()
    cur.execute(
        """
        SELECT item_name, quantity, price, transaction_type, timestamp
        FROM transactions
        WHERE timestamp >= '2025-10-17 18:00:00'
        ORDER BY timestamp
        """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def test_no_timestamp_jump():
    reset_recent()
    tracker = MarketTracker(debug=False)
    tracker.process_ocr_text(HELIX_SNAPSHOT)

    rows = fetch_transactions()
    # Expect exactly two rows: Helix @ 18:07, Rhino @ 18:31
    assert len(rows) == 2, f"Expected 2 rows, got {len(rows)}: {rows}"

    helix = rows[0]
    rhino = rows[1]

    assert helix[0] == 'Helix Elixir', f"First entry should be Helix Elixir, got {helix}"
    assert helix[4] == '2025-10-17 18:07:00', f"Helix timestamp drifted: {helix[4]}"

    assert rhino[0] == 'Rhino Blood', f"Second entry should be Rhino Blood, got {rhino}"
    assert rhino[4] == '2025-10-17 18:31:00'

    print('✅ Helix regression passed: historical timestamp preserved and Rhino stored once')


if __name__ == "__main__":
    try:
        test_no_timestamp_jump()
    except AssertionError as exc:
        print(f"❌ Regression failed: {exc}")
        sys.exit(1)
    except Exception as exc:
        print(f"❌ Unexpected error: {exc}")
        sys.exit(1)
    sys.exit(0)
