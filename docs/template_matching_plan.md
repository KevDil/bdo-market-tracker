# Template-Matching Auto-Detection: Implementierungsplan

## Ziele
- **Automatische Regionserkennung**: Marktfenster (Overview & Detail) ohne manuelle Kalibrierung lokalisieren.
- **Performance**: Matching nur bei Bedarf, Laufzeit pro Erkennung < 50 ms auf RTX 4070 SUPER.
- **Robustheit**: UI-Verschiebungen, unterschiedliche Fensterzustände (Buy/Sell/Detail/Confirm) und Fokuswechsel handhaben.
- **Fallbacks**: Manuelle Regionseinstellung weiter verfügbar; gescheiterte Auto-Detection stört Live-Tracking nicht.

## Voraussetzungen
- Windows 10+, Python 3.10–3.13.
- `mss`, `opencv-python`, `numpy` bereits Bestandteil des Projekts.
- Referenzscreenshots in `dev-screenshots/windows/` & `dev-screenshots/transaction_log.png`.

## Architekturübersicht
1. **Template-Assets**
   - Basis-Templates aus `dev-screenshots/windows/*.png` (Overview-, Detail-, Confirm-Fenster).
   - Log-Template aus `dev-screenshots/transaction_log.png`.
   - Ablage als PNG unter `config/templates/` (neu) oder direkte Nutzung aus `dev-screenshots/`.
   - Optional mehrere Varianten (Buy/Sell, hell/dunkel, Confirm).

2. **Template-Layer** (`template_matching.py` neu)
   - Lädt Templates einmalig (Lazy Loading) und normalisiert (Graustufen, float32).
   - Bietet API:
     - `load_templates()` → Dict mit `Template`-Objekten (Name, Bild, Masken, Meta).
     - `match_templates(frame, templates, scales)` → Liste von Treffern.
     - `refine_match(match, frame)` → Validierung/Rescoring.
   - Enthält Parameterkonstanten: `MATCH_METHOD = cv2.TM_CCOEFF_NORMED`, Thresholds, Multi-Scale-Step.

3. **Vollbild-Capture**
   - Ergänzend zu `utils.capture_region()` neue Funktion `utils.capture_fullscreen()` (ohne manuelle Region).
   - Downsampling (z. B. auf 25 % via `cv2.resize`) zur Beschleunigung.

4. **Detection-Pipeline** (`utils.py` / neues Modul)
   - Trigger-Aufruf: Start der Anwendung, Fokus-Restore, signifikante Fehler (`Screenshot error`, Schwarzbild), manuelle GUI-Aktion.
   - Ablauf:
     1. Vollbild erfassen.
     2. Preprocessing (Graustufen, optional CLAHE).
     3. `match_templates()` iteriert Templates & Skalen (0.85–1.15, Schritt 0.05).
     4. Top-K Ergebnis(e) (max. 3) nach Score sortieren.
     5. Validierung: Score ≥ Threshold (z. B. 0.85), optional Zweit-Template (Log oder Button-Reihe) auf konsistenten Offset prüfen.
     6. Bei Erfolg: Region = `(x, y, x + width, y + height)` mit Fensterausdehnung aus `DEFAULT_REGION` (Breite/Höhe) berechnen.
     7. Plausibilitätsprüfung: Monitorgröße (`mss.monitors`), Mindestabstände zu Rändern, optional Mittelwert über mehrere Frames.
   - Rückgabe: `DetectionResult(region, score, template_name, scale, timestamp)`.

