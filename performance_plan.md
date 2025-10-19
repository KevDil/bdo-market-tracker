# Performance-Optimierungsplan: Scan-Latenz reduzieren

## Kontext & aktuelle Beobachtungen
- Nutzer:innen melden ~1,3 s OCR-Laufzeit im GPU-Modus und >3 s im CPU-Modus (Stand Januar 2025). Die Pipeline läuft vollständig synchron (`tracker.py:226-274`) und blockiert pro Scan auf `capture_region → preprocess → EasyOCR → Parsing`.
- In `_process_image` wird immer die „Balanced“-Vorverarbeitung mit CLAHE und Schärfung genutzt (`utils.py:207-259`), obwohl `fast_mode` verfügbar ist. Das erzeugt pro Frame zusätzliche 50–80 ms CPU-Zeit.
- Die ROI-Erkennung beschränkt sich auf die oberen 65 % des Fensters (`utils.py:194-203`), während die Repository-Guidelines ein 75 %-Trim vorgeben. Der Versatz deutet auf unnötig große OCR-Fläche bzw. fehlende Spezifikationstreue hin.
- EasyOCR wird stets mit `canvas_size=2240`, `paragraph=True` und `batch_size=1` betrieben (`utils.py:348-371`). Für ein ~1100 px breites ROI führt das zu Up-Scaling und längerem GPU-Vorlauf. PaddleOCR ist vorbereitet (`ocr_engines.py`), aber deaktiviert (`config.py:20-23`).
- Jeder Scan schreibt OCR-Text und Debug-Events in `ocr_log.txt` (`utils.py:28-61`) und speichert Debug-Bilder (`tracker.py:288-299`), solange `debug` aktiv ist. In vielen Installationen ist Debug standardmäßig an (`tracker.py:86-100`, `config.py:98-110`), was I/O-lastige Latenz einführt.
- Die MD5-basierte Cache-Prüfung auf Vollbild oder ROI (`utils.py:490-556`) kopiert den Bildausschnitt bei jedem Scan und blockiert im Falle eines Misses, obwohl anschließend erneut CLAHE gerechnet wird.
- `USE_ASYNC_PIPELINE` ist deaktiviert (`config.py:189-199`), sodass Capture, OCR und Parsing nicht überlappen. Gleichzeitig laufen alle OCR-Tasks über einen einzigen EasyOCR-Reader (`config.py:268-360`), der bei GPU-Verfügbarkeit zwar initialisiert wird, aber häufig auf CPU zurückfällt, wenn `torch.cuda.is_available()` false liefert (z. B. bei fehlenden Treibern).

## Phase 0 – Messbasis & Monitoring (sofort)
1. **Deterministisches Benchmarking aufsetzen**  
   - Schreibe ein Skript `scripts/perf/benchmark_scan.py`, das 20 aufeinanderfolgende Scans mit fixer ROI ausführt, Warmups verwirft und Capture-, Preprocess-, OCR- und Parsing-Zeiten getrennt protokolliert (Messpunkte sind in `tracker.py:235-274` bereits vorhanden).  
   - Ergänze eine Option, um GPU/CPU-Modus zu erzwingen (`set_use_gpu`) und Debug-Logging temporär auszuschalten.
2. **Profiler-Hooks & GPU-Telemetrie**  
   - Ergänze optionale Telemetrie (z. B. via `torch.cuda.memory_allocated()` und `torch.cuda.synchronize()`) in `_process_image` für Messläufe, ohne sie standardmäßig zu aktivieren.  
   - Stelle sicher, dass `log_text`/`log_debug` deaktivierbar sind (ENV-Flag) und nicht automatisch mitmessen.
3. **ROI-Visualisierung & Snapshot-Archiv**  
   - Lege reproduzierbare Test-Frames unter `dev-screenshots/` ab und dokumentiere ROI-Overlays, um Flächenreduktionen später beurteilen zu können.
