"""
Quick OCR Performance Test
Tests if V5 optimizations are active after GPU warm-up
"""
import time
import cv2
import numpy as np
from utils import ocr_image_cached

print("🔥 GPU Warm-up Test")
print("=" * 60)

# EasyOCR initializes automatically on first import

# Create test images for each ROI type
roi_configs = [
    ("label", 414, 224),     # 92k px → Target: ~56ms
    ("log", 816, 223),       # 182k px → Target: ~151ms
    ("metrics", 740, 448),   # 331k px → Target: ~186ms
]

print("\n📊 Testing OCR Performance (3 iterations each):")
print("-" * 60)

for roi_label, width, height in roi_configs:
    # Create dummy image
    img = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
    
    times = []
    for i in range(3):
        start = time.perf_counter()
        text, was_cached, _ = ocr_image_cached(
            img,
            method='auto',
            use_roi=False,  # Don't apply additional ROI, test the full image
            fast_mode=True,
            roi_label=roi_label,
        )
        elapsed = (time.perf_counter() - start) * 1000
        
        if not was_cached:
            times.append(elapsed)
            status = "✅" if elapsed < 300 else "⚠️"
            print(f"  {status} {roi_label:12s} #{i+1}: {elapsed:6.1f}ms {' [CACHED]' if was_cached else ''}")
    
    if times:
        avg = sum(times) / len(times)
        print(f"     └─ Average (non-cached): {avg:.1f}ms")
        print()

print("=" * 60)
print("✅ Test complete!")
print("\nExpected Performance (after GPU warm-up):")
print("  - label:   50-100ms")
print("  - log:     100-200ms")
print("  - metrics: 150-250ms")
print("\nFirst iteration is slower (GPU warm-up), later ones should be faster!")
