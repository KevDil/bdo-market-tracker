import os
from pathlib import Path

debug_dir = Path("debug")
log_files = list(debug_dir.glob("*.txt"))

print(f"Found {len(log_files)} log files in debug/:")
for f in log_files:
    print(f"  - {f.name} ({f.stat().st_size} bytes)")

# Check for latest log with preorder mentions
tracker_log = debug_dir / "tracker.log"
if tracker_log.exists():
    with open(tracker_log, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"\n=== Last 100 lines from tracker.log ===")
    for line in lines[-100:]:
        if any(keyword in line.lower() for keyword in ['preorder', 'relist', 'sharp black']):
            print(line.rstrip())
else:
    print("\nNo tracker.log found")

# Check for any .log files
log_files_all = list(debug_dir.glob("*.log"))
print(f"\n=== All .log files ===")
for f in log_files_all:
    print(f"  - {f.name} (modified: {f.stat().st_mtime})")