4. **Messresultate festhalten (Januar 2025, GPU-Benchmark)**  
   - Capture ≈ 12 ms, Preprocess ≈ 1,6 ms, Postprocess ≈ 0 ms (Dry-Run).  
   - OCR dominiert mit ≈ 1 200 ms (p95 ≈ 1 223 ms), Cache-Hit-Rate 0 %.  
   - CUDA-Allokation ~200 MB, daher liegt das Optimierungspotenzial klar im OCR-Pfad.

## Phase 1 – Quick Wins (1–2 Tage, hohes Nutzen/Risiko-Verhältnis)
1. **Debug-IO standardmäßig abschalten**  
   - Setze den Persistenz-Default für `debug_mode` auf `False` (`config.py:98-116`) und wickle `log_text`, `log_debug` sowie `_write_debug_images` über denselben Schalter (`tracker.py:243-267`, `utils.py:28-61`).  
   - Ergänze im GUI eine Warnung, dass Debug nur für Fehlersuche aktiv sein soll.
2. **Vorverarbeitung beschleunigen**  
   - Führe einen adaptiven Modus ein: verwende `fast_mode=True` (`utils.py:230-235`) für GPU-Läufe oder wenn der letzte OCR-Confidence-Wert >0,65 lag; fallback auf CLAHE nur bei Qualitätsproblemen.  
   - Prüfe, ob das Schärfen komplett entfallen kann oder hardwarebeschleunigt via OpenCL (`cv2.UMat`).
3. **ROI trimmen & dynamisieren**  
   - Passe `detect_log_roi` so an, dass nur noch das rote Transaktionsfeld aus `dev-screenshots/regions.png` erfasst wird (oberes Log, keine Itemliste). Ergänze zwei neue Helper: `detect_metrics_roi` für das grüne Delta-Feld (Orders/Collect/Re-list) sowie `detect_window_label_roi` für die gelben Fenster-Titel.  
   - Lasse das Log-ROI bei jedem Poll verarbeiten, trigger die Metrik-/Label-ROIs nur bei Bedarf (z. B. wenn `detect_window_type` unsicher ist oder wenn neue Log-Einträge auftauchen).  
   - Dokumentiere die neue ROI-Aufteilung (75 % Trim laut Guidelines, zusätzliche Sub-ROIs) und stelle Konfiguration/Testbarkeit sicher.
4. **EasyOCR-/GPU-Pipeline härten**  
   - Verifiziere, dass EasyOCR tatsächlich auf der GPU läuft (Logging von `torch.cuda.get_device_name()`, `torch.cuda.is_available()` vor jedem Scan, optional Halbpräzision aktivieren).  
   - Reduziere `canvas_size` für GPU auf ~1600, deaktiviere `paragraph=True` und teste `detail=0`/`batch_size>1`, um die Erkennungszeit unter das beobachtete 1,2 s-Level zu drücken (`utils.py:348-371`).  
   - Für CPU-Läufe darf `contrast_ths` leicht erhöht werden; dokumentiere alle Parameteränderungen in den Repository-Guidelines.
5. **Cache-Hotpath entlasten**  
   - Ersetze das MD5-basiierte Hashing durch `np.ndarray.tobytes()` mit `blake2s` oder ein Rolling-Hash über downsampled Frames (`utils.py:490-533`).  
   - Cache auch das vorverarbeitete Graustufenbild, damit OCR-Hits ohne erneute CLAHE-Berechnung auskommen.
6. **Fokus & Poll-Steuerung verfeinern**  
   - Senke den Burst-Schlaf (`tracker.py:102-112`) nur bei echten `sell_item`/`buy_item`-Fenstern und halte das Standard-Polling bei 0,15 s, um unnötige Scans zu reduzieren.

## Phase 2 – Strukturelle Verbesserungen (eine Sprint-Länge)
1. **Asynchrones Capture/OCR reaktivieren**  
   - Reaktiviere `USE_ASYNC_PIPELINE` mit `ASYNC_QUEUE_MAXSIZE=1`, aber ermögliche ein zweites Worker-Thread für OCR, um Capture zu überlappen (`config.py:189-200`, `tracker.py:3950-4135`).  
   - Stelle sicher, dass die Queue ältere Frames droppt und füge Cancel-Backoff hinzu, um GUI-Stops responsiv zu halten.
