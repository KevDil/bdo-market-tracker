# ONNX/TensorRT Optimization Plan - EasyOCR Performance Boost

## 🎯 Ziel

**EasyOCR 2-3x schneller machen** durch Model-Optimization mit ONNX Runtime und TensorRT.

**Aktuell:** 334ms Mean (Balance/Item ~350ms, Warehouse ~150ms)  
**Ziel:** <150ms Mean (Balance/Item ~150-200ms, Warehouse ~50-80ms)  
**Speedup:** 2-3x faster ✨

---

## 📚 Grundlagen: Was ist ONNX & TensorRT?

### ONNX (Open Neural Network Exchange)
- **Standardformat** für neuronale Netze (model interchange format)
- **Plattform-unabhängig** - funktioniert mit PyTorch, TensorFlow, etc.
- **Optimiert** - Graph-Optimierungen (Fusion, Constant Folding, etc.)

### ONNX Runtime
- **Inference Engine** für ONNX-Modelle
- **Execution Providers**: CPU, CUDA, TensorRT, DirectML
- **Schneller als PyTorch** - spezialisiert auf Inference (kein Training)

### TensorRT (NVIDIA)
- **GPU-Inference-Engine** - optimiert für NVIDIA GPUs
- **Layer Fusion** - kombiniert Operationen für bessere GPU-Auslastung
- **Precision Calibration** - INT8/FP16 für mehr Speed
- **Kernel Auto-Tuning** - wählt beste Implementation pro GPU

### Warum schneller?

```
PyTorch (aktuell):
  Model → Python → PyTorch → CUDA → GPU
  - Python-Overhead
  - Generischer Code (für Training + Inference)
  - Keine hardware-spezifische Optimierung

ONNX Runtime + TensorRT:
  Model → ONNX Runtime → TensorRT → GPU
  - Kein Python-Overhead (C++ Engine)
  - Inference-only (kein Training-Code)
  - GPU-spezifische Optimierungen (RTX 4070 SUPER)
  - Layer Fusion (weniger Kernel Calls)
  - Mixed Precision (FP16 statt FP32)
```

**Result:** 2-3x Speedup für Inference! 🚀

---

## 🏗️ Architektur: EasyOCR Internals

### Aktueller EasyOCR-Stack:

```
EasyOCR Reader
├── Detection Model (CRAFT)  ← Text-Detection (findet Text-Regionen)
│   └── PyTorch Model (ResNet-based)
│   └── Input: Image (H×W×3)
│   └── Output: Text Regions (Boxes)
│
└── Recognition Model (CRNN) ← Text-Recognition (liest Text)
    └── PyTorch Model (CNN + LSTM + CTC)
    └── Input: Cropped Text Region
    └── Output: String + Confidence
```

### Was wir optimieren:

1. **Detection Model** (CRAFT) - ~60-70% der Zeit
2. **Recognition Model** (CRNN) - ~30-40% der Zeit

**Beide können zu ONNX konvertiert werden!**

---

## 📋 Implementation Plan (4 Phasen)

### **Phase 1: Export zu ONNX** (Einmalig)

#### Schritt 1.1: EasyOCR-Modelle extrahieren
```python
import easyocr
reader = easyocr.Reader(['en'], gpu=True)

# Modelle befinden sich in:
# C:\Users\kdill\.EasyOCR\model\
# - craft_mlt_25k.pth (Detection)
# - english_g2.pth (Recognition)

detector = reader.detector  # CRAFT Model
recognizer = reader.recognizer  # CRNN Model
```

#### Schritt 1.2: Detection Model → ONNX
```python
import torch

# Dummy Input (für Tracing)
dummy_input = torch.randn(1, 3, 640, 640).cuda()  # BxCxHxW

# Export
torch.onnx.export(
    detector,
    dummy_input,
    "craft_detection.onnx",
    input_names=['image'],
    output_names=['score_map', 'link_map'],
    dynamic_axes={
        'image': {0: 'batch', 2: 'height', 3: 'width'},
        'score_map': {0: 'batch', 2: 'height', 3: 'width'},
        'link_map': {0: 'batch', 2: 'height', 3: 'width'}
    },
    opset_version=17
)
```

