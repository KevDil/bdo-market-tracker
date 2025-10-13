#!/usr/bin/env python3
"""
Performance Benchmark: RapidFuzz vs difflib für Item-Name-Korrektur

Vergleicht die Performance von:
1. RapidFuzz (aktuelle Implementation in market_json_manager.py)
2. difflib.SequenceMatcher (alte Methode)

Erwartete Ergebnisse:
- RapidFuzz: 10-50x schneller als difflib
- Bessere Genauigkeit bei OCR-Fehlern (WRatio scorer)
"""

import time
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from market_json_manager import correct_item_name, get_all_item_names
from difflib import SequenceMatcher


def correct_item_name_difflib(raw_name: str, item_whitelist: list, min_score: float = 0.86):
    """
    Legacy implementation using difflib.SequenceMatcher.
    Kept for benchmark comparison only.
    """
    if not raw_name or not item_whitelist:
        return raw_name, False
    
    raw_lower = raw_name.lower()
    
    # Exact match first
    for item in item_whitelist:
        if item.lower() == raw_lower:
            return item, True
    
    # Fuzzy match with difflib
    best_match = None
    best_score = 0.0
    
    for item in item_whitelist:
        score = SequenceMatcher(None, raw_lower, item.lower()).ratio()
        if score > best_score:
            best_score = score
            best_match = item
    
    if best_score >= min_score:
        return best_match, True
    
    return raw_name, False


