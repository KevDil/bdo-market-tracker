# Performance-Analyse & Implementierungsstand
**Datum**: Oktober 2025  
**Analyst**: GitHub Copilot  
**Basis**: performance_plan.md Revision

---

## Executive Summary

Der Performance-Plan wurde umfassend analysiert und mit dem aktuellen Implementierungsstand abgeglichen. **Haupterkenntnis**: Die Infrastruktur ist zu 75% implementiert, aber die **kritischste Optimierung fehlt noch** – die Anpassung von EasyOCR's `canvas_size` Parameter.

### Schnelle Wins verfügbar:
1. ✅ **Phase 0 komplett**: Benchmark-Tool, Metriken, ROI-Visualisierung
2. 🟡 **Phase 1 zu 75%**: Infrastructure da, aber canvas_size nicht optimiert
3. 🔴 **canvas_size Optimierung**: -30% OCR-Zeit erwartet (1200ms → 840ms)

---

## Detaillierte Befunde

### 1. Was bereits läuft ✅

#### Caching & Performance-Grundlagen
- **Preprocess-Cache**: `blake2s` Hash-basiert, Cache-Hits = 0ms Preprocessing
- **OCR-Cache**: TTL 5s (war 2s), Size 20 (war 10)
- **Debug-Default**: OFF (war teilweise ON) → -50ms I/O

#### ROI-Management
- **Drei separate ROIs** implementiert:
  - `detect_log_roi()`: Transaktions-Log (0-32% Höhe)
  - `detect_window_label_roi()`: Fenstertitel (33-65%)
  - `detect_metrics_roi()`: UI-Metriken (33-97%)
- **Adaptive OCR-Strategie**: Label zuerst → Log-Skip bei Detailfenstern

#### Monitoring & Benchmarking
- **Benchmark-Script**: `scripts/perf/benchmark_scan.py`
  - Warmup, GPU-Forcing, Static-Image-Support
  - GPU-Telemetrie (CUDA memory)
  - Dry-run Mode
- **Metriken im Code**: `tracker._process_image()` sammelt alle Timings

### 2. Kritische Diskrepanzen ⚠️

#### A) ROI-Trim Konflikt
**AGENTS.md sagt**:
```
ROI trim: keep y-range at top 0–75% of the capture
```

**Code tut** (`utils.py:214`):
```python
y_end = int(h * 0.32)  # Nur 32%!
```

**Status**: 🟡 **KLÄRUNGSBEDARF**
- Entweder AGENTS.md ist veraltet ODER Code ist falsch
- Benötigt Vergleich mit `dev-screenshots/regions.png`
- **Beide Dokumente müssen synchron sein!**

#### B) EasyOCR canvas_size
**Aktuell**:
```python
canvas_size = 2240  # utils.py:501
```

**Problem**:
- Log-ROI ist nur ~700×200px
- EasyOCR skaliert hoch auf 2240×N
- 3× Up-Scaling erzeugt unnötige GPU-Last

**Lösung**:
```python
canvas_size = 1600  # -28% Pixel
```

**Erwarteter Impact**: -300-400ms (30% Reduktion)

#### C) Adaptive CLAHE ignoriert fast_mode
**Aktuell** (`tracker.py:285`):
```python
proc = preprocess(img, adaptive=True, denoise=False, fast_mode=use_fast_preprocess)
```

**Problem**: `adaptive=True` ist hardcoded, `fast_mode` wird nur für Sharpening genutzt

**Vorschlag**:
```python
use_adaptive = not use_fast_preprocess
proc = preprocess(img, adaptive=use_adaptive, denoise=False, fast_mode=use_fast_preprocess)
```

**Erwarteter Impact**: -40ms bei GPU

### 3. Benchmark-Baseline (Januar 2025)

**Hardware**: RTX 4070 SUPER  
**Modus**: GPU, Debug=OFF

```
┌──────────────┬──────────┬────────┐
│ Phase        │ Zeit     │ Anteil │
├──────────────┼──────────┼────────┤
│ Capture      │  ~12 ms  │   1%   │
│ Preprocess   │  ~1.6 ms │   0%   │
│ OCR          │ ~1200 ms │  95%   │ ← FLASCHENHALS
│ Postprocess  │   ~0 ms  │   0%   │
├──────────────┼──────────┼────────┤
│ TOTAL        │ ~1214 ms │ 100%   │
└──────────────┴──────────┴────────┘

Cache-Hit-Rate: 0% (bei wechselnden Frames)
CUDA Memory:    ~200 MB
```