#### Schritt 1.3: Recognition Model → ONNX
```python
# Recognition input: cropped text region
dummy_text_input = torch.randn(1, 1, 64, 256).cuda()  # BxCxHxW

torch.onnx.export(
    recognizer,
    dummy_text_input,
    "crnn_recognition.onnx",
    input_names=['text_image'],
    output_names=['logits'],
    dynamic_axes={
        'text_image': {0: 'batch', 3: 'width'},
        'logits': {0: 'batch', 1: 'sequence'}
    },
    opset_version=17
)
```

**Output:**
- `craft_detection.onnx` (~70 MB)
- `crnn_recognition.onnx` (~40 MB)

---

### **Phase 2: ONNX Runtime Integration** (Python Wrapper)

#### Schritt 2.1: ONNX Runtime installieren
```powershell
pip install onnxruntime-gpu  # Mit CUDA-Support
# oder
pip install onnxruntime  # CPU-only (für Tests)
```

#### Schritt 2.2: Custom OCR Engine erstellen
```python
# ocr_engines_onnx.py

import onnxruntime as ort
import numpy as np
import cv2

class ONNXEasyOCR:
    def __init__(self, use_gpu=True):
        # Session Options
        sess_options = ort.SessionOptions()
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        
        # Execution Provider
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider'] if use_gpu else ['CPUExecutionProvider']
        
        # Load Models
        self.detector = ort.InferenceSession(
            "models/craft_detection.onnx",
            sess_options,
            providers=providers
        )
        
        self.recognizer = ort.InferenceSession(
            "models/crnn_recognition.onnx",
            sess_options,
            providers=providers
        )
        
        print(f"✅ ONNX Models loaded on: {self.detector.get_providers()[0]}")
    
    def detect(self, image: np.ndarray):
        """Run Detection Model"""
        # Preprocess
        img = cv2.resize(image, (640, 640))
        img = img.transpose(2, 0, 1).astype(np.float32) / 255.0
        img = np.expand_dims(img, axis=0)  # Add batch dimension
        
        # Inference
        inputs = {self.detector.get_inputs()[0].name: img}
        outputs = self.detector.run(None, inputs)
        
        score_map, link_map = outputs
        
        # Postprocess (find text boxes)
        boxes = self._find_boxes(score_map, link_map)
        return boxes
    
    def recognize(self, text_region: np.ndarray):
        """Run Recognition Model"""
        # Preprocess (resize to fixed height, variable width)
        h, w = 64, 256
        img = cv2.resize(text_region, (w, h))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        img = img.astype(np.float32) / 255.0
        img = np.expand_dims(img, axis=(0, 1))  # Add batch + channel
        
        # Inference
        inputs = {self.recognizer.get_inputs()[0].name: img}
        outputs = self.recognizer.run(None, inputs)
        
        logits = outputs[0]
        
        # Decode (CTC decoder)
        text = self._decode_ctc(logits)
        return text
    
    def readtext(self, image: np.ndarray):
        """Main API (compatible with EasyOCR)"""
        # 1. Detect text regions
        boxes = self.detect(image)
        
        # 2. Recognize each region
        results = []
        for box in boxes:
            # Crop region
            text_region = self._crop_box(image, box)
            
            # Recognize
            text = self.recognize(text_region)
            confidence = 0.9  # TODO: implement confidence from logits
            
            results.append((box, text, confidence))
        
        return results
```

#### Schritt 2.3: Integration in `utils.py`
```python
# utils.py

from ocr_engines_onnx import ONNXEasyOCR

# Global Instance
_onnx_reader = None

def init_onnx_ocr(use_gpu=True):
    global _onnx_reader
    if _onnx_reader is None:
        _onnx_reader = ONNXEasyOCR(use_gpu=use_gpu)
    return _onnx_reader

def perform_ocr_onnx(img, roi_type='auto'):
    """ONNX-Optimized OCR"""
    reader = init_onnx_ocr(use_gpu=True)
    
    start = time.perf_counter()
    results = reader.readtext(img)
    elapsed_ms = (time.perf_counter() - start) * 1000
    
    # Extract text
    text = '\n'.join([result[1] for result in results])
    
    return text, elapsed_ms
```

---

### **Phase 3: TensorRT Optimization** (Optional, für max. Speed)