def benchmark_correction_methods():
    """Run comprehensive benchmark comparing RapidFuzz vs difflib."""
    
    print("=" * 80)
    print("🔬 Performance Benchmark: RapidFuzz vs difflib")
    print("=" * 80)
    print()
    
    # Load item whitelist
    print("📚 Loading item whitelist...")
    item_whitelist = get_all_item_names()
    print(f"   Loaded {len(item_whitelist)} items")
    print()
    
    # Test cases: realistic OCR errors
    test_cases = [
        # Easy cases (exact matches)
        "Black Stone (Weapon)",
        "Lion's Blood Elixir",
        "Pure Copper Crystal",
        
        # OCR errors (typos, missing characters)
        "Black Stone Weapon",  # Missing parentheses
        "Lions Blood Elixir",  # Missing apostrophe
        "Pure Copper Crysta",  # Missing 'l'
        "Bl4ck Stone (We4pon)",  # OCR digit confusion
        "Lion s Blood Elixir",  # Extra space
        "Pure C0pper Crystal",  # 0 instead of o
        
        # Hard cases (multiple errors)
        "Bl ck St0ne Weapn",  # Multiple missing chars + digit
        "L10ns Blo0d El1x1r",  # Multiple OCR errors
        "Pur Copr Cryst",  # Many missing chars
        
        # Edge cases
        "Black",  # Partial name
        "Crystal",  # Generic term
        "Stone",  # Very common word
        "",  # Empty string
    ]
    
    print(f"🧪 Test cases: {len(test_cases)}")
    print()
    
    # Warmup (JIT compilation, cache initialization)
    print("🔥 Warmup runs...")
    for _ in range(10):
        correct_item_name("Black Stone (Weapon)")
        correct_item_name_difflib("Black Stone (Weapon)", item_whitelist)
    print()
    
    # Benchmark RapidFuzz
    print("⚡ Benchmarking RapidFuzz (current implementation)...")
    start_time = time.perf_counter()
    rapidfuzz_results = []
    
    for test_case in test_cases:
        corrected, is_valid = correct_item_name(test_case)
        rapidfuzz_results.append((test_case, corrected, is_valid))
    
    rapidfuzz_time = time.perf_counter() - start_time
    print(f"   Time: {rapidfuzz_time:.4f}s")
    print(f"   Avg per item: {rapidfuzz_time / len(test_cases) * 1000:.2f}ms")
    print()
    
    # Benchmark difflib
    print("🐢 Benchmarking difflib (legacy implementation)...")
    start_time = time.perf_counter()
    difflib_results = []
    
    for test_case in test_cases:
        corrected, is_valid = correct_item_name_difflib(test_case, item_whitelist)
        difflib_results.append((test_case, corrected, is_valid))
    
    difflib_time = time.perf_counter() - start_time
    print(f"   Time: {difflib_time:.4f}s")
    print(f"   Avg per item: {difflib_time / len(test_cases) * 1000:.2f}ms")
    print()
    
    # Results comparison
    print("=" * 80)
    print("📊 RESULTS")
    print("=" * 80)
    print()
    
    speedup = difflib_time / rapidfuzz_time if rapidfuzz_time > 0 else 0
    print(f"🚀 Speedup: {speedup:.1f}x faster with RapidFuzz")
    print(f"⚡ Time saved: {(difflib_time - rapidfuzz_time):.4f}s ({((difflib_time - rapidfuzz_time) / difflib_time * 100):.1f}%)")
    print()
    
    # Quality comparison
    print("🎯 Accuracy Comparison:")
    print()
    print(f"{'Input':<25} {'RapidFuzz':<25} {'difflib':<25} {'Match?':<10}")
    print("-" * 85)
    
    matches = 0
    differences = 0
    
    for i, test_case in enumerate(test_cases):
        rf_corrected, rf_valid = rapidfuzz_results[i][1], rapidfuzz_results[i][2]
        dl_corrected, dl_valid = difflib_results[i][1], difflib_results[i][2]
        
        match = "✅" if (rf_corrected == dl_corrected and rf_valid == dl_valid) else "❌"
        
        if match == "✅":
            matches += 1
        else:
            differences += 1
            
        # Truncate long names for display
        test_display = test_case[:24] if test_case else "(empty)"
        rf_display = rf_corrected[:24] if rf_corrected else "-"
        dl_display = dl_corrected[:24] if dl_corrected else "-"
        
        print(f"{test_display:<25} {rf_display:<25} {dl_display:<25} {match:<10}")
    
    print()
    print(f"✅ Matching results: {matches}/{len(test_cases)} ({matches/len(test_cases)*100:.1f}%)")
    print(f"❌ Different results: {differences}/{len(test_cases)} ({differences/len(test_cases)*100:.1f}%)")
    print()
    
    # Summary
    print("=" * 80)
    print("📝 SUMMARY")
    print("=" * 80)
    print()
    print(f"RapidFuzz is {speedup:.1f}x faster than difflib")
    print(f"Average per-item correction time:")
    print(f"  - RapidFuzz: {rapidfuzz_time / len(test_cases) * 1000:.2f}ms")
    print(f"  - difflib:   {difflib_time / len(test_cases) * 1000:.2f}ms")
    print()
    
    if speedup >= 10:
        print("✅ EXCELLENT: >10x speedup achieved!")
    elif speedup >= 5:
        print("✅ GOOD: 5-10x speedup achieved")
    elif speedup >= 2:
        print("⚠️  OK: 2-5x speedup (acceptable)")
    else:
        print("❌ POOR: <2x speedup (investigate)")
    
    print()
    print("💡 Recommendation: Continue using RapidFuzz (current implementation)")
    print()
    
    # Extrapolate performance for real-world usage
    print("=" * 80)
    print("🌍 REAL-WORLD IMPACT")
    print("=" * 80)
    print()
    
    # Assume 1000 item corrections per hour (conservative estimate)
    corrections_per_hour = 1000
    
    rf_time_per_hour = (rapidfuzz_time / len(test_cases)) * corrections_per_hour
    dl_time_per_hour = (difflib_time / len(test_cases)) * corrections_per_hour
    time_saved_per_hour = dl_time_per_hour - rf_time_per_hour
    
    print(f"Assuming {corrections_per_hour} item corrections per hour:")
    print(f"  - RapidFuzz: {rf_time_per_hour:.2f}s/hour")
    print(f"  - difflib:   {dl_time_per_hour:.2f}s/hour")
    print(f"  - Time saved: {time_saved_per_hour:.2f}s/hour ({time_saved_per_hour/60:.1f} minutes/hour)")
    print()
    
    print("=" * 80)


if __name__ == "__main__":
    try:
        benchmark_correction_methods()
    except KeyboardInterrupt:
        print("\n\n⚠️  Benchmark interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
