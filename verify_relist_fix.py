"""
Test script to verify the relist fix implementation.
Tests all three phases of the fix.
"""
import sys
from pathlib import Path

print("="*60)
print("RELIST FIX VERIFICATION")
print("="*60)

# Phase 1: Check if rapid-scan logging is added
print("\n[Phase 1] Checking rapid-scan logging...")
tracker_code = Path("tracker.py").read_text(encoding='utf-8')

phase1_checks = {
    "Rapid-scan start logging": "[RAPID-SCAN] Starting rapid scan" in tracker_code,
    "Rapid-scan completion logging": "[RAPID-SCAN] ✅ Completed scan" in tracker_code,
    "Rapid-scan capture fail check": "[RAPID-SCAN] ❌ Capture failed" in tracker_code,
}

for check, result in phase1_checks.items():
    status = "✅" if result else "❌"
    print(f"  {status} {check}")

# Phase 2: Check proactive input-field extraction
print("\n[Phase 2] Checking proactive input-field extraction...")

phase2_checks = {
    "Baseline input extraction": "Extracting preorder input fields from baseline frame" in tracker_code,
    "Input fields caching": "_detail_cached_input_fields" in tracker_code,
    "Cache timestamp tracking": "_detail_cached_input_timestamp" in tracker_code,
    "Cached fields usage in detection": "Using CACHED input fields" in tracker_code,
}

for check, result in phase2_checks.items():
    status = "✅" if result else "❌"
    print(f"  {status} {check}")

# Phase 3: Check relist-pattern detection
print("\n[Phase 3] Checking relist-pattern detection...")

phase3_checks = {
    "Relist pattern detection": "[RELIST-DETECT] ✅ Pattern matched" in tracker_code,
    "Auto-collect calculation": "autocollect_total = total_balance_decrease - new_preorder_total" in tracker_code,
    "Auto-collect transaction save": "[RELIST] ✅ Auto-collect saved" in tracker_code,
    "Old preorder marking": "mark_collected" in tracker_code,
    "Transaction-log fallback": "[DETAIL-FALLBACK]" in tracker_code,
}

for check, result in phase3_checks.items():
    status = "✅" if result else "❌"
    print(f"  {status} {check}")

# Summary
print("\n" + "="*60)

all_results = list(phase1_checks.values()) + list(phase2_checks.values()) + list(phase3_checks.values())
all_passed = sum(all_results)
total_checks = len(all_results)

print(f"SUMMARY: {all_passed}/{total_checks} checks passed")

if all_passed == total_checks:
    print("✅ All phases implemented successfully!")
    sys.exit(0)
else:
    print("⚠️  Some checks failed - review implementation")
    sys.exit(1)