#### Schritt 3.1: TensorRT Execution Provider
```python
# ONNX Runtime mit TensorRT Backend
providers = [
    ('TensorRTExecutionProvider', {
        'device_id': 0,
        'trt_max_workspace_size': 2 * 1024 * 1024 * 1024,  # 2 GB
        'trt_fp16_enable': True,  # FP16 Precision (2x faster)
        'trt_engine_cache_enable': True,  # Cache optimized engine
        'trt_engine_cache_path': './tensorrt_cache/'
    }),
    'CUDAExecutionProvider',
    'CPUExecutionProvider'
]

session = ort.InferenceSession("craft_detection.onnx", providers=providers)
```

#### Was passiert?
1. **First Run:** TensorRT baut optimierte Engine (dauert ~1 Min)
   - Layer Fusion (weniger GPU Kernel Calls)
   - Precision Calibration (FP16 statt FP32)
   - Hardware-spezifische Optimierung (RTX 4070 SUPER)

2. **Cached:** Engine wird gespeichert (`./tensorrt_cache/`)

3. **Subsequent Runs:** Nutzt cached Engine → **2-3x schneller!**

---

### **Phase 4: Benchmarking & Validation** (Kritisch!)

#### Schritt 4.1: Performance-Vergleich
```python
# scripts/utils/benchmark_onnx.py

import time
from utils import perform_ocr, perform_ocr_onnx

# Load test images
test_images = {
    'balance': cv2.imread('debug/debug_balance_buy_item_proc.png'),
    'warehouse': cv2.imread('debug/debug_warehouse_buy_item_proc.png'),
    'item_name': cv2.imread('debug/debug_item_name_buy_item_proc.png'),
}

results = {'PyTorch': {}, 'ONNX': {}, 'ONNX+TensorRT': {}}

# Benchmark PyTorch (baseline)
for name, img in test_images.items():
    times = []
    for _ in range(10):
        text, elapsed = perform_ocr(img)
        times.append(elapsed)
    results['PyTorch'][name] = np.mean(times)

# Benchmark ONNX
for name, img in test_images.items():
    times = []
    for _ in range(10):
        text, elapsed = perform_ocr_onnx(img)
        times.append(elapsed)
    results['ONNX'][name] = np.mean(times)

# Print Results
print("Performance Comparison:")
for engine, data in results.items():
    print(f"\n{engine}:")
    for roi, ms in data.items():
        speedup = results['PyTorch'][roi] / ms if engine != 'PyTorch' else 1.0
        print(f"  {roi:15s}: {ms:6.1f}ms ({speedup:.2f}x)")
```

#### Schritt 4.2: Accuracy-Validation
```python
# CRITICAL: ONNX muss gleichen Text erkennen wie PyTorch!

def validate_accuracy():
    test_cases = [
        ('debug/balance.png', '1,234,567,890 Silver'),
        ('debug/warehouse.png', '4486'),
        ('debug/item_name.png', 'Pure Powder Reagent'),
    ]
    
    for img_path, expected in test_cases:
        img = cv2.imread(img_path)
        
        # PyTorch
        text_pytorch, _ = perform_ocr(img)
        
        # ONNX
        text_onnx, _ = perform_ocr_onnx(img)
        
        # Compare (fuzzy match)
        similarity = fuzz.ratio(text_pytorch, text_onnx)
        
        if similarity < 90:
            print(f"❌ Accuracy Regression: {img_path}")
            print(f"   PyTorch: {text_pytorch}")
            print(f"   ONNX:    {text_onnx}")
            print(f"   Similarity: {similarity}%")
            return False
    
    print("✅ All accuracy tests passed!")
    return True
```

#### Schritt 4.3: Integration Tests
```python
# Tests mit echten BDO-Screenshots
# Alle bisherigen Tests müssen weiterhin bestehen!

pytest tests/unit/test_parsing.py
pytest tests/unit/test_collect_anchor.py
pytest tests/unit/test_powder_of_darkness.py
```

---

## 📊 Erwartete Performance-Gains

### Conservative Estimate (ONNX Runtime):
```
Balance:    350ms → 200ms  (1.75x faster)
Warehouse:  150ms → 80ms   (1.88x faster)
Item Name:  350ms → 200ms  (1.75x faster)

Overall:    334ms → 180ms  (1.86x faster) ✅
```

### Optimistic Estimate (ONNX + TensorRT + FP16):
```
Balance:    350ms → 120ms  (2.92x faster)
Warehouse:  150ms → 50ms   (3.00x faster)
Item Name:  350ms → 120ms  (2.92x faster)

Overall:    334ms → 100ms  (3.34x faster) 🚀
```

