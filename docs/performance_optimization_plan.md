# Performance-Optimierungsplan

## Ausgangslage
- EasyOCR wird bereits per ROI-exhaustiver Suche optimiert (`docs/archive/2025-10/utils/benchmark_per_roi_exhaustive.py`).
- Live-Pipeline (`tracker.py`, `utils.py`, `parsing.py`, `database.py`) enthält weitere konfigurierbare Stellschrauben, die bislang statisch gewählt sind.
- Ziel: Systematische Steigerung von Geschwindigkeit und Erkennungsqualität bei vertretbarem Engineering-Aufwand.

## Zielbild
- **Messbar schnellere Scans**: ≥25 % zusätzliche Reduktion der Average-Frame-Latenz gegenüber Stand 2025-10.
- **Stabile OCR-Qualität**: Keine Regression bei Transaktions-Erkennungsquote oder Datenintegrität.
- **Reproduzierbare Benchmarks**: Automatisierte Mess-Skripte für OCR-, Parsing- und Persistenzpfad.

## Phase 0 – Grundlagen & Datensätze
- **Datensatz kuratieren** (`dev-screenshots/`, `debug/`):
  - **Detail-Fenster** (buy/sell, confirm) in mindestens drei UI-Skalierungen.
  - **Overview-Fenster** mit variierender Itemliste (5–10 Items, Mixed Fonts).
  - **Problemfälle** (schwacher Kontrast, Bewegung, Popups).
- **Ground Truth erfassen**:
  - Labels für OCR-Text, ROI-Offsets, erwartete Parsing-Outputs.
  - Ablage unter `tests/fixtures/perf/`.
- **Benchmark-Harness aufsetzen**:
  - Gemeinsame Utility (`scripts/perf/run_benchmarks.py`) zum Triggern aller Teilbenchmarks.
  - Ausgabe als JSON + Markdown-Report (z. B. `docs/perf_reports/YYYY-MM-DD.md`).

## Phase 1 – EasyOCR-Parameter weiterentwickeln
- **Accuracy-Metriken ergänzen**:
  - Hamming-/Levenshtein-Distanz pro ROI, Token-Abdeckung, Confidence-Mittelwerte.
  - Kategorisierte Fehlertypen (fehlende Timestamp, Item-Name, Preis).
- **Adaptive Suche**:
  - Successive-Halving oder Bayesian Optimization (z. B. `scikit-optimize`) statt kompletter Grid-Suche.
  - Ziel: Tests pro ROI < 5 000 Kombinationen bei vergleichbarer Qualität.
- **Profiling-Integration**:
  - GPU-Timing via `torch.cuda.Event`.
  - CPU-Fallback-Pfad parallel untersuchen.
- **Deployment**:
  - Beste Konfigurationen auto-generiert in `config/easyocr_profiles.json`.
  - `utils.extract_text()` liest Profil anhand ROI-Typ.

## Phase 2 – Weitere brute-force-fähige Parameterfelder

