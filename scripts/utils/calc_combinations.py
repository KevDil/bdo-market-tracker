#!/usr/bin/env python3
"""Calculate total combinations for exhaustive benchmark."""

# TWO-PHASE APPROACH

# Canvas sizes per ROI
canvas_counts = {
    'warehouse_sell': 6,
    'warehouse_buy': 6,
    'balance': 6,
    'item_name': 6,
    'label': 6,
    'log': 5,
}

# PHASE 1: Primary parameters
text_thresh = 6
batch = 5

# PHASE 2: Secondary parameters (for top 3 configs only)
contrast = 4
adjust = 5
low = 4
link = 3

print("="*80)
print("TWO-PHASE PARAMETER OPTIMIZATION")
print("="*80)
print()

# PHASE 1 calculations
print("PHASE 1: Primary Parameters (canvas, threshold, batch)")
print("-" * 80)
phase1_per_roi = text_thresh * batch
print(f"Combinations per ROI (canvas × threshold × batch): canvas_count × {phase1_per_roi}")
print()

phase1_total = 0
for roi, canvas_count in canvas_counts.items():
    roi_phase1 = canvas_count * phase1_per_roi
    phase1_total += roi_phase1
    print(f"{roi:20s}: {canvas_count} canvas × {phase1_per_roi} = {roi_phase1} configs")

print()
print(f"PHASE 1 TOTAL: {phase1_total:,} configurations")
print()

# PHASE 2 calculations
print("PHASE 2: Secondary Parameters (for top 3 configs per ROI)")
print("-" * 80)
phase2_per_config = contrast * adjust * low * link
top_configs_per_roi = 3
phase2_per_roi = top_configs_per_roi * phase2_per_config
print(f"Combinations per ROI: {top_configs_per_roi} top configs × {phase2_per_config} = {phase2_per_roi}")
print()

phase2_total = len(canvas_counts) * phase2_per_roi
print(f"PHASE 2 TOTAL: {phase2_total:,} configurations")
print()

# GRAND TOTAL
grand_total = phase1_total + phase2_total
print("="*80)
print(f"GRAND TOTAL: {grand_total:,} configurations")
print("="*80)
print()

# Estimate time (3 runs per config, 50ms average per run)
avg_run_time = 0.05  # 50ms
runs_per_config = 3
total_seconds = grand_total * runs_per_config * avg_run_time
minutes = total_seconds / 60
hours = minutes / 60

print(f"Estimated time (50ms/run, 3 runs/config):")
print(f"  {total_seconds:,.0f} seconds")
print(f"  {minutes:.1f} minutes")
print(f"  {hours:.2f} hours")
print()
print(f"💡 Much more manageable than 456,000 configs (19 hours)!")