### Real-World Impact:
```
Detail-Window Scan (aktuell):
  Item Name: 350ms
  Balance:   350ms
  Warehouse: 150ms
  ──────────────────
  Total:     850ms per scan
  
  In 3s window: 3-4 scans possible

Detail-Window Scan (mit ONNX+TensorRT):
  Item Name: 120ms
  Balance:   120ms
  Warehouse: 50ms
  ──────────────────
  Total:     290ms per scan
  
  In 3s window: 10+ scans possible! 🎯
```

**→ Relist-Detection wird viel robuster!**

---

## ⚠️ Risiken & Mitigation

### Risk 1: Accuracy-Regression
**Problem:** ONNX könnte minimal anderen Output haben (numerische Präzision)

**Mitigation:**
- ✅ Umfangreiche Accuracy-Tests mit echten Screenshots
- ✅ Fuzzy-Match Toleranz (95%+ similarity)
- ✅ Parallel-Run: ONNX + PyTorch, compare results
- ✅ Fallback zu PyTorch bei Unsicherheit

### Risk 2: Export-Probleme
**Problem:** EasyOCR-Modelle könnten nicht ONNX-kompatibel sein

**Mitigation:**
- ✅ Teste Export mit dummy inputs
- ✅ Validiere ONNX-Modell mit `onnx.checker`
- ✅ Teste mit ONNX Runtime BEFORE TensorRT
- ✅ Dokumentiere unsupported ops

### Risk 3: TensorRT Build-Zeit
**Problem:** Erste TensorRT-Engine-Build dauert lange (~1 Min)

**Mitigation:**
- ✅ Engine-Caching aktivieren
- ✅ Pre-build während Installation/Setup
- ✅ Fallback zu CUDA Provider bei Cache-Miss

### Risk 4: Platform-Abhängigkeit
**Problem:** TensorRT ist NVIDIA-spezifisch

**Mitigation:**
- ✅ Graceful Degradation: TensorRT → CUDA → CPU
- ✅ Auto-Detection der verfügbaren Providers
- ✅ PyTorch-Fallback bleibt verfügbar

---

## 🛠️ Implementation Timeline

### Week 1: ONNX Export & Validation
- [ ] Day 1-2: Export Detection Model
- [ ] Day 3-4: Export Recognition Model
- [ ] Day 5-7: Validate ONNX Models (accuracy tests)

### Week 2: ONNX Runtime Integration
- [ ] Day 1-2: Create `ONNXEasyOCR` class
- [ ] Day 3-4: Integrate in `utils.py`
- [ ] Day 5: Benchmark vs. PyTorch
- [ ] Day 6-7: Integration tests

### Week 3: TensorRT Optimization (Optional)
- [ ] Day 1-2: TensorRT Provider setup
- [ ] Day 3-4: Engine building & caching
- [ ] Day 5: FP16 Precision tuning
- [ ] Day 6-7: Final benchmarks

### Week 4: Production Deployment
- [ ] Day 1-2: Feature flag (`USE_ONNX_OCR`)
- [ ] Day 3-4: Parallel run (ONNX + PyTorch validation)
- [ ] Day 5: Switch default to ONNX
- [ ] Day 6-7: Monitor & fine-tune

**Total:** ~3-4 Wochen bis Production-Ready

---

## 📦 Dependencies

```powershell
# Core
pip install onnx>=1.15.0
pip install onnxruntime-gpu>=1.17.0  # Mit CUDA 12.x

# Optional (für TensorRT)
# TensorRT wird automatisch von onnxruntime-gpu genutzt
# Keine separate Installation nötig!

# Development
pip install onnxsim  # ONNX Model Simplifier
pip install netron   # Model Visualizer
```

---

## 🎯 Success Criteria

### Must-Have (Minimum Viable):
- ✅ ONNX Models exportiert
- ✅ ONNX Runtime läuft auf GPU
- ✅ Accuracy >= 95% vs. PyTorch (fuzzy match)
- ✅ Speedup >= 1.5x
- ✅ Alle Tests bestehen

### Nice-to-Have (Optimal):
- ✅ TensorRT Provider funktioniert
- ✅ FP16 Precision ohne Accuracy-Loss
- ✅ Speedup >= 2.5x
- ✅ Engine-Caching funktioniert

