# PaddleOCR 3.x API Migration Guide

## 🔄 API-Änderungen (2.x → 3.x)

PaddleOCR hat in Version 3.x die API überarbeitet. Die Benchmark-Scripts wurden aktualisiert.

### Parameter-Mapping:

| Old API (2.x) | New API (3.x) | Notes |
|---------------|---------------|-------|
| `use_gpu=True/False` | ❌ **Entfernt** | GPU wird automatisch erkannt via `paddle.is_compiled_with_cuda()` |
| `use_angle_cls` | `use_textline_orientation` | Text-Orientierung (Rotation-Detection) |
| `det_db_thresh` | `text_det_thresh` | Detection threshold |
| `det_db_box_thresh` | `text_det_box_thresh` | Box confidence threshold |
| `det_db_unclip_ratio` | `text_det_unclip_ratio` | Text region expansion |
| `rec_batch_num` | `text_recognition_batch_size` | Recognition batch size |
| `cls=True/False` (in `.ocr()`) | ❌ **Entfernt** | Parameter wird bei Init gesetzt |
| `det_algorithm` / `rec_algorithm` | ❌ **Entfernt** | Use `ocr_version` stattdessen |

### Neue Parameter:

| Parameter | Values | Description |
|-----------|--------|-------------|
| `ocr_version` | `'PP-OCRv3'`, `'PP-OCRv4'` | Modell-Version auswählen |

## ✅ Updated Scripts

- ✅ `benchmark_paddle_optimized.py` - Aktualisiert mit neuer API
- ✅ `quick_paddle_test.py` - Aktualisiert mit neuer API
- ⚠️ `ocr_engines.py` - **NOCH NICHT aktualisiert** (nur wenn Migration erfolgt)

## 🚀 Jetzt testen:

```powershell
# Vollständiger Benchmark
python scripts/utils/benchmark_paddle_optimized.py

# Quick Test
python scripts/utils/quick_paddle_test.py
```

## 📦 Installation

```powershell
# Check Version
python -c "import paddleocr; print(paddleocr.__version__)"

# Upgrade auf 3.x (falls nötig)
pip install --upgrade paddleocr

# GPU Support (empfohlen!)
pip install paddlepaddle-gpu
```

## 🔍 GPU Detection

PaddleOCR 3.x erkennt GPU automatisch:

```python
import paddle
print(f"GPU available: {paddle.is_compiled_with_cuda()}")
print(f"Device: {paddle.get_device()}")
```

**Wichtig**: Kein `use_gpu` Parameter mehr! GPU wird automatisch genutzt wenn verfügbar.

## ⚠️ Breaking Changes

Falls alter Code existiert:

```python
# ALT (2.x) - FUNKTIONIERT NICHT MEHR
reader = PaddleOCR(
    use_gpu=True,
    det_db_thresh=0.3,
    rec_batch_num=1
)
result = reader.ocr(img, cls=False)

# NEU (3.x)
reader = PaddleOCR(
    text_det_thresh=0.3,
    text_recognition_batch_size=1
)
result = reader.ocr(img)  # cls parameter entfernt
```

## 📊 Erwartete Ergebnisse

Nach dem Update sollten alle Benchmark-Configs laufen:

```
✅ PP-OCRv3 Mobile (batch=1)
✅ PP-OCRv3 Mobile (fast-det)
✅ PP-OCRv4 Mobile
✅ PP-OCRv3 Server
```

Falls Errors:
1. Check PaddleOCR Version: `pip show paddleocr`
2. Re-install: `pip install --force-reinstall paddleocr`
3. Check GPU: `python -c "import paddle; print(paddle.is_compiled_with_cuda())"`