| Bereich | Parameter | Ort | Messgröße | Brute-Force-Ansatz |
| --- | --- | --- | --- | --- |
| **Preprocessing** | `clipLimit`, `tileGridSize`, Sharpen-Kernel, `alpha/beta`, Fast-Mode-Schwellwerte | `utils.preprocess()` | OCR-Zeit, Genauigkeit | Latin-Hypercube Sampling + lokale Grid-Verfeinerung |
| **ROI-Detektion** | Multiplikatoren für `detect_*_roi` (Start/Ende), Metrics-ROI-Höhe | `utils.py` | OCR-Trefferquote, Skip-Rate | Exhaustives Raster über ±5 % Offsets, bewertet mit Log-Verlust |
| **ROI-Signatur** | `threshold_pct`, Skip-Force-Threshold, Cache-TTL | `utils.compare_roi_signatures()` / `tracker.MarketTracker` | Anzahl OCR-Aufrufe, verpasste Events | Grid 0.5–3 % mit Simulationslauf auf Annotated Frames |
| **Burst/Polling** | `poll_interval`, `poll_interval_burst`, Burst-Dauer | `tracker.MarketTracker` | Zeit bis Event-Erkennung, CPU/GPU-Last | Parameter Sweep über Test-Replays (Simulationsmodus) |
| **Parsing Cache** | `_PARSING_CACHE_TTL`, `MAX_SIZE` | `parsing.py` | Cache-Hit-Rate, Parsing-Latenz | Replay-Logs (5–10 Min) mit TTL-Varianten |
| **Parsing Heuristiken** | Regex-Prioritäten, `_strip_ui_collect_tail()` Filter, `_BOUNDARY_PATTERNS` | `parsing.py` | Fehlklassifizierungen, Laufzeit | Kohortenbasierte Kombinationstests (z. B. 32 Sample-Varianten) |
| **Database** | WAL, `synchronous`, `cache_size`, Batch-Größe | `database.py` + PRAGMA | Insert-Latenz, Journalgröße | Automatisierter Benchmark mit `scripts/perf/benchmark_scan.py` |
| **Preorder Cache** | `_cache_ttl`, Struktur (dict vs. OrderedDict) | `preorder_manager.py` | Lookup-Latenz, Trefferquote | Benchmark-Skript mit simulierten Events |
| **API Client** | Retry-Zahl, Backoff-Faktoren | `bdo_api_client.py` | Gesamtdauer Bulk-Abfragen | Replay API-Aufrufe mit Mock-Server |

## Phase 3 – Automatisierung & Tooling
- **Bench Runner**: CLI `python scripts/perf/run_benchmarks.py --scenario=o...` ruft Teilskripte auf, schreibt Ergebnisse in `docs/perf_reports/`.
- **Konfig-Katalog**: YAML/JSON-Definition pro Parameterfeld (Suche, Grenzen, Abbruchkriterien).
- **Result Evaluator**: Python-Modul `scripts/perf/evaluate_config.py` berechnet Score (z. B. `score = time_weight * norm_ms + error_weight * norm_error`).
- **Dashboard**: Optional Jupyter-Notebook `notebooks/perf_analysis.ipynb` für Visualisierung.

## Phase 4 – Integration in Pipeline
- **Profil-Lader**: Neue Klasse `PerformanceProfileManager` (z. B. in `utils.py`), die ROI/Modul-spezifische Settings lädt.
- **Fallback-Logik**: Konfigurationen versionieren (`profile_version`). Bei Fehlern automatischer Rollback auf „stable“.
- **Runtime-Adaption**: Telemetrie (Rolling Average) steuert Schwellwert-Korrekturen (z. B. ROI-Threshold ±0.1 bei hoher Fehlerrate).

## Phase 5 – Qualitätssicherung
- **Regression-Tests**: `pytest -k perf` ruft reproduzierbare Benchmarks (kleiner Datensatz) aus CI-pipeline-kompatiblen Jobs auf.
- **Health-Metriken**: Live-Debug Ausgabe (`log_debug`) sammelt Latenz-Percentiles, OCR-Hitrate.
- **Canary-Modus**: Option in GUI `Enable Canary Profile`, um neue Parameter isoliert zu testen.

## Risiko & Mitigation
- **GPU-Throttling**: Langläufer-Benchmarks limitieren via CUDA-Stream-Prio; Scripts pausieren zwischen Tests.
- **Overfitting an Debug-Screens**: Datensatz regelmäßig um Live-Captures aus unterschiedlichen Auflösungen erweitern.
- **Komplexität**: Parameterraum priorisieren (Pareto) und Iterationen pro Phase begrenzen.

## Deliverables
- `docs/performance_optimization_plan.md` (dieses Dokument).
- `scripts/perf/run_benchmarks.py` + Submodule.
- `config/easyocr_profiles.json` (auto-generiert).
- `docs/perf_reports/<date>.md` für jede Optimierungsrunde.
- Ergänzungen in `AGENTS.md` (Profil-Handling, Benchmarks, Fallback-Prozess).

## Nächste Schritte
1. Phase-0-Datensammlung starten, Ground Truth definieren.
2. EasyOCR-Benchmark-Skript erweitern (Accuracy + adaptive Suche).
3. Preprocessing-Parameter-Suche prototypisch aufsetzen (kleiner Raum, manuelle Auswertung).
4. Ergebnisse dokumentieren, Folgeiterationen priorisieren.
