# PaddleOCR Optimization Guide - BDO Market Tracker

## 🎯 Ziel

PaddleOCR so konfigurieren, dass es **schneller als EasyOCR** (400-700ms) wird, bei gleicher oder besserer Accuracy.

## 📊 Aktuelle Situation

- **EasyOCR**: 400-700ms pro ROI (Balance/Item Name), 150-200ms (Warehouse)
- **PaddleOCR (alte Config)**: 5-6s pro Scan ❌ (zu langsam)
- **Ziel**: <400ms pro ROI ✅

## 🔬 Kritische Parameter

### 1. Recognition Batch Number
```python
rec_batch_num=1  # Single ROI → kein Batching nötig!
```
**Problem**: Default `rec_batch_num=6` ist für Multi-Image-Batches optimiert.  
**Lösung**: Bei Single-ROI-Processing ist `1` optimal (kein Batching-Overhead).

### 2. Detection Thresholds (Aggressiver = Schneller)
```python
det_db_thresh=0.5        # default: 0.3 (höher = weniger Detections)
det_db_box_thresh=0.7    # default: 0.6 (höher = strengere Filterung)
det_db_unclip_ratio=1.3  # default: 1.5 (niedriger = kleinere Text-Boxen)
```
**Effekt**: Weniger False-Positives, schnellere Detection-Phase.  
**Risiko**: Könnte schwachen Text (graue Warehouse-Zahlen) verpassen.

### 3. Angle Classification ausschalten
```python
use_angle_cls=False  # Keine Text-Rotation im BDO-UI
```
**Effekt**: Spart ~50-100ms pro Image.

### 4. Modell-Auswahl
```python
# Option 1: PP-OCRv3 mobile (Standard)
# - Balanced Speed/Accuracy
# - Gut getestet

# Option 2: PP-OCRv4 mobile (Neuestes)
# - Bessere Accuracy (SVTR_LCNet recognizer)
# - Evtl. minimal langsamer

# Option 3: Server Models
# - Beste Accuracy
# - Deutlich langsamer → NICHT für Echtzeit
```

## 🧪 Benchmark-Scripts

### 1. Umfassender Benchmark (alle Configs)
```powershell
python scripts/utils/benchmark_paddle_optimized.py
```

**Testet**:
- PP-OCRv3 vs. v4
- Mobile vs. Server Models
- Verschiedene Detection-Parameter
- Batch-Sizes
- Vergleich gegen EasyOCR Baseline

**Output**: 
- Console-Zusammenfassung
- Detaillierte Datei: `paddle_benchmark_results_YYYYMMDD_HHMMSS.txt`

### 2. Quick Test (einzelnes Bild)
```powershell
python scripts/utils/quick_paddle_test.py
python scripts/utils/quick_paddle_test.py --image debug_proc.png
```

**Testet**:
- Optimierte Config
- Fast-Detection Config
- 5 Iterationen pro Config
- Zeigt erkannten Text

## 📈 Erwartete Ergebnisse

### Optimistisch (Erfolg)
```
PP-OCRv3 Mobile (optimized): 250-350ms
→ 1.5-2x schneller als EasyOCR! ✅
→ Migration empfohlen
```

### Realistisch (Mixed)
```
PP-OCRv3 Mobile (optimized): 400-600ms
→ Ähnlich wie EasyOCR (~0.9-1.2x)
→ Keine Migration nötig
```

### Pessimistisch (Failure)
```
PP-OCRv3 Mobile: 800-1200ms
→ Immer noch 2x langsamer als EasyOCR ❌
→ Bei EasyOCR bleiben
```

## 🎛️ Optimierungs-Strategie

### Phase 1: Baseline finden
1. Run `benchmark_paddle_optimized.py`
2. Identifiziere schnellste Config
3. Vergleiche gegen EasyOCR

### Phase 2: Feintuning (falls nötig)
Falls PaddleOCR langsam ist, versuche:

