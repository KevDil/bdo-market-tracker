"""Debug: Analyze timestamp and event positions"""
import sys
import os
# Add project root (two levels up from scripts/utils/) to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from parsing import find_all_timestamps

text = """2025.10.11 11.05 2025.10.11 10.56 2025.10.11 10.50 2025.10.11 10.50 
Listed Magical Shard x200 for 640,000,000 Silver 
Transaction of Magical Shard x130 worth 367,942,575 Silver 
Placed order of Spirit's Leaf x5,000"""

print("=" * 60)
print("TEXT ANALYSIS")
print("=" * 60)
print("\nFull text:")
print(repr(text[:200]))
print("\n" + "=" * 60)
print("TIMESTAMPS:")
print("=" * 60)
ts_positions = find_all_timestamps(text)
for pos, ts_text in ts_positions:
    # Show what comes after each timestamp
    after = text[pos:pos+50].replace('\n', '\\n')
    print(f"pos={pos:3d}, ts='{ts_text}', after='{after}'")

print("\n" + "=" * 60)
print("EVENTS:")
print("=" * 60)
events = [
    ("Listed", text.find("Listed")),
    ("Transaction", text.find("Transaction")),
    ("Placed", text.find("Placed"))
]
for name, pos in events:
    if pos >= 0:
        # Find closest timestamp BEFORE this event
        preceding = [(p, t) for p, t in ts_positions if p < pos]
        if preceding:
            closest_pos, closest_ts = max(preceding, key=lambda x: x[0])  # max = closest (last one before)
            distance = pos - closest_pos
            print(f"{name:12s} at pos={pos:3d}, closest_ts='{closest_ts}' (distance={distance} chars)")
        else:
            print(f"{name:12s} at pos={pos:3d}, NO preceding timestamp!")

print("\n" + "=" * 60)
print("EXPECTED ASSIGNMENT:")
print("=" * 60)
print("Listed       -> 11.05 (first/closest timestamp)")
print("Transaction  -> 10.56 (second timestamp)")
print("Placed       -> 10.50 (third/fourth timestamp)")