5. **Live-Tracking-Layer** (`window_tracker.py` neu oder in `template_matching.py`)
   - Verantwortlich für kontinuierliche Positionsüberwachung ohne merklichen Performance-Verlust.
   - Nutzt bei jedem Scan den bereits erfassten Frame (`self._current_frame`) und führt ein **lokales Template-Matching** im Suchfenster um die zuletzt bekannte Region (Margin z. B. ±80 px) aus.
   - Erzeugt aus dem ursprünglichen Treffer einen **Tracking-Template-Ausschnitt** (z. B. Kopfzeile „Central Market“ + Tab-Leiste) und cached diesen als `cv2`-Matrix.
   - Ablauf pro Scan:
     1. Zuschnitt des Suchfensters aus dem aktuellen Frame (gleiches Downsampling wie bei ROI-Analyse).
     2. `cv2.matchTemplate` mit Tracking-Template; akzeptiere Offsets bis ±80 px.
     3. Wenn Offset > Toleranz (z. B. 6 px) → Region um Delta verschieben, ROI-Caches invalidieren.
     4. Wenn Score < Threshold (z. B. 0.75) → Async-Task für Vollbild-Detection anstoßen, während aktuelle Region weitergenutzt wird.
   - Optional: Glättung via exponentiellem Moving Average, um Jitter zu vermeiden.
   - Tracking läuft synchron mit `auto_track`-Polling (0.15 s) und nutzt vorhandene Frames → kein zusätzliches Screen-Capture nötig.

6. **Integration in `MarketTracker` (`tracker.py`)**
   - `MarketTracker.__init__`:
     - Neues Flag `auto_detect_region` aus `config.DEFAULT_AUTO_DETECT_REGION`.
     - Wenn aktiv: vor erstem Scan Auto-Detection ausführen.
     - Erfolg → `self.region` setzen, `set_capture_region()` mit `LAST_DETECTED_REGION` persistieren.
   - **Recalibration Hooks**:
     - Beim Fokusverlust/ -rückkehr (`_capture_frame()`): wenn Region > Monitorfläche hinausläuft oder schwarzes Bild → Auto-Detection.
     - Nach `Screenshot error`: Retry-Limit (z. B. 3) → Auto-Detection erneut versuchen.
   - **ROI-Reset**: Nach Region-Update `self._last_roi_signatures` & `self._roi_skip_counters` zurücksetzen.

7. **GUI (`gui.py`)
   - Checkbox „Auto-Region erkennen“ (persistiert in `config`).
   - Buttons:
     - `Auto-Fenster finden` → einmaliger Scan.
     - Erfolgs-/Fehlermeldung mit Score & Template-Namen.
   - Region-Textfeld nur editierbar, wenn Auto-Detection deaktiviert oder manuelles Override.

8. **Persistenz (`config.py`)**
   - Neue Settings-Schlüssel `auto_detect_region` (bool), `last_detected_region` (Tuple).
   - Getter/Setter analog `get_capture_region()`/`set_capture_region()`.
   - Fallback: Wenn Auto-Detection fehlschlägt → `last_detected_region` oder `DEFAULT_REGION`.

9. **Dokumentation**
   - `AGENTS.md`: Abschnitt „Auto-Detection“ mit Triggern, Templates, Parametern, Fallback.
   - Eventuell `docs/template_matching_plan.md` (dieses Dokument) als Referenz.

## Algorithmische Details
- **Multi-Scale Matching**
  - Skalen: `[0.85, 0.90, 0.95, 1.00, 1.05, 1.10, 1.15]`.
  - Template-Resize pro Iteration via `cv2.resize(template, (0, 0), fx=scale, fy=scale)`.
  - Downsampled Vollbild (z. B. 960×540 aus 1920×1080) → Matching-Kosten ~5 ms/Template/Skala.
  - Optional: Pyramid Matching (`cv2.pyrDown`/`pyrUp`) statt direktem Resize.

- **Score-Validierung**
  - `cv2.TM_CCOEFF_NORMED`: Score ∈ [-1, 1]. Start-Threshold 0.85.
  - Zweite Validierung:
    - `match_templates()` kann zusätzlich `transaction_log.png` verwenden, um die rechtsseitige Position des Logs zu vergleichen.
    - Offset-Differenz ≤ ±10 px.
  - Zusätzlich: `detect_tab_from_text()` (OCR-Snippet) optional zur Verifikation (langsamer, nur im Zweifel einsetzen).

- **Performance-Schutz**
  - Auto-Detection läuft in separatem Thread (`ThreadPoolExecutor(max_workers=1)`), damit Polling nicht blockiert.
  - Timeout pro Matching-Batch (z. B. 150 ms) → bei Überschreitung Abbruch & Fallback.
  - Ergebnis wird asynchron in `self.region` übernommen; zwischenzeitlich weiter mit alter Region scannen.
  - Live-Tracking verwendet ausschließlich den bereits vorliegenden Frame (nach `_capture_frame`), wodurch kein zusätzlicher Screenshot entsteht.
  - Lokales Matching begrenzt das Suchfenster und reduziert Kosten auf ≤2 ms pro Scan.