2. **ROI-Diffing vor OCR**  
   - Implementiere schnelle Pixel-/Histogram-Vergleiche pro Sub-ROI (Log, Metriken, Fenster-Labels); wenn ein Abschnitt unverändert bleibt, überspringe die OCR dafür und nutze den Cache.  
   - Halte die Heuristiken im Tracker-State (`tracker.py:115-160`) fest, damit keine Events verloren gehen und Sub-ROIs synchron bleiben.
3. **OCR-Engine evaluieren**  
   - Teste PaddleOCR mit GPU („PPOCRv4 server“) und optimierten Parametern (`ocr_engines.py:118-206`) in separaten Benchmarkläufen.  
   - Alternativ evaluiere RapidOCR oder Tencent OCR (Python bindings), falls EasyOCR weiterhin >800 ms benötigt.
4. **Screen-Capture optimieren**  
   - Prüfe Alternativen wie `dxcam` oder `d3dshot`, die GPU-unterstütztes Capture bieten, und vergleiche Latenz gegen `mss` (`utils.py:160-169`).  
   - Achte darauf, dass Fokus-Checks (`utils.py:118-159`) erhalten bleiben.
5. **GPU-Scheduling verbessern**  
   - Verifiziere, dass EasyOCR den GPU-Pfad tatsächlich nutzt (`config.py:268-339`). Falls `torch.cuda.is_available()` false zurückgibt, biete einen Diagnosehinweis im GUI an.  
   - Implementiere einen Warmup-Lauf, der Modelle vorlädt und die ersten Scans beschleunigt.

## Phase 3 – Zukunftsthemen / Stretch Goals
1. **Inkrementelle Textverarbeitung**  
   - Erfasse OCR-Linienpositionen und führe nur noch Partial-OCR in Bereichen mit Änderungen aus (z. B. mittels Bounding Boxes aus EasyOCR).  
   - Kombiniere dies mit einem linearen Text-Diff, um DB-Dedupe zu entlasten.
2. **GPU-gestützte Vorverarbeitung**  
   - Portiere CLAHE/Filter auf CuPy oder TorchVision, um CPU-Spitzen zu vermeiden.  
   - Prüfe OpenCL-Unterstützung für Nutzer:innen ohne CUDA.
3. **Model-Feintuning**  
   - Finetune ein schlankes OCR-Modell (z. B. `PaddleOCR slim` oder ein CRNN) speziell auf BDO-Schriftarten und deploye es als ONNX/TensorRT-Modul.
4. **Adaptive Polling & Event-Trigger**  
   - Kopple den Poll-Interval an UI-Events (z. B. Fensterwechsel via WinAPI `SetWinEventHook`) statt an starres Timing.  
   - Reduziert GPU-Last in Phasen ohne Marktaktivität.

## Validierung & Qualitätssicherung
- Führe nach jeder Phase den vollständigen Test-Satz aus (`python scripts/run_all_tests.py`) und mindestens die Parsing-relevanten Unittests (`tests/unit/...`).  
- Vergleiche die Benchmark-Skripte aus Phase 0 vor und nach jeder Änderung, dokumentiere Ergebnisse im Repo (z. B. `docs/perf/scan_benchmarks.md`).  
- Aktualisiere das Repository-Guidelines-Dokument synchron mit jeder Parameteränderung (insbesondere ROI, OCR-Engine, Cache-Verhalten).  
- Stelle sicher, dass Debug-Logging bei Regressionsanalysen leicht reaktivierbar ist und dass `debug`-Artefakte nicht versehentlich im Release-Betrieb verbleiben.

## Erwartetes Ergebnis
- Phase 1 sollte die Scan-Zeit im GPU-Modus auf ≲0,8 s und im CPU-Modus auf ≲1,8 s drücken (durch Reduktion von Vorverarbeitung, Logging und OCR-Parameter).  
- Phase 2 zielt darauf ab, durch Overlap & Diffing unter 0,6 s (GPU) bzw. 1,2 s (CPU) zu gelangen.  
- Phase 3 liefert zusätzliche Reserven und Stabilität für künftige Patches oder höhere Auflösungen.
