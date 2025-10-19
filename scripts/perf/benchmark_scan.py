#!/usr/bin/env python3
"""
Benchmark the MarketTracker scan pipeline.

This script measures capture, preprocessing, OCR, and parsing times over multiple
runs. It supports warmup iterations, optional static image input, and GPU telemetry.

Examples:
    python scripts/perf/benchmark_scan.py --runs 20 --warmup 5
    python scripts/perf/benchmark_scan.py --image dev-screenshots/debug_orig.png --dry-run
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import cv2
except ImportError as exc:  # pragma: no cover - cv2 is a runtime dependency
    print("OpenCV (cv2) is required for the benchmark script:", exc, file=sys.stderr)
    sys.exit(1)

# Ensure repository root is on sys.path so the tracker package can be imported
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from tracker import MarketTracker  # noqa: E402
from config import set_use_gpu, set_debug_mode, get_use_gpu  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure MarketTracker scan performance.")
    parser.add_argument(
        "--runs",
        type=int,
        default=20,
        help="Number of measured scans (default: 20)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=3,
        help="Warmup scans to discard from stats (default: 3)",
    )
    parser.add_argument(
        "--use-gpu",
        dest="use_gpu",
        action="store_true",
        help="Force GPU mode for the benchmark (overrides persisted setting).",
    )
    parser.add_argument(
        "--use-cpu",
        dest="use_gpu",
        action="store_false",
        help="Force CPU mode for the benchmark (overrides persisted setting).",
    )
    parser.add_argument(
        "--image",
        type=Path,
        help="Optional path to a screenshot that replaces live capture.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        default=True,
        help="Skip downstream parsing/DB writes (default: enabled).",
    )
    parser.add_argument(
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Enable full processing, including DB updates.",
    )
    parser.add_argument(
        "--telemetry",
        action="store_true",
        help="Record optional torch CUDA telemetry (requires torch + GPU).",
    )
    parser.set_defaults(use_gpu=get_use_gpu(True))
    return parser.parse_args()


def load_image(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Failed to load image: {path}")
    return img


def maybe_patch_for_dry_run(tracker: MarketTracker) -> None:
    """Disable downstream processing if dry-run mode is requested."""
    tracker._original_process_ocr_text = tracker.process_ocr_text  # type: ignore[attr-defined]

    def _noop_process_ocr_text(_text: str) -> None:
        return None

    tracker.process_ocr_text = _noop_process_ocr_text  # type: ignore[assignment]


def restore_process_ocr_text(tracker: MarketTracker) -> None:
    original = getattr(tracker, "_original_process_ocr_text", None)
    if original is not None:
        tracker.process_ocr_text = original  # type: ignore[assignment]
        delattr(tracker, "_original_process_ocr_text")


def measure_scan(
    tracker: MarketTracker,
    *,
    static_image: Optional[np.ndarray],
    telemetry: bool,
) -> Dict[str, Any]:
    metrics: Dict[str, Any] = {}

    if static_image is not None:
        metrics["capture_ms"] = 0.0
        img = static_image.copy()
    else:
        capture_start = time.perf_counter()
        img = tracker._capture_frame()
        metrics["capture_ms"] = (time.perf_counter() - capture_start) * 1000

    if img is None:
        metrics["error"] = "capture_failed"
        return metrics

    tracker._process_image(img, context="perf", allow_debug=False, metrics=metrics)

    if telemetry:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.synchronize()
                metrics["cuda_memory_mb"] = torch.cuda.memory_allocated(0) / (1024 * 1024)
                metrics["cuda_max_memory_mb"] = torch.cuda.max_memory_allocated(0) / (1024 * 1024)
        except Exception as exc:  # pragma: no cover - optional diagnostics
            metrics.setdefault("telemetry_warning", str(exc))

    return metrics


def summarize(label: str, values: List[float]) -> str:
    if not values:
        return f"{label}: no data"
    sorted_vals = sorted(values)
    idx = max(0, min(len(sorted_vals) - 1, int(round(0.95 * len(sorted_vals) - 1))))
    p95 = sorted_vals[idx]
    return (
        f"{label}: mean={statistics.mean(values):.1f}ms "
        f"median={statistics.median(values):.1f}ms "
        f"p95={p95:.1f}ms "
        f"min={min(values):.1f}ms max={max(values):.1f}ms"
    )


def main() -> None:
    args = parse_args()

    # Disable debug logging for clean measurements
    set_debug_mode(False)
    set_use_gpu(args.use_gpu)

    tracker = MarketTracker(debug=False)
    tracker.running = True

    static_image = load_image(args.image) if args.image else None

    if args.dry_run:
        maybe_patch_for_dry_run(tracker)

    warmup = max(0, args.warmup)
    runs = max(1, args.runs)
    total_iterations = warmup + runs

    print(f"Benchmark configuration: runs={runs}, warmup={warmup}, gpu={args.use_gpu}, dry_run={args.dry_run}")
    if static_image is not None:
        print(f"Using static image: {args.image}")
    else:
        print("Using live capture (ensure Black Desert window is focused).")

    measured: List[Dict[str, Any]] = []
    for idx in range(total_iterations):
        metrics = measure_scan(tracker, static_image=static_image, telemetry=args.telemetry)

        if metrics.get("error"):
            print(f"[{idx+1}/{total_iterations}] ERROR: {metrics['error']}")
        else:
            msg = (
                f"[{idx+1}/{total_iterations}] "
                f"capture={metrics.get('capture_ms', 0):.1f}ms "
                f"preprocess={metrics.get('preprocess_ms', 0):.1f}ms "
                f"ocr={metrics.get('ocr_ms', 0):.1f}ms "
                f"postprocess={metrics.get('postprocess_ms', 0):.1f}ms "
                f"total={metrics.get('total_ms', 0):.1f}ms "
                f"cache_hit={metrics.get('ocr_cache_hit', False)}"
            )
            if args.telemetry:
                msg += f" cuda_mem={metrics.get('cuda_memory_mb', 0):.1f}MB"
            print(msg)

        if idx >= warmup and not metrics.get("error"):
            measured.append(metrics)

        # Give OCR threads a brief breather
        time.sleep(0.05)

    tracker.running = False
    restore_process_ocr_text(tracker)

    if not measured:
        print("No successful scans recorded after warmup.")
        return

    capture_times = [m.get("capture_ms", 0.0) for m in measured]
    preprocess_times = [m.get("preprocess_ms", 0.0) for m in measured]
    ocr_times = [m.get("ocr_ms", 0.0) for m in measured]
    post_times = [m.get("postprocess_ms", 0.0) for m in measured]
    total_times = [m.get("total_ms", 0.0) for m in measured]

    print("\nSummary (excluding warmup):")
    for label, values in [
        ("Capture", capture_times),
        ("Preprocess", preprocess_times),
        ("OCR", ocr_times),
        ("Postprocess", post_times),
        ("Total", total_times),
    ]:
        print("  " + summarize(label, values))

    cache_hits = sum(1 for m in measured if m.get("ocr_cache_hit"))
    print(f"\nCache hit rate: {cache_hits}/{len(measured)} ({(cache_hits/len(measured))*100:.1f}%)")

    if args.telemetry:
        cuda_mem = [m.get("cuda_memory_mb", 0.0) for m in measured if m.get("cuda_memory_mb") is not None]
        if cuda_mem:
            print("  CUDA memory usage (allocated MB): "
                  f"mean={statistics.mean(cuda_mem):.1f} max={max(cuda_mem):.1f}")


if __name__ == "__main__":
    main()
