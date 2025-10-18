"""
Manual regression tester for window detection heuristics.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils import detect_window_type


def main():
    ocr_text = """Central Market Ww Warehouse Balance 74,153,643,082 2025.10.11 14.01 2025.10.11 14.01 2025.10.11 14.01 2025.10.11 14.01 Placed order of Spirit's Leaf x5,000 for 20,200,000 Silver Transaction of Spirit's Leaf x5,000 worth 20,300,000 Silver has been completed: Placed order of Grim Reaper's Elixir x2,000 for 418,000,000 Silver Withdrew order of Grim Reaper's Elixir xl,991 for 416,119,000 silver Manage Warehouse Warehouse Capacity 4,155.8 / 11,000 VT 31.590 Sell Pearl Item Selling Limit 0 / 35 Sell Buy Kfse KVeo Enter search term:  Enter a search term: Items Listed   556 Sales Completed Jceeel VT Traditional Mattress Registration Count Sales Completed 2024 04-26 16.02 690,000 Cancel Re-list"""
    print("🧪 Testing window detection with ambiguous text\n")
    window_type = detect_window_type(ocr_text)
    print(f"Detected window: {window_type}")

    sell_text = """Central Market 2025.10.11 12.30 2025.10.11 12.30 Transaction of Magical Shard x100 worth 300,000,000 Silver has been completed. Listed Magical Shard x200 for 600,000,000 Silver Sales Completed 200"""
    print("\n" + "=" * 60)
    print("Testing with pure SELL overview text:\n")
    sell_window = detect_window_type(sell_text)
    print(f"Detected window: {sell_window}")

    buy_text = """Central Market 2025.10.11 14.30 Purchased Test Item x10 for 100,000 Silver Transaction of Test Item x10 worth 100,000 Silver has been completed Orders Completed"""
    print("\n" + "=" * 60)
    print("Testing with pure BUY overview text:\n")
    buy_window = detect_window_type(buy_text)
    print(f"Detected window: {buy_window}")


if __name__ == "__main__":
    main()
