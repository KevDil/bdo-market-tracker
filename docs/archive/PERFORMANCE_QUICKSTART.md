# Performance-Optimierung - Quick Start

## 🎯 Übersicht

Die Performance-Analyse zeigt **40-60% Optimierungspotential** in den Bereichen:
- OCR-Performance (größter Bottleneck)
- Caching-Strategien
- Database-Operationen
- Threading-Overhead

## 📊 Benchmark ausführen

```bash
cd c:\Users\kdill\Desktop\market_tracker
python scripts\benchmark_performance.py
```

**Ausgabe:**
```
=== OCR Performance Benchmark ===
capture             : 0.015s ± 0.002s
preprocess          : 0.120s ± 0.015s
ocr_easyocr         : 1.250s ± 0.180s
ocr_tesseract       : 0.680s ± 0.090s
total               : 2.065s ± 0.220s

=== Parsing Performance Benchmark ===
Per Entry:   8.50ms ± 1.20ms
Throughput:  117.6 entries/sec

=== Database Performance Benchmark ===
insert     : 2.50ms ± 0.80ms
select     : 0.80ms ± 0.20ms
update     : 2.20ms ± 0.60ms

=== Full Cycle Benchmark ===
Full Cycle:  2.100s ± 0.250s
Throughput:  0.48 scans/sec
```

## ⚡ Quick Wins (heute umsetzbar)

### 1. Item-Name-Cache erhöhen
**Datei:** `utils.py:320`

```python
# VORHER
@lru_cache(maxsize=1)  # Nutzlos!

# NACHHER
@lru_cache(maxsize=500)  # 50-70% schneller bei wiederholten Items
```

### 2. Memory-Leak-Fix
**Datei:** `tracker.py:30`

```python
# VORHER
self.seen_tx_signatures = set()  # Wächst unbegrenzt!

# NACHHER
from collections import deque
self.seen_tx_signatures = deque(maxlen=1000)
```

### 3. Regex-Patterns pre-kompilieren
**Datei:** `parsing.py:23`

```python
# Global definieren (außerhalb der Funktion)
_ANCHOR_PATTERN = re.compile(
    r"(...)", 
    re.IGNORECASE
)

def split_text_into_log_entries(text):
    # Verwenden: _ANCHOR_PATTERN.finditer(text)
```

## 📈 Performance-Tracking

Nach den Quick Wins erneut benchmarken:

```bash
python scripts\benchmark_performance.py > benchmark_after.txt
```

Vergleiche:
- OCR-Zeit sollte gleich bleiben (~1-2s)
- Parsing-Zeit sollte ~15% schneller sein
- Memory-Usage sollte stabil bleiben (kein Leak)

## 🚀 Nächste Schritte

Siehe detaillierte Roadmap in:
**`docs/PERFORMANCE_ANALYSIS_2025-10-12.md`**

Phase 1 (Quick Wins):
- ✅ Item-Name-Cache erhöhen
- ✅ Memory-Leak-Fix
- ✅ Regex-Pattern-Optimierung
- ⏳ Database-Indizes hinzufügen
- ⏳ Log-Rotation implementieren

Phase 2 (OCR-Optimierung):
- ⏳ Screenshot-Hash-Caching
- ⏳ Adaptive OCR-Quality
- ⏳ GPU-Acceleration testen

## 📚 Weitere Ressourcen

- **Performance-Analyse:** `docs/PERFORMANCE_ANALYSIS_2025-10-12.md`
- **Benchmark-Script:** `scripts/benchmark_performance.py`
- **Instructions:** `instructions.md` (Section "pending_features")