- **Fehlerbehandlung**
  - Keine Treffer → GUI-Hinweis + Log (`log_debug("[AUTO-DETECT] No match (max score=...)")`).
  - Niedrige Scores → Suggestion, manuelle Kalibrierung zu nutzen.
  - Exceptions (z. B. fehlende Templates) → Fallback auf manuelle Region.

- **Drift Detection**
  - Kontinuierliches Tracking misst pro Scan den Offset; erst bei anhaltenden Abweichungen (z. B. 5 Scans unter Score-Threshold oder kumulativ >40 px Drift) wird eine Vollbild-Detection ausgelöst.
  - Zusätzlich: Periodischer Health-Check (alle 60 s) behält Multi-Scale-Matching bei, um schleichende Fehler zu erkennen.

## Testplan
- **Unit Tests**
  - Mocking von `mss` und `cv2.matchTemplate`, um Score-Threshold-Logik zu prüfen.
  - Tests für `template_matching`-Hilfsfunktionen (Skalierungs-Loop, Thresholds, Auswahl Top-K).
  - Persistenz-Tests für neue `config`-Settings.

- **Manual / Integration Tests** (`tests/manual/`)
  - Szenarien: Fenster verschoben, anderes UI-Theme, Confirm-Dialog offen, Marktfenster minimiert.
  - Performance-Messung: Start-Detection, kontinuierliches Tracking (≤2 ms pro Poll), Re-Detection (<150 ms total, <50 ms im Schnitt).
  - Fensterverschiebungen während laufendem Tracking (z. B. Drag & Drop) → Region folgt innerhalb ≤0.3 s.
  - Fallback: Ohne Marktfenster (Spielmenü) → Kein Match, manuelle Region bleibt aktiv.

- **Instrumentation**
  - `log_debug`-Einträge bei Start, Erfolg, Fehler, Score-Threshold, Laufzeit.
  - Optionale Telemetrie: Rolling Average der Matching-Zeiten.

## Risiken & Mitigation
- **UI-Skalierung ≠100 %**
  - Mit Multi-Scale abgedeckt; ansonsten ORB-Feature-Matching als Fallback implementieren.
- **Neue UI-Skins / Patches**
  - Templates aktualisieren (Dokumentation in `AGENTS.md`).
  - Optional adaptives Template-Update: erfolgreichen Treffer als neues Template cachen.
- **Überlagernde Fenster**
  - Fokus-Check (`is_bdo_window_in_foreground`) vor Auto-Detection.
  - Bei Transparent-Fenstern: Score-Threshold erhöhen oder Maske für Templates nutzen.
- **Performance-Drops**
  - Matching nur bei Triggern, nicht in Poll-Schleife.
  - Threads & Timeouts verhindern Blockaden.

## Aufgabenliste (Implementierung)
- **Vorbereitung**
  - Templates zuschneiden & speichern (`config/templates/`).
  - `AGENTS.md` um Feature-Vorschau ergänzen.
- **Coding**
  - `template_matching.py` implementieren (Laden, Matching, Validierung).
  - `utils.py` um `capture_fullscreen()` + Wrapper ergänzen.
  - `config.py` Settings + Getter/Setter erweitern.
  - `tracker.py` Auto-Detection-Hooks; ROI-Reset.
  - `gui.py` UI-Elemente & Aktionen.
- **Tests & Doku**
  - Unit + manuelle Tests.
  - Changelog/Release Notes.

## Umsetzungsschätzung
- **Coding**: 1–1.5 PT (inkl. Templates & Tests).
- **Feintuning**: 0.5 PT (Threshold, Logs, UX).
- **Dokumentation**: 0.25 PT.

## Follow-up-Ideen
- Feature-Matching (ORB/SIFT) als Fallback.
- Adaptive Templates (Capturing Erfolgs-Hit).
- Telemetrie → automatische Threshold-Anpassung.
- Integration mit Preorder Detection (z. B. Auto-Screenshot beim Aufpoppen neuer Fenster).