**Detection optimieren**:
```python
# Noch aggressivere Thresholds
det_db_thresh=0.6
det_db_box_thresh=0.8
det_db_unclip_ratio=1.2
```

**Bildgröße reduzieren**:
```python
# In utils.py: preprocess_for_ocr()
canvas_size = 600  # statt 700 oder 800
```

**Detection komplett skippen** (ROI-Mode):
```python
# Nur Recognizer nutzen auf festen ROIs
# Requires PaddleOCR API-Zugriff auf rec_model direkt
# → Komplexer, aber schnellster Ansatz
```

### Phase 3: Integration (falls erfolgreich)
Falls PaddleOCR schneller ist:

1. **Update `config.py`**:
   ```python
   OCR_ENGINE = 'paddle'
   OCR_FALLBACK_ENABLED = True  # EasyOCR als Fallback
   ```

2. **Update `ocr_engines.py`** mit optimierten Parametern:
   ```python
   def init_paddle_ocr(use_gpu: bool = False, lang: str = 'en'):
       _paddle_reader = PaddleOCR(
           use_gpu=use_gpu,
           lang=lang,
           show_log=False,
           use_angle_cls=False,
           det_db_thresh=0.5,        # Optimiert!
           det_db_box_thresh=0.7,    # Optimiert!
           det_db_unclip_ratio=1.3,  # Optimiert!
           rec_batch_num=1,          # Optimiert!
       )
   ```

3. **Tests**:
   - Magical Shard relist
   - Unknown Seed relist
   - Pure Powder Reagent relist
   - Verify accuracy (keine Regression!)

## 🔍 Troubleshooting

### PaddleOCR ist langsam trotz Optimierung

**Mögliche Ursachen**:
1. **GPU nicht genutzt**: Check `get_use_gpu()` in config
2. **Alte PaddleOCR Version**: Upgrade zu 2.7+
   ```powershell
   pip install --upgrade paddleocr
   ```
3. **CPU-bound**: PaddleOCR braucht GPU für Speed
4. **Model-Download bei erstem Run**: Warmup-Run dauert länger

### Text wird nicht erkannt

**Mögliche Ursachen**:
1. **Thresholds zu aggressiv**: Reduziere `det_db_thresh` auf 0.3
2. **Grayscale statt RGB**: PaddleOCR braucht RGB!
3. **Preprocessing zu stark**: Reduziere CLAHE-Contrast

### ImportError: No module named 'paddleocr'

```powershell
# CPU-Version
pip install paddleocr

# GPU-Version (empfohlen!)
pip install paddlepaddle-gpu
pip install paddleocr
```

### CUDA/cuDNN Errors

**Windows GPU Setup**:
1. Install CUDA Toolkit 11.8 oder 12.0
2. Install cuDNN 8.x
3. Verify:
   ```python
   import paddle
   print(paddle.device.get_device())  # Should show GPU
   ```

## 📚 Referenzen

- PaddleOCR Docs: https://github.com/PaddlePaddle/PaddleOCR
- PP-OCRv3 Paper: https://arxiv.org/abs/2206.03001
- PP-OCRv4 Release: https://github.com/PaddlePaddle/PaddleOCR/blob/main/doc/doc_en/PP-OCRv4_introduction_en.md
- Model Zoo: https://github.com/PaddlePaddle/PaddleOCR/blob/main/doc/doc_en/models_list_en.md

## 🎯 Erfolgs-Kriterien

PaddleOCR ist dann besser als EasyOCR wenn:

1. ✅ **Schneller**: <400ms pro ROI (Balance/Item Name)
2. ✅ **Gleiche Accuracy**: Keine Relist-Detection-Fehler
3. ✅ **Stabil**: Keine Crashes/Memory-Leaks
4. ✅ **Wartbar**: Klare Konfiguration, dokumentiert

Wenn alle 4 Kriterien erfüllt → **Migration zu PaddleOCR** ✅  
Sonst → **Bei EasyOCR bleiben** ✅

---

**Viel Erfolg mit den Benchmarks! 🚀**
