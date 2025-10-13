import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time
import numpy as np
import argparse
from tracker import MarketTracker
from utils import capture_region, preprocess, extract_text, capture_and_ocr_cached, get_cache_stats, clear_cache
from config import DEFAULT_REGION

def benchmark_capture(iterations=10):
    print("\n" + "="*60)
    print("Screenshot Capture Benchmark")
    print("="*60)
    timings = []
    for i in range(iterations):
        t0 = time.time()
        img = capture_region(DEFAULT_REGION)
        t1 = time.time()
        timings.append(t1 - t0)
    arr = np.array(timings)
    print(f"Mean: {arr.mean()*1000:.1f}ms")
    return arr.mean()

def benchmark_ocr(iterations=5):
    print("\n" + "="*60)
    print("OCR Benchmark (uncached)")
    print("="*60)
    timings = []
    for i in range(iterations):
        img = capture_region(DEFAULT_REGION)
        proc = preprocess(img)
        t0 = time.time()
        text = extract_text(proc, use_roi=True, method='easyocr')
        t1 = time.time()
        timings.append(t1 - t0)
    arr = np.array(timings)
    print(f"Mean: {arr.mean()*1000:.1f}ms")
    return arr.mean()

def benchmark_cached_ocr(iterations=20):
    print("\n" + "="*60)
    print("Cached OCR Benchmark")
    print("="*60)
    clear_cache()
    timings = []
    hits = []
    for i in range(iterations):
        t0 = time.time()
        text, cached, stats = capture_and_ocr_cached(DEFAULT_REGION, method='easyocr')
        t1 = time.time()
        timings.append(t1 - t0)
        hits.append(cached)
    arr = np.array(timings)
    hit_rate = sum(hits) / len(hits) * 100
    print(f"Mean: {arr.mean()*1000:.1f}ms")
    print(f"Cache Hit Rate: {hit_rate:.1f}%")
    return arr.mean(), hit_rate

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iterations', type=int, default=10)
    args = parser.parse_args()
    
    print("\nBDO Market Tracker Performance Benchmark")
    results = {}
    results['capture'] = benchmark_capture(args.iterations)
    results['ocr'] = benchmark_ocr(min(args.iterations, 5))
    results['cached_ocr'], results['hit_rate'] = benchmark_cached_ocr(20)
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Capture: {results['capture']*1000:.1f}ms")
    print(f"OCR (uncached): {results['ocr']*1000:.1f}ms")
    print(f"OCR (cached): {results['cached_ocr']*1000:.1f}ms")
    if results['ocr'] > 0:
        speedup = results['ocr'] / results['cached_ocr']
        print(f"Cache Speedup: {speedup:.2f}x")

if __name__ == '__main__':
    main()
