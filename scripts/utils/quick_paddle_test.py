#!/usr/bin/env python3
"""
Quick PaddleOCR Test - Schneller Test mit optimalen Parametern

Usage:
    python scripts/utils/quick_paddle_test.py
    python scripts/utils/quick_paddle_test.py --image debug_proc.png
"""

import sys
import os
import time
import cv2
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from config import get_use_gpu


def test_paddle_optimized(image_path: str):
    """
    Testet PaddleOCR mit optimierten Parametern für BDO.
    """
    print("="*80)
    print("QUICK PADDLEOCR TEST - Optimized Parameters")
    print("="*80)
    
    # Load image
    if not os.path.exists(image_path):
        print(f"❌ Image not found: {image_path}")
        return
    
    img = cv2.imread(image_path)
    if img is None:
        print(f"❌ Failed to load image: {image_path}")
        return
    
    print(f"✅ Loaded image: {image_path}")
    print(f"   Size: {img.shape[1]}x{img.shape[0]} ({img.shape[2]} channels)")
    
    # Convert BGR to RGB (PaddleOCR expects RGB)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # GPU detection
    use_gpu = get_use_gpu(default=True)
    print(f"\n🖥️  GPU Mode: {use_gpu}")
    
    # Test configurations (PaddleOCR 3.x API)
    # NOTE: show_log parameter removed in 3.x
    configs = [
        {
            'name': 'PP-OCRv3 Mobile (optimized)',
            'kwargs': {
                'lang': 'en',
                'ocr_version': 'PP-OCRv3',
                'use_textline_orientation': False,  # NEW: replaces use_angle_cls
                'text_det_thresh': 0.3,  # NEW: replaces det_db_thresh
                'text_det_box_thresh': 0.5,  # NEW: replaces det_db_box_thresh
                'text_det_unclip_ratio': 1.6,  # NEW: replaces det_db_unclip_ratio
                'text_recognition_batch_size': 1,  # NEW: replaces rec_batch_num (optimal für single ROI)
            }
        },
        {
            'name': 'PP-OCRv3 Mobile (fast detection)',
            'kwargs': {
                'lang': 'en',
                'ocr_version': 'PP-OCRv3',
                'use_textline_orientation': False,
                'text_det_thresh': 0.5,  # Aggressiver threshold
                'text_det_box_thresh': 0.7,
                'text_det_unclip_ratio': 1.3,
                'text_recognition_batch_size': 1,
            }
        },
    ]
    
    try:
        from paddleocr import PaddleOCR
    except ImportError:
        print("\n❌ PaddleOCR not installed!")
        print("   Install: pip install paddleocr")
        print("   For GPU: pip install paddlepaddle-gpu")
        return
    
    # Test each config
    for i, config in enumerate(configs, 1):
        print(f"\n{'='*80}")
        print(f"Test {i}/{len(configs)}: {config['name']}")
        print(f"{'='*80}")
        
        try:
            # Initialize
            print("Initializing PaddleOCR...")
            start_init = time.perf_counter()
            reader = PaddleOCR(**config['kwargs'])
            init_time = (time.perf_counter() - start_init) * 1000
            print(f"✅ Initialization: {init_time:.0f}ms")
            
            # Warmup
            print("Warmup run...")
            _ = reader.ocr(img_rgb)  # cls parameter removed in PaddleOCR 3.x
            
            # Benchmark (5 runs)
            print("Running 5 benchmark iterations...")
            times = []
            results_text = []
            
            for j in range(5):
                start = time.perf_counter()
                result = reader.ocr(img_rgb)  # cls parameter removed
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
                
                # Extract text
                if result and result[0]:
                    texts = []
                    for line in result[0]:
                        if len(line) == 2:
                            bbox, (text, conf) = line
                            texts.append(f"{text} ({conf:.2f})")
                    
                    combined = ' | '.join(texts)
                    results_text.append(combined)
                    print(f"  Run {j+1}: {elapsed:.1f}ms - Found {len(texts)} text regions")
                else:
                    results_text.append("(no text)")
                    print(f"  Run {j+1}: {elapsed:.1f}ms - No text detected")
            
            # Statistics
            mean_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)
            
            print(f"\n📊 Statistics:")
            print(f"   Mean:   {mean_time:.1f}ms")
            print(f"   Min:    {min_time:.1f}ms")
            print(f"   Max:    {max_time:.1f}ms")
            print(f"   Range:  {max_time - min_time:.1f}ms")
            
            print(f"\n📝 Detected Text (first run):")
            if results_text[0]:
                print(f"   {results_text[0][:200]}")
            else:
                print("   (none)")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)


def main():
    parser = argparse.ArgumentParser(description='Quick PaddleOCR optimization test')
    parser.add_argument('--image', '-i', default='debug_proc.png',
                       help='Path to test image (default: debug_proc.png)')
    
    args = parser.parse_args()
    
    # Resolve path
    if not os.path.isabs(args.image):
        # Try relative to project root
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        image_path = os.path.join(project_root, args.image)
    else:
        image_path = args.image
    
    test_paddle_optimized(image_path)


if __name__ == "__main__":
    main()