**Flaschenhals-Diagnose**:
- OCR dominiert mit 95% der Gesamtzeit
- GPU ist nicht der Limiter (nur 200 MB VRAM)
- EasyOCR's interne Skalierung ist das Problem

---

## Action Items (Priorisiert)

### 🔴 Kritisch (Diese Woche)

#### 1. canvas_size Optimierung
**Aufwand**: 1 Stunde  
**Erwartung**: -300ms OCR-Zeit  
**Risiko**: Niedrig

**Implementierung**:
```python
# In utils.py:501
if easyocr_uses_gpu():
    canvas_size = 1600       # Down from 2240
    contrast_ths = 0.32      # Down from 0.35
    text_threshold = 0.70    # Down from 0.72
```

**Validierung**:
```bash
# Baseline
python scripts/perf/benchmark_scan.py --runs 20 --use-gpu > before.txt

# Apply changes
# Edit utils.py

# Test
python scripts/perf/benchmark_scan.py --runs 20 --use-gpu > after.txt
python scripts/run_all_tests.py  # MUSS passieren!

# Vergleich
diff before.txt after.txt
```

#### 2. ROI-Trim Dokumentation
**Aufwand**: 30 Minuten  
**Ziel**: AGENTS.md ↔ Code Sync

**Schritte**:
1. Öffne `dev-screenshots/regions.png`
2. Messe roter Log-ROI Bereich
3. Entscheide:
   - Falls Log = 0-32%: Update AGENTS.md
   - Falls Log = 0-75%: Update Code + Tests
4. Dokumentiere Entscheidung in beiden Dateien

#### 3. Baseline-Dokumentation
**Aufwand**: 1 Stunde  
**Ziel**: Reproduzierbare Referenz

**Erstelle**:
- `docs/perf/scan_benchmarks_baseline.md`
- Aktuelle Messungen
- Grafiken/Tabellen

### 🟡 Wichtig (Diese/Nächste Woche)

#### 4. Adaptive CLAHE
**Aufwand**: 2 Stunden  
**Erwartung**: -40ms  
**Risiko**: Mittel (OCR-Qualität)

```python
# tracker.py:285
use_adaptive = not use_fast_preprocess
proc = preprocess(img, adaptive=use_adaptive, denoise=False, fast_mode=use_fast_preprocess)
```

**Validierung**: A/B-Test mit OCR-Qualität

#### 5. GPU-Device Logging
**Aufwand**: 1 Stunde  
**Ziel**: Transparenz für User

Zeige in GUI:
- Welches EasyOCR-Device aktiv ist
- GPU Memory Usage (optional)

### 🔵 Phase 2 (Nächste 2-4 Wochen)

6. **Async Pipeline** reaktivieren
7. **ROI-Diffing** implementieren
8. **Alternative OCR-Engines** evaluieren (PaddleOCR, RapidOCR)

---

## Erwartete Verbesserungen

### Phase 1 (canvas_size + CLAHE)
```
GPU:  1200ms → 840ms → 800ms ✅ (Ziel erreicht)
CPU:  3000ms → 2400ms → 2300ms ⚠️ (Ziel 1800ms verfehlt)
```

### Phase 2 (Async + Diffing + Alt-OCR)
```
GPU:  800ms → 650ms → 550ms → 500ms ✅
CPU:  2300ms → 2000ms → 1600ms → 1100ms ✅
```

---

## Risikobewertung

| Risiko | Wahrsch. | Impact | Mitigation |
|--------|----------|--------|------------|
| OCR-Qualität leidet | Mittel | Hoch | Testsuite als Gate, Rollback |
| GPU-Memory Overflow | Niedrig | Mittel | 2048 MB Limit (bereits da) |
| Async-Queue Stau | Mittel | Mittel | Maxsize=1, Drop-Strategie |
| ROI bricht Tests | Niedrig | Hoch | Umfangreiche Smoke-Tests |

---

## Fazit

**Status Quo**: 
- ✅ Infrastruktur ist sehr gut (Caching, ROI-Split, Benchmarking)
- 🔴 Kritische Optimierung fehlt (canvas_size)
- 🟡 Dokumentations-Gaps (ROI-Trim, Guidelines-Sync)

**Quick Win verfügbar**:
- 1 Stunde Arbeit → -30% OCR-Zeit
- Niedriges Risiko
- Hoher Impact

**Empfehlung**: 
Priorisiere `canvas_size` Optimierung JETZT, bevor Phase 2 begonnen wird. Die 30% Verbesserung ist low-hanging fruit.

**Nächster Review**: Nach canvas_size Änderung neue Baseline erstellen