### Show-Stopper (Abort-Kriterien):
- ❌ Accuracy < 90% (zu viele Fehler)
- ❌ Speedup < 1.2x (kein echtes Gain)
- ❌ Crashes/Instabilität
- ❌ Export schlägt fehl (unsupported ops)

---

## 🔄 Rollback Plan

Falls ONNX nicht funktioniert:

```python
# config.py
USE_ONNX_OCR = False  # Fallback zu PyTorch

# utils.py
if USE_ONNX_OCR and onnx_available():
    text = perform_ocr_onnx(img)
else:
    text = perform_ocr(img)  # PyTorch (bewährt)
```

**Kein Risiko** - PyTorch-Code bleibt erhalten! ✅

---

## 📚 Referenzen

### ONNX Export:
- https://pytorch.org/docs/stable/onnx.html
- https://github.com/onnx/tutorials

### ONNX Runtime:
- https://onnxruntime.ai/docs/
- https://onnxruntime.ai/docs/execution-providers/TensorRT-ExecutionProvider.html

### TensorRT:
- https://developer.nvidia.com/tensorrt
- https://github.com/NVIDIA/TensorRT

### EasyOCR Internals:
- https://github.com/JaidedAI/EasyOCR
- CRAFT Paper: https://arxiv.org/abs/1904.01941
- CRNN Paper: https://arxiv.org/abs/1507.05717

---

## 💡 Bonus: Alternative Optimierungen

Falls ONNX zu komplex ist:

### Option 3A: Model Distillation
- Trainiere kleineres Model (Student) das großes Model (Teacher) nachahmt
- 50% weniger Parameter → ~2x schneller
- **Aber:** Braucht Training-Data und Zeit

### Option 3B: Quantization (INT8)
- Konvertiere FP32 Weights zu INT8 → 4x kleinere Modelle
- Inference ~2-3x schneller
- **Aber:** Kann Accuracy reduzieren

### Option 3C: Batch Processing
- Statt 1 ROI pro Call, verarbeite mehrere ROIs gleichzeitig
- GPU-Auslastung steigt → bis zu 2x schneller
- **Aber:** Erhöht Latenz für ersten ROI

---

## 🎓 Learning Goals

Nach dieser Optimization verstehst du:

1. **ONNX Format** - Standard für ML-Models
2. **Inference Optimization** - Unterschied Training vs. Inference
3. **TensorRT** - GPU-specific Optimizations
4. **Mixed Precision** - FP16 vs. FP32 Trade-offs
5. **Model Export** - PyTorch → ONNX Workflow
6. **Performance Engineering** - Measuring, Profiling, Optimizing

**→ Transferable Skills für alle ML-Projekte!** 🚀

---

## ❓ FAQ

### Q: Warum nicht einfach ein schnelleres Modell verwenden?
**A:** EasyOCR nutzt bereits state-of-the-art Models (CRAFT + CRNN). Das Problem ist nicht das Model, sondern die Inference-Engine (PyTorch ist generisch, ONNX/TensorRT sind spezialisiert).

### Q: Funktioniert das auch auf AMD-GPUs?
**A:** Teilweise. ONNX Runtime unterstützt DirectML (AMD/Intel), aber TensorRT ist NVIDIA-only. Auf AMD wäre Speedup ~1.5-2x statt 2-3x.

### Q: Muss ich die Models neu trainieren?
**A:** NEIN! Wir nutzen die vortrainierten EasyOCR-Models, exportieren sie nur zu ONNX. Keine Training-Data oder GPU-Zeit nötig.

### Q: Was wenn Export fehlschlägt?
**A:** Dann bleiben wir bei PyTorch (funktioniert ja bereits). Kein Risiko!

### Q: Kann ich beide Engines parallel nutzen?
**A:** JA! Feature-Flag `USE_ONNX_OCR` + Fallback zu PyTorch. Wir können A/B-Testing machen.

---

## 🚀 Next Steps

Bereit zu starten? Hier ist der erste Schritt:

```powershell
# 1. Install Dependencies
pip install onnx onnxruntime-gpu

# 2. Create Export Script
python scripts/utils/export_easyocr_to_onnx.py

# 3. Test ONNX Models
python scripts/utils/test_onnx_models.py

# 4. Benchmark
python scripts/utils/benchmark_onnx.py
```

**Soll ich mit Phase 1 (ONNX Export) anfangen?** 🎯
