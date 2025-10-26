# Implementierungsplan: Bedarfsgesteuerte ROI-OCR

**Datum:** 26. Oktober 2025  
**Branch:** feature/detail-window-capture  
**Autor:** AI Agent (basierend auf Code-Analyse und Requirements)

## 🎯 Zielsetzung

Reduzierung der OCR-Aufrufe durch bedarfsgesteuerte Ausführung: ROI-OCR wird nur dann durchgeführt, wenn aktive Verbraucher (Detail-Delta, UI-Inferenz, Preorder/Listing-Detection) die Daten tatsächlich benötigen. Dies minimiert CPU/GPU-Last und erhöht die Performance, ohne Transaktions-Detektion zu gefährden.

## 📋 Aktuelle Situation

### IST-Zustand (Analyse von tracker.py)

**Scan-Frequenzen:**
- Standard-Polling: 0.5s (500ms)
- Burst-Scans: 0.08s (80ms) bei Detail-Fenstern
- Game-Friendly Mode: ≥0.8s bei aktiver GPU

**ROI-OCR Aufrufe pro Scan (Lines 390-810):**
1. **Label-ROI** (detect_window_label_roi): Immer ausgeführt (~56.5ms)
2. **Log-ROI** (detect_log_roi): Bei Overview-Fenstern (~151.3ms)
   - Wird bei Detail-Fenstern übersprungen (Line 620: `skip_log_ocr = detail_window_detected`)
3. **Metrics-ROI** (detect_metrics_roi): Bei `_pending_metrics_refresh=True` (~186.0ms)
   - Refresh-Logik in Lines 647-703
   - Nach Fensterwechsel oder bei Burst-Scans
4. **Detail-ROIs** (Lines 711-791):
   - Item-Name-ROI (~20.2ms) - wird gecacht nach erstem Scan
   - Balance-ROI (~18.1ms)
   - Warehouse-ROI (~18.0ms)
   - Preorder-Input-ROI (~wird in _extract_preorder_input_fields aufgerufen)

**Aktuelles Caching (Lines 510-645):**
- ROI-Signature-basiertes Diffing (compute_roi_stats_signature)
- Cache-TTL: 5.0s, MAX_CACHE_SIZE: 20
- Cache-Hit-Rate: ~50-70%

**Probleme:**
1. ❌ Metrics-ROI wird auch ausgeführt wenn keine UI-Inferenz benötigt wird
2. ❌ Detail-Balance/Warehouse werden kontinuierlich gescannt auch ohne aktive Deltas
3. ❌ Keine expliziten Need-Flags - schwer nachvollziehbar welche Komponente welche ROI braucht
4. ❌ Log-ROI wird bei JEDEM Overview-Scan ausgeführt (auch wenn Baseline unverändert)
5. ❌ Preorder-Input-ROI-Extraktion läuft unabhängig von tatsächlichem Bedarf

## 🏗️ Architektur-Änderungen

### 1. Flag-System Einführen

**Neue Instanz-Variablen in MarketTracker.__init__ (nach Line 230):**

```python
# === BEDARFSGESTEUERTE ROI-OCR FLAGS ===
# Diese Flags steuern wann welche ROI OCR benötigt
# Werden von Verbrauchern (Detail-Delta, UI-Inferenz, etc.) gesetzt
self._needs_log_text = True          # Log-ROI OCR benötigt? (Default: True für ersten Scan)
self._needs_metrics_text = False     # Metrics-ROI OCR benötigt?
self._needs_detail_balance = False   # Detail-Balance-ROI benötigt?
self._needs_detail_warehouse = False # Detail-Warehouse-ROI benötigt?
self._needs_detail_inputs = False    # Detail-Input-Felder (Preorder/Listing) benötigt?

# === ROI-USAGE STATISTIK ===
# Pro Scan tracking für Debug/Diagnostik
self._roi_usage_last_scan = {
    'label': 'not_run',      # Status: 'ocr', 'cache', 'skipped', 'not_run'
    'log': 'not_run',
    'metrics': 'not_run',
    'detail_balance': 'not_run',
    'detail_warehouse': 'not_run',
    'detail_inputs': 'not_run'
}

# === DETAIL-WINDOW STATE MACHINE ===
# State: idle, baseline, delta
# idle: Kein Detail-Fenster aktiv
# baseline: Baseline-Capture läuft (Balance/Warehouse-OCR aktiv)
# delta: Delta-Monitoring (nur bei Änderungen OCR)
self._detail_metric_state = 'idle'
```

**Dokumentations-Kommentar in process_ocr_text (nach Line 4837):**

```python
def process_ocr_text(self, full_text):
    """
    Hauptfunktion: Parsen von OCR-Text und Transaktions-Extraktion.
    
    === VERBRAUCHER VON ROI-FLAGS ===
    
    _needs_log_text:
        - Gesetzt von: process_ocr_text (wenn Overview-Fenster aktiv)
        - Verwendet von: _scan_region (Line 620+)
        - Zurückgesetzt: Nach erfolgreichem Log-OCR
        
    _needs_metrics_text:
        - Gesetzt von: _infer_transactions_from_ui (Line 6350+) wenn UI-Deltas ohne Log-Anker
        - Gesetzt von: Fensterwechsel (Line 4907) wenn Rate-Limit erlaubt
        - Verwendet von: _scan_region (Line 647-703)
        - Zurückgesetzt: Nach erfolgreichem Metrics-OCR oder Cache-Hit
        
    _needs_detail_balance / _needs_detail_warehouse:
        - Gesetzt von: _monitor_detail_window (Line 3894) State-Transition
        - Verwendet von: _scan_region (Line 756, 771)
        - Zurückgesetzt: Nach erfolgreichem Detail-OCR oder Timeout
        
    _needs_detail_inputs:
        - Gesetzt von: _detect_preorder_placement / _detect_listing_placement
        - Gesetzt von: _monitor_detail_window (Line 4028) bei Baseline-Capture
        - Verwendet von: _extract_preorder_input_fields (Line 1097)
        - Zurückgesetzt: Nach erfolgreichem Input-OCR
        
    === SCAN-ABLAUF MIT FLAGS ===
    
    1. Label-OCR: Immer (zur Fenster-Erkennung)
    2. Log-OCR: Nur wenn _needs_log_text=True AND Overview-Fenster
    3. Metrics-OCR: Nur wenn _needs_metrics_text=True AND roi_changed
    4. Detail-OCR: Nur wenn Detail-Fenster UND entsprechendes Flag=True
    5. Nach OCR: Flag zurücksetzen (außer bei Fehlern → Retry)
    """
```

### 2. Helper-Funktionen Hinzufügen

**Neue Methoden in MarketTracker (nach Line 950):**

```python
def _set_need_flag(self, flag_name: str, value: bool, reason: str = ""):
    """
    Setzt ein Need-Flag mit Debug-Logging.
    
    Args:
        flag_name: Name des Flags ('log_text', 'metrics_text', 'detail_balance', etc.)
        value: True = OCR benötigt, False = nicht benötigt
        reason: Grund für Flag-Änderung (für Debug-Logs)
    """
    attr_name = f'_needs_{flag_name}'
    old_value = getattr(self, attr_name, None)
    
    if old_value == value:
        return  # Keine Änderung
    
    setattr(self, attr_name, value)
    
    if self.debug:
        action = "ENABLED" if value else "DISABLED"
        log_debug(f"[ROI-FLAG] {flag_name}: {action} | Reason: {reason}")

def _schedule_metrics_refresh(self, reason: str = ""):
    """
    Plant Metrics-ROI-Refresh ein (setzt Flag mit Rate-Limiting).
    
    Args:
        reason: Grund für Refresh (für Debug-Logs)
    """
    now = datetime.datetime.now()
    
    # Rate-Limiting prüfen
    time_since_last_refresh = None
    if self._last_metrics_refresh_time is not None:
        time_since_last_refresh = (now - self._last_metrics_refresh_time).total_seconds()
    
    # Burst-Mode überschreibt Rate-Limit
    is_burst = (self._burst_until and now < self._burst_until) or self._request_immediate_rescan > 0
    
    if is_burst or time_since_last_refresh is None or time_since_last_refresh >= 1.0:
        self._set_need_flag('metrics_text', True, reason)
    else:
        if self.debug:
            log_debug(f"[METRICS-REFRESH] Skipped due to rate-limiting (last_refresh={time_since_last_refresh:.2f}s < 1.0s)")

def _set_detail_metric_state(self, state: str, reason: str = ""):
    """
    Setzt Detail-Window State-Machine und entsprechende Flags.
    
    Args:
        state: 'idle', 'baseline', 'delta'
        reason: Grund für State-Änderung
    """
    valid_states = ('idle', 'baseline', 'delta')
    if state not in valid_states:
        if self.debug:
            log_debug(f"[DETAIL-STATE] Invalid state '{state}' - must be one of {valid_states}")
        return
    
    old_state = self._detail_metric_state
    if old_state == state:
        return
    
    self._detail_metric_state = state
    
    # State-spezifische Flag-Updates
    if state == 'idle':
        # Kein Detail-Fenster → Alle Detail-Flags aus
        self._set_need_flag('detail_balance', False, "Detail-State: idle")
        self._set_need_flag('detail_warehouse', False, "Detail-State: idle")
        self._set_need_flag('detail_inputs', False, "Detail-State: idle")
        
    elif state == 'baseline':
        # Baseline-Capture → Balance & Warehouse benötigt
        self._set_need_flag('detail_balance', True, "Detail-State: baseline (capture)")
        self._set_need_flag('detail_warehouse', True, "Detail-State: baseline (capture)")
        # Inputs nur bei Buy-Window
        if self._detail_window_type == 'buy_item':
            self._set_need_flag('detail_inputs', True, "Detail-State: baseline (preorder detection)")
        
    elif state == 'delta':
        # Delta-Monitoring → Nur bei tatsächlichen Änderungen OCR
        # Flags werden on-demand von _monitor_detail_window gesetzt
        pass
    
    if self.debug:
        log_debug(f"[DETAIL-STATE] Transition: {old_state} → {state} | Reason: {reason}")
```

### 2.1 Lebenszyklus & Verantwortlichkeiten der Flags

Um Missbrauch zu vermeiden, braucht jedes Flag einen klaren „Besitzer“:

| Flag | Setzt | Löscht | Bemerkung |
| --- | --- | --- | --- |
| `_needs_log_text` | `process_ocr_text` wenn Overview-Text neu oder Baseline ungültig; `auto_track` beim Start | Nach erfolgreichem `log`-OCR innerhalb `_scan_region` **und** sobald `process_ocr_text` alle Einträge abgearbeitet hat | Zwischen zwei Overview-Frames bleibt es `False`; Detailfenster setzen es temporär auf `False` |
| `_needs_metrics_text` | `_infer_transactions_from_ui` sobald UI-Deltas benötigt werden; `_schedule_metrics_refresh` bei Fensterwechsel/Burst | `_clear_metrics_refresh` nach OCR oder Cache-Hit; `_infer_transactions_from_ui` nach erfolgreichem Inferenzlauf | Damit werden Metrics wirklich nur als Fallback gelesen |
| `_needs_detail_balance/_warehouse` | `_set_detail_metric_state('baseline'/'delta')` sowie `_force_detail_metric_refresh` | `_set_detail_metric_state('idle')` nach Transaktion oder Timeout | Einstellungen erfolgen ausschließlich über die State-Machine |
| `_needs_detail_inputs` | `_detect_preorder_placement/_detect_listing_placement` kurz vor der Input-ROI-OCR | Nach erfolgreichem Parsen oder wenn `_detail_cached_input_fields` bereits gefüllt ist | Kein automatisches Setzen beim Betreten des Fensters mehr |

Diese Tabelle im Plan ergänzt den bisherigen Abschnitt und stellt sicher, dass Flags nicht „auf Verdacht“ gesetzt bleiben.

### 2.2 UI-Metrics wirklich zum Fallback machen

* `_infer_transactions_from_ui()` muss `_needs_metrics_text = True` setzen, sobald ein Item ohne Log-Anker, aber mit UI-Deltas verarbeitet werden soll. Erst nach erfolgreichem `tx_candidates.append(...)` wird das Flag wieder `False`.  
* Fensterwechsel/Burst rufen nur `_schedule_metrics_refresh()`, die tatsächliche OCR-Ausführung passiert erst, wenn das Flag gesetzt bleibt **und** `roi_changed["metrics"]` true ist.  
* Im Overview-Pfad (`process_ocr_text`) darf `cached_metrics` überhaupt nur ausgewertet werden, wenn `_needs_metrics_text` oder `metrics_refresh_ran` true ist; ansonsten wird der Metrics-Text ignoriert. Dadurch ist garantiert, dass UI-Deltas wirklich nur als Fallback dienen.

### 3. Flag-Lebenszyklus Definieren

#### 3.1 Log-Text Flag

**Modifikation in _scan_region (um Line 620):**

```python
# === LOG-ROI: Nur bei Overview UND Flag gesetzt ===
text = ""
log_roi_skipped = False

# Entscheidung: Log-OCR benötigt?
need_log_ocr = self._needs_log_text and (not detail_window_detected)

if need_log_ocr and log_roi:
    # Prüfe ROI-Änderung
    if roi_changed["log"]:
        # ROI hat sich geändert → OCR durchführen
        text, was_cached, ocr_stats = ocr_image_cached(
            img,
            method='auto',
            use_roi=True,
            preprocessed=proc,
            fast_mode=use_fast_preprocess,
            roi=log_roi,
            roi_label="log",
            cache_tag="log",
        )
        self._last_roi_results["log"] = text
        
        # ROI-Usage tracking
        self._roi_usage_last_scan['log'] = 'cache' if was_cached else 'ocr'
        
        # Flag zurücksetzen nach erfolgreichem OCR
        self._set_need_flag('log_text', False, "Log-OCR completed successfully")
        
    else:
        # ROI unverändert → Cache verwenden
        text = self._last_roi_results["log"]
        log_roi_skipped = True
        self._roi_usage_last_scan['log'] = 'cache'
        
        # Flag NICHT zurücksetzen - nächster Scan kann neue Daten bringen
        # (z.B. wenn User scrollt aber ROI-Signature noch ähnlich ist)
        
    if self.debug:
        cache_status = "cache-hit" if was_cached or log_roi_skipped else "fresh-ocr"
        log_debug(f"{perf_prefix} Log-OCR: {cache_status}, need_flag={self._needs_log_text}")
        
elif not need_log_ocr and not detail_window_detected:
    # Log-Flag nicht gesetzt → Skip OCR, use cached result
    text = self._last_roi_results.get("log", "")
    self._roi_usage_last_scan['log'] = 'skipped'
    
    if self.debug:
        log_debug(f"{perf_prefix} Log-OCR SKIPPED (_needs_log_text=False)")
        
elif detail_window_detected:
    # Detail-Window → Log-OCR nie ausführen
    self._roi_usage_last_scan['log'] = 'not_run'
```

**Set-Logic in process_ocr_text (um Line 4870):**

```python
# Window-Type erkannt → Log-Flag für Overview setzen
if wtype in ("sell_overview", "buy_overview"):
    # Overview-Fenster → Log-Text benötigt
    self._set_need_flag('log_text', True, f"Window: {wtype} (Overview)")
else:
    # Detail-Fenster → Log-Text NICHT benötigt
    self._set_need_flag('log_text', False, f"Window: {wtype} (Detail)")
```

**Reset-Logic nach erfolgreichem Parse:**

Nach erfolgreichem `split_text_into_log_entries()` mit neuen Einträgen:

```python
# In process_ocr_text, nach Line 5200 (nach structured = split_text_into_log_entries)
if structured and len(structured) > 0:
    # Neue Einträge gefunden → Log-Text wurde erfolgreich verarbeitet
    # Flag bleibt TRUE für nächsten Scan (kontinuierliches Monitoring)
    pass
else:
    # Keine neuen Einträge → Log-Text kann gecacht bleiben
    # Flag bleibt TRUE (warten auf neue Daten)
    pass
```

#### 3.2 Metrics-Text Flag

**Modifikation in _scan_region (um Line 647):**

```python
# === METRICS-ROI: Nur wenn Flag gesetzt UND ROI geändert ===
metrics_refresh_ran = False
metrics_roi_skipped = False

if detail_window_detected:
    # Detail-Window → Metrics nicht verfügbar
    refresh_metrics = False
    self._roi_usage_last_scan['metrics'] = 'not_run'
else:
    # Overview-Window → Prüfe Flag
    refresh_metrics = self._needs_metrics_text

if refresh_metrics and roi_changed["metrics"]:
    # Metrics benötigt UND ROI geändert → OCR
    if metrics_roi:
        metrics_text, metrics_cached, metrics_stats = ocr_image_cached(
            img,
            method='auto',
            use_roi=True,
            preprocessed=proc,
            fast_mode=use_fast_preprocess,
            roi=metrics_roi,
            roi_label="metrics",
            cache_tag="metrics",
        )
        if metrics_text:
            self._last_metrics_text = metrics_text
            self._last_roi_results["metrics"] = metrics_text
        
        metrics_refresh_ran = True
        self._roi_usage_last_scan['metrics'] = 'cache' if metrics_cached else 'ocr'
        
        # FLAG ZURÜCKSETZEN nach erfolgreichem OCR
        self._set_need_flag('metrics_text', False, "Metrics-OCR completed")
        
        # Housekeeping
        self._metrics_refresh_failures = 0
        self._last_metrics_refresh_time = now_dt
        self._last_metrics_refresh_ts = now_dt
        
    else:
        # ROI detection failed
        self._metrics_refresh_failures += 1
        if self._metrics_refresh_failures >= 3:
            # Give up after 3 failures
            self._set_need_flag('metrics_text', False, "Metrics-ROI detection failed 3x")
            self._metrics_refresh_failures = 0
        self._roi_usage_last_scan['metrics'] = 'failed'
        
elif refresh_metrics and not roi_changed["metrics"]:
    # Flag gesetzt ABER ROI unverändert → Cache verwenden
    metrics_text = self._last_roi_results.get("metrics", "")
    self._roi_usage_last_scan['metrics'] = 'cache'
    
    # FLAG ZURÜCKSETZEN nach Cache-Hit
    self._set_need_flag('metrics_text', False, "Metrics from cache (ROI unchanged)")
    
    # Housekeeping
    self._metrics_refresh_failures = 0
    self._last_metrics_refresh_time = now_dt
    self._last_metrics_refresh_ts = now_dt
    
elif not refresh_metrics:
    # Flag NICHT gesetzt → Skip komplett
    self._roi_usage_last_scan['metrics'] = 'skipped'
    if self.debug:
        log_debug(f"{perf_prefix} Metrics-OCR SKIPPED (_needs_metrics_text=False)")
```

**Set-Logic in Verbrauchern:**

```python
# 1. UI-Inferenz (in process_ocr_text, um Line 6350+)
# Wenn kein Log-Anker vorhanden ABER UI-Deltas erkannt
if not has_log_anchor and ui_delta_detected:
    self._set_need_flag('metrics_text', True, "UI-Inferenz: Deltas ohne Log-Anker erkannt")

# 2. Fensterwechsel (in process_ocr_text, um Line 4907)
if prev_window != wtype and wtype in ("sell_overview", "buy_overview"):
    self._schedule_metrics_refresh(reason=f"Window transition: {prev_window} → {wtype}")

# 3. Burst-Scan Start
if self._burst_until and now < self._burst_until:
    self._schedule_metrics_refresh(reason="Burst-scan active")
```

**Reset nach UI-Inferenz:**

```python
# Nach erfolgreichem tx_candidates.append in _infer_ui_transaction logic
tx_candidates.append({
    'item_name': item_name,
    'quantity': inferred_qty,
    'price': inferred_price,
    # ...
    '_ui_inferred': True
})

# Flag zurücksetzen - UI-Deltas wurden verarbeitet
self._set_need_flag('metrics_text', False, "UI-Inferenz completed")
```

#### 3.3 Detail-Balance/Warehouse Flags

**Integration mit State-Machine in _monitor_detail_window (um Line 3950):**

```python
# 1. Detail-Fenster-Eintritt → BASELINE State
if not self._detail_window_active:
    # Aktiviere Baseline-Capture
    self._set_detail_metric_state('baseline', reason=f"Detail-Window entered: {window_type}")
    
    # State-Machine setzt automatisch Balance/Warehouse Flags
    # (siehe _set_detail_metric_state Implementierung)
    
    # ... Baseline-Capture-Code ...
    
    return

# 2. Nach erfolgreicher Baseline-Capture → DELTA State
if self._detail_baseline_captured:
    self._set_detail_metric_state('delta', reason="Baseline captured, monitoring deltas")

# 3. Delta-Monitoring: Flags on-demand setzen
if self._detail_metric_state == 'delta':
    # Balance/Warehouse nur bei vermuteter Änderung
    # Z.B. nach User-Interaktion (Button-Click simuliert durch Burst-Scan)
    
    if self._request_immediate_rescan > 0:
        # Burst-Scan aktiv → Metrics benötigt für Delta-Detection
        self._set_need_flag('detail_balance', True, "Burst-scan: Check for balance delta")
        self._set_need_flag('detail_warehouse', True, "Burst-scan: Check for warehouse delta")
    else:
        # Kein Burst → Metrics nicht benötigt (warte auf nächsten Trigger)
        self._set_need_flag('detail_balance', False, "Delta-State: idle")
        self._set_need_flag('detail_warehouse', False, "Delta-State: idle")

# 4. Nach erfolgreicher Transaktion → Rolling Baseline
# Balance/Warehouse müssen für NÄCHSTE Transaktion erneut gescannt werden
if transaction_saved:
    # Update Rolling Baseline
    self._detail_baseline_balance = current_balance
    self._detail_baseline_warehouse = current_warehouse
    
    # Flags für NÄCHSTE Delta-Detection vorbereiten
    # Aber NICHT sofort setzen - nur bei Burst
    if self._burst_until and datetime.datetime.now() < self._burst_until:
        self._set_need_flag('detail_balance', True, "Rolling baseline: next delta")
        self._set_need_flag('detail_warehouse', True, "Rolling baseline: next delta")

# 5. Timeout oder Detail-Fenster geschlossen → IDLE State
timeout_seconds = 30.0  # 30s ohne Änderung
if (datetime.datetime.now() - self._detail_detail_snapshot_ts).total_seconds() > timeout_seconds:
    self._set_detail_metric_state('idle', reason=f"Timeout: {timeout_seconds}s without changes")
    self._reset_detail_window_state()
```

**OCR-Ausführung in _scan_region (um Line 756):**

```python
# === DETAIL-BALANCE-ROI ===
if detail_window_detected and self._needs_detail_balance:
    balance_roi = detect_detail_balance_roi(proc, detected_detail_type)
    if balance_roi and roi_changed.get("detail_balance", True):
        balance_text, _, _ = ocr_image_cached(
            img,
            method='auto',
            use_roi=True,
            preprocessed=proc,
            fast_mode=use_fast_preprocess,
            roi=balance_roi,
            roi_label="detail_balance",
            cache_tag="detail_balance",
        )
        self._roi_usage_last_scan['detail_balance'] = 'ocr'
        
        # Flag zurücksetzen nach erfolgreichem OCR
        self._set_need_flag('detail_balance', False, "Balance-OCR completed")
        
    elif balance_roi and not roi_changed.get("detail_balance", False):
        # ROI unverändert → Cache
        balance_text = self._last_roi_results.get("detail_balance", "")
        self._roi_usage_last_scan['detail_balance'] = 'cache'
        self._set_need_flag('detail_balance', False, "Balance from cache")
        
elif detail_window_detected and not self._needs_detail_balance:
    # Detail-Window ABER Flag nicht gesetzt → Skip
    balance_text = self._last_roi_results.get("detail_balance", "")
    self._roi_usage_last_scan['detail_balance'] = 'skipped'
    
# === Analog für WAREHOUSE-ROI ===
```

#### 3.4 Detail-Inputs Flag

**Set-Logic bei Preorder/Listing-Detection:**

```python
# In _detect_preorder_placement / _detect_listing_placement
def _detect_preorder_placement(self, item_name: str, ocr_text: str) -> bool:
    """Erkennt ob Preorder platziert wurde durch Input-Feld-Analyse."""
    
    # Flag setzen: Input-Felder müssen gelesen werden
    self._set_need_flag('detail_inputs', True, reason=f"Preorder detection: {item_name}")
    
    # ... Input-Field-Extraktion ...
    
    # Flag zurücksetzen nach erfolgreicher Extraktion
    self._set_need_flag('detail_inputs', False, reason="Input fields extracted")
    
    return preorder_detected
```

**OCR-Ausführung in _extract_preorder_input_fields (um Line 1097):**

```python
def _extract_preorder_input_fields(self, img, proc_img, window_type: str):
    """Extrahiert Preorder-Eingabewerte aus Detail-Fenster Input-ROI."""
    
    # Prüfe Flag: Input-OCR benötigt?
    if not self._needs_detail_inputs:
        # Flag nicht gesetzt → Use Cache
        if hasattr(self, '_detail_cached_input_fields'):
            cached = self._detail_cached_input_fields
            cache_age = (datetime.datetime.now() - self._detail_cached_input_timestamp).total_seconds()
            
            if cached and cache_age < 5.0:  # 5s Cache-TTL
                if self.debug:
                    log_debug(f"[PREORDER-INPUT] Using cached input fields (age={cache_age:.1f}s)")
                self._roi_usage_last_scan['detail_inputs'] = 'cache'
                return cached
    
    # Flag gesetzt ODER Cache abgelaufen → OCR durchführen
    try:
        roi = detect_detail_preorder_input_roi(proc_img, window_type)
        if not roi:
            self._roi_usage_last_scan['detail_inputs'] = 'failed'
            return None
        
        input_text, was_cached, cache_stats = ocr_image_cached(
            img,
            method='auto',
            use_roi=True,
            preprocessed=proc_img,
            fast_mode=False,
            roi=roi,
            roi_label="preorder_input",
            cache_tag="preorder_input",
        )
        
        self._roi_usage_last_scan['detail_inputs'] = 'cache' if was_cached else 'ocr'
        
        # Parse Input-Text → Extract price/quantity
        result = self._parse_input_fields(input_text, window_type)
        
        if result:
            # Cache für spätere Verwendung
            self._detail_cached_input_fields = result
            self._detail_cached_input_timestamp = datetime.datetime.now()
            
            # Flag zurücksetzen
            self._set_need_flag('detail_inputs', False, "Input-OCR completed")
            
        return result
        
    except Exception as e:
        if self.debug:
            log_debug(f"[PREORDER-INPUT] OCR error: {e}")
        self._roi_usage_last_scan['detail_inputs'] = 'failed'
        return None
```

### 4. ROI-Usage Statistik & Instrumentation

**Statistik-Reset pro Scan (am Anfang von _scan_region):**

```python
# Reset ROI-Usage-Statistik für diesen Scan
self._roi_usage_last_scan = {
    'label': 'not_run',
    'log': 'not_run',
    'metrics': 'not_run',
    'detail_balance': 'not_run',
    'detail_warehouse': 'not_run',
    'detail_inputs': 'not_run'
}
```

**Debug-Output am Ende von _scan_region:**

```python
# Am Ende der Funktion, vor return
if self.debug or get_debug_mode('roi_stats'):
    # Zähle OCR-Aufrufe
    ocr_count = sum(1 for status in self._roi_usage_last_scan.values() if status == 'ocr')
    cache_count = sum(1 for status in self._roi_usage_last_scan.values() if status == 'cache')
    skip_count = sum(1 for status in self._roi_usage_last_scan.values() if status == 'skipped')
    
    log_debug(
        f"[ROI-STATS] Scan #{self._scan_counter}: "
        f"OCR={ocr_count}, Cache={cache_count}, Skipped={skip_count} | "
        f"Details: {self._roi_usage_last_scan}"
    )
```

**Aggregierte Session-Statistik:**

```python
# Neue Instanz-Variable in __init__
self._roi_usage_session_stats = {
    'scans_total': 0,
    'label': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
    'log': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
    'metrics': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
    'detail_balance': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
    'detail_warehouse': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0},
    'detail_inputs': {'ocr': 0, 'cache': 0, 'skipped': 0, 'failed': 0}
}

# Update am Ende von _scan_region
self._roi_usage_session_stats['scans_total'] += 1
for roi_name, status in self._roi_usage_last_scan.items():
    if status != 'not_run':
        self._roi_usage_session_stats[roi_name][status] += 1

# Neue Methode für Summary-Report
def get_roi_usage_summary(self) -> dict:
    """Returns aggregated ROI-usage statistics for current session."""
    stats = self._roi_usage_session_stats.copy()
    
    # Calculate percentages
    total_scans = stats['scans_total']
    if total_scans > 0:
        for roi_name in ['label', 'log', 'metrics', 'detail_balance', 'detail_warehouse', 'detail_inputs']:
            roi_stats = stats[roi_name]
            total_activations = sum(roi_stats.values())
            roi_stats['total_activations'] = total_activations
            roi_stats['activation_rate'] = (total_activations / total_scans) * 100.0
            
            if total_activations > 0:
                roi_stats['ocr_rate'] = (roi_stats['ocr'] / total_activations) * 100.0
                roi_stats['cache_rate'] = (roi_stats['cache'] / total_activations) * 100.0
                roi_stats['skip_rate'] = (roi_stats['skipped'] / total_activations) * 100.0
    
    return stats
```

## 📦 Test-Strategie

### Unit-Tests

**Test 1: Detail-Burst ohne Transaktion**
```python
# tests/unit/test_roi_demand_flags.py

def test_detail_burst_no_transaction_minimal_ocr():
    """
    Szenario: Detail-Fenster öffnet, Burst-Scans laufen, KEINE Transaktion.
    Erwartung: Balance/Warehouse nur beim BASELINE-Scan OCR.
    """
    tracker = MarketTracker(debug=True)
    
    # Simuliere Detail-Window-Entry
    tracker._detail_needs_baseline_capture = True
    tracker._set_detail_metric_state('baseline', "Test: Baseline capture")
    
    # Flags sollten gesetzt sein
    assert tracker._needs_detail_balance == True
    assert tracker._needs_detail_warehouse == True
    
    # Simuliere ersten Scan (Baseline)
    # ... mock OCR calls ...
    
    # Nach Baseline: State → delta
    tracker._set_detail_metric_state('delta', "Test: Monitoring")
    
    # Keine Burst-Scans mehr → Flags sollten AUS sein
    assert tracker._needs_detail_balance == False
    assert tracker._needs_detail_warehouse == False
    
    # Statistik prüfen
    stats = tracker.get_roi_usage_summary()
    assert stats['detail_balance']['ocr'] == 1  # Nur 1x (Baseline)
    assert stats['detail_warehouse']['ocr'] == 1
```

**Test 2: Placed + UI-Deltas → Metrics-OCR**
```python
def test_placed_with_ui_deltas_triggers_metrics_ocr():
    """
    Szenario: Log zeigt "Placed order", UI-Metrics zeigen Deltas.
    Erwartung: _needs_metrics_text wird gesetzt, genau 1x Metrics-OCR.
    """
    tracker = MarketTracker(debug=True)
    tracker.current_window = 'buy_overview'
    
    # Initial: Metrics-Flag aus
    assert tracker._needs_metrics_text == False
    
    # Simuliere Parsing mit placed-only entry + UI-Deltas
    ocr_text = """
    11:23 Placed order of Lion Blood x5000 for 4,270,000 Silver
    """
    
    # Mock UI-Metrics
    tracker._last_ui_buy_metrics = {
        'lion blood': {'ordersCompleted': 5, 'remainingPrice': 21350000}
    }
    
    # Process
    tracker.process_ocr_text(ocr_text)
    
    # Flag sollte gesetzt sein (UI-Inferenz benötigt Metrics)
    assert tracker._needs_metrics_text == True
    
    # Simuliere Scan mit Metrics-OCR
    # ... mock _scan_region ...
    
    # Nach OCR: Flag sollte zurückgesetzt sein
    assert tracker._needs_metrics_text == False
    
    # Statistik
    stats = tracker.get_roi_usage_summary()
    assert stats['metrics']['ocr'] == 1  # Genau 1x
```

**Test 3: Normales Overview → Log aktiv, Metrics deaktiviert**
```python
def test_overview_with_transactions_log_active_metrics_inactive():
    """
    Szenario: Overview-Fenster mit vollständigen Transaktions-Log-Einträgen.
    Erwartung: Log-OCR aktiv, Metrics-OCR bleibt deaktiviert.
    """
    tracker = MarketTracker(debug=True)
    tracker.current_window = 'buy_overview'
    
    ocr_text = """
    11:23 Transaction of Lion Blood worth 4,270,000 Silver
    11:24 Purchased 5000x Lion Blood for 4,270,000 Silver
    """
    
    # Process
    tracker.process_ocr_text(ocr_text)
    
    # Log-Flag sollte TRUE bleiben (kontinuierliches Monitoring)
    assert tracker._needs_log_text == True
    
    # Metrics-Flag sollte FALSE sein (keine UI-Inferenz benötigt)
    assert tracker._needs_metrics_text == False
    
    # Statistik nach mehreren Scans
    for _ in range(5):
        # ... mock scan ...
        pass
    
    stats = tracker.get_roi_usage_summary()
    assert stats['log']['ocr'] > 0  # Log-OCR aktiv
    assert stats['metrics']['ocr'] == 0  # Metrics nie benötigt
```

### Integrations-Tests

**Replay-Test mit dev-screenshots:**

```python
# tests/integration/test_roi_demand_replay.py

def test_detail_window_session_replay():
    """
    Replays Detail-Window-Session aus dev-screenshots/windows/*.png
    Misst ROI-Aufrufe vorher/nachher.
    """
    screenshots = sorted(Path('dev-screenshots/windows/buy_item').glob('*.png'))
    
    # Test WITHOUT demand-driven OCR
    tracker_baseline = MarketTracker(debug=False)
    baseline_stats = run_replay_session(tracker_baseline, screenshots)
    
    # Test WITH demand-driven OCR
    tracker_optimized = MarketTracker(debug=False)
    optimized_stats = run_replay_session(tracker_optimized, screenshots)
    
    # Compare OCR counts
    baseline_ocr = sum(baseline_stats['roi']['ocr'] for roi in baseline_stats['roi'])
    optimized_ocr = sum(optimized_stats['roi']['ocr'] for roi in optimized_stats['roi'])
    
    reduction_pct = ((baseline_ocr - optimized_ocr) / baseline_ocr) * 100
    
    print(f"OCR Reduction: {reduction_pct:.1f}% ({baseline_ocr} → {optimized_ocr})")
    
    # Erwartung: Mindestens 40% Reduktion
    assert reduction_pct >= 40.0
    
    # Transaktionen müssen identisch sein
    assert baseline_stats['transactions'] == optimized_stats['transactions']
```

### Benchmark-Skript

**scripts/perf/benchmark_roi_usage.py:**

```python
#!/usr/bin/env python3
"""
Benchmark: ROI-Usage Optimierung durch Demand-Driven OCR.

Misst OCR-Aufrufe pro ROI in einer simulierten Tracking-Session.
Vergleicht Vorher/Nachher-Metriken.
"""

import time
from pathlib import Path
from tracker import MarketTracker

def benchmark_roi_usage():
    """Run benchmark comparing baseline vs optimized ROI-OCR."""
    
    print("=" * 80)
    print("ROI-USAGE BENCHMARK")
    print("=" * 80)
    
    # Load test screenshots
    test_cases = [
        ('Overview mit Transaktionen', 'dev-screenshots/windows/buy_overview_001.png'),
        ('Detail-Window Burst', 'dev-screenshots/windows/buy_item_burst_*.png'),
        ('Relist-Szenario', 'dev-screenshots/windows/sell_item_relist_*.png')
    ]
    
    results = {}
    
    for test_name, pattern in test_cases:
        print(f"\n[TEST] {test_name}")
        print("-" * 80)
        
        # Run with demand-driven OCR
        tracker = MarketTracker(debug=False)
        
        # Simulate tracking session
        screenshots = sorted(Path().glob(pattern))
        start = time.perf_counter()
        
        for screenshot in screenshots:
            # ... simulate scan ...
            pass
        
        elapsed = time.perf_counter() - start
        stats = tracker.get_roi_usage_summary()
        
        # Print results
        print(f"Duration: {elapsed:.2f}s")
        print(f"Total Scans: {stats['scans_total']}")
        print(f"\nROI-Usage:")
        
        for roi_name in ['label', 'log', 'metrics', 'detail_balance', 'detail_warehouse']:
            roi_stats = stats[roi_name]
            if roi_stats['total_activations'] > 0:
                print(f"  {roi_name:20s}: OCR={roi_stats['ocr']:3d} ({roi_stats['ocr_rate']:5.1f}%), "
                      f"Cache={roi_stats['cache']:3d} ({roi_stats['cache_rate']:5.1f}%), "
                      f"Skip={roi_stats['skipped']:3d} ({roi_stats['skip_rate']:5.1f}%)")
        
        results[test_name] = stats
    
    # Summary
    print("\n" + "=" * 80)
    print("ZUSAMMENFASSUNG")
    print("=" * 80)
    
    total_ocr_calls = sum(
        sum(stats[roi]['ocr'] for roi in ['label', 'log', 'metrics', 'detail_balance', 'detail_warehouse'])
        for stats in results.values()
    )
    
    total_skips = sum(
        sum(stats[roi]['skipped'] for roi in ['label', 'log', 'metrics', 'detail_balance', 'detail_warehouse'])
        for stats in results.values()
    )
    
    print(f"Gesamt-OCR-Aufrufe: {total_ocr_calls}")
    print(f"Gesamt-Skips: {total_skips}")
    print(f"Einsparung: {(total_skips / (total_ocr_calls + total_skips)) * 100:.1f}%")

if __name__ == '__main__':
    benchmark_roi_usage()
```

## 🚀 Rollout-Strategie

### Phase 1: Flags + Logging (Woche 1)
**Änderungen:**
- Flag-System in `__init__` hinzufügen
- Helper-Methoden implementieren (`_set_need_flag`, `_schedule_metrics_refresh`, `_set_detail_metric_state`)
- ROI-Usage-Tracking in `_scan_region` einbauen
- Debug-Logs für alle Flag-Änderungen

**Verhalten:**
- ✅ Keine funktionalen Änderungen
- ✅ Flags werden gesetzt aber (noch) nicht ausgewertet
- ✅ OCR-Verhalten bleibt identisch

**Tests:**
- Unit-Tests für Helper-Methoden
- Manuelles Testen mit Debug-Logs
- Verifizieren dass Flags korrekt gesetzt werden

**Risiko:** 🟢 Minimal (nur Logging-Overhead)

### Phase 2: Metrics-Fallback (Woche 2)
**Änderungen:**
- Metrics-ROI-OCR an `_needs_metrics_text` koppeln
- Set-Logic in UI-Inferenz (Line 6350+) implementieren
- Set-Logic bei Fensterwechsel (Line 4907) implementieren
- Reset-Logic nach erfolgreichem Metrics-OCR

**Verhalten:**
- ✅ Metrics-OCR wird nur bei Bedarf ausgeführt
- ✅ UI-Inferenz funktioniert weiterhin
- ⚠️ Möglicherweise weniger Metrics-Scans → Logs prüfen

**Tests:**
- `test_placed_with_ui_deltas_triggers_metrics_ocr`
- `test_overview_with_transactions_log_active_metrics_inactive`
- Replay-Tests mit UI-Inferenz-Szenarien
- Manuelle Tests: Buy-Overview mit Relist-Pattern

**Risiko:** 🟡 Mittel (UI-Inferenz könnte fehlschlagen wenn Flag-Logic falsch)

**Rollback-Plan:**
```python
# Fallback: Metrics IMMER bei Overview-Fenstern
if wtype in ("sell_overview", "buy_overview"):
    self._needs_metrics_text = True
```

### Phase 3: Detail-State-Machine (Woche 3)
**Änderungen:**
- Detail-Metric-State-Machine implementieren (idle/baseline/delta)
- Balance/Warehouse-ROI an Flags koppeln
- State-Transitions in `_monitor_detail_window` integrieren
- Rolling-Baseline-Updates mit Flag-Management

**Verhalten:**
- ✅ Detail-Balance/Warehouse nur bei Baseline + Burst-Scans
- ✅ Delta-Monitoring wird reaktiver (weniger kontinuierliches OCR)
- ⚠️ Kritisch: Detail-Window-Transaktionen dürfen NICHT verloren gehen

**Tests:**
- `test_detail_burst_no_transaction_minimal_ocr`
- Replay-Tests mit Detail-Window-Sessions
- Manuelle Tests: Sofort-Käufe, Multi-Buy-Sessions, Timeouts
- **KRITISCH:** Birch-Sap-Szenario (SOFORT-Kauf nach Window-Open)

**Risiko:** 🔴 Hoch (Detail-Window-Transaktionen sind kritisch)

**Monitoring:**
```python
# Nach jedem Detail-Window-Exit: Log-Fallback-Check
if self._pending_log_fallback_txs:
    log_debug(f"[LOG-FALLBACK] {len(self._pending_log_fallback_txs)} missing transactions detected!")
```

**Rollback-Plan:**
```python
# Fallback: Detail-ROIs IMMER aktiv während Detail-Window
if detail_window_detected:
    self._needs_detail_balance = True
    self._needs_detail_warehouse = True
```

### Phase 4: Preorder-Inputs-Entkopplung (Woche 4 - Optional)
**Änderungen:**
- Input-ROI-OCR an `_needs_detail_inputs` koppeln
- Set-Logic in `_detect_preorder_placement`
- Cache-basierter Fallback in `_extract_preorder_input_fields`

**Verhalten:**
- ✅ Input-ROI nur bei Preorder/Listing-Detection
- ✅ Cache-Nutzung für wiederholte Zugriffe

**Tests:**
- Relist-Detection-Tests
- Preorder-Placement-Tests

**Risiko:** 🟡 Mittel (Relist-Detection könnte betroffen sein)

## 📊 Erwartete Performance-Verbesserungen

### Baseline-Messungen (Aktuell)

**Scan-Profil (Overview-Fenster):**
- Label-OCR: 56.5ms (immer)
- Log-OCR: 151.3ms (immer bei Overview)
- Metrics-OCR: 186.0ms (nur bei Refresh, ~alle 5s)
- **Gesamt:** ~207.8ms/Scan (ohne Metrics), ~393.8ms/Scan (mit Metrics)

**Detail-Window-Burst (30s @ 80ms Polling):**
- Scans: ~375 Scans (30s / 0.08s)
- Pro Scan: Label (56.5ms) + Balance (18.1ms) + Warehouse (18.0ms) + Item-Name (20.2ms, nur 1x)
- **Gesamt:** ~112.8ms/Scan × 375 = 42.3 Sekunden OCR-Zeit

### Projizierte Verbesserungen

**Overview-Fenster:**
- Log-OCR: 50% Reduktion (nur bei neuen Einträgen, nicht bei statischen Screens)
- Metrics-OCR: 80% Reduktion (nur bei UI-Inferenz-Bedarf, ~5% der Scans)
- **Einsparung:** ~150ms/Scan bei statischen Screens

**Detail-Window-Burst:**
- Balance/Warehouse: 95% Reduktion (nur 1x Baseline + 5-10 Deltas statt 375x)
- Pro Burst: ~20 OCR-Scans statt 375
- **Einsparung:** ~355 Scans × 36.1ms = 12.8 Sekunden

**Session-Gesamteinsparung:**
- 10 Min Tracking, 5 Detail-Window-Sessions, 500 Overview-Scans
- Vorher: 500×207.8ms + 5×42.3s = 315 Sekunden OCR
- Nachher: 500×150ms + 5×4.5s = 97 Sekunden OCR
- **Reduktion: 69% (~218 Sekunden gespart)**

## ⚠️ Risiken & Mitigations

### Risiko 1: Detail-Window-Transaktionen verloren

**Symptom:** Birch-Sap-Scenario (SOFORT-Kauf) wird nicht mehr erkannt.

**Ursache:** Balance/Warehouse-OCR wird übersprungen weil Flag nicht gesetzt.

**Mitigation:**
```python
# Safeguard: Bei Detail-Window-Entry IMMER mindestens 1x OCR
if not self._detail_window_active and detail_window_detected:
    # Force Flags für ersten Scan (Baseline)
    self._needs_detail_balance = True
    self._needs_detail_warehouse = True
    
# Log-Fallback bleibt aktiv
if self._pending_log_fallback_txs:
    log_debug(f"[SAFETY] Log-Fallback detected {len(self._pending_log_fallback_txs)} missing txs")
```

### Risiko 2: UI-Inferenz schlägt fehl

**Symptom:** Relist-Pattern wird nicht erkannt (placed-only ohne UI-Deltas).

**Ursache:** Metrics-Flag nicht gesetzt weil placed-Entry falsch klassifiziert.

**Mitigation:**
```python
# Fallback: Bei placed/withdrew/listed IMMER Metrics-Refresh anfordern
if entry_type in ('placed', 'withdrew', 'listed'):
    self._schedule_metrics_refresh(reason=f"Placed/Withdrew/Listed entry: {item_name}")
```

### Risiko 3: Flag-Reset zu früh

**Symptom:** Flags werden zurückgesetzt bevor OCR laufen konnte.

**Ursache:** Race-Condition zwischen Set und Reset.

**Mitigation:**
```python
# Flag NUR zurücksetzen nach ERFOLGREICHEM OCR
if ocr_text and len(ocr_text) > 3:  # Mindestens 3 Zeichen
    self._set_need_flag('log_text', False, "OCR successful")
else:
    # OCR failed → Flag NICHT zurücksetzen (Retry nächster Scan)
    log_debug(f"[ROI-FLAG] log_text: OCR failed, keeping flag=True for retry")
```

### Risiko 4: Performance-Regression

**Symptom:** System ist langsamer als vorher trotz weniger OCR-Calls.

**Ursache:** Flag-Management-Overhead höher als eingesparte OCR-Zeit.

**Mitigation:**
```python
# Profiling mit cProfile
import cProfile
profiler = cProfile.Profile()
profiler.enable()
# ... tracking session ...
profiler.disable()
profiler.print_stats(sort='cumtime')

# Flag-Updates batchen statt einzeln
flag_updates = []
# ... sammle updates ...
for flag_name, value, reason in flag_updates:
    self._set_need_flag(flag_name, value, reason)
```

## 📝 Dokumentations-Updates

### AGENTS.md Updates

```markdown
## ROI-OCR: Bedarfsgesteuerte Ausführung

- **Flag-System**: Jede ROI hat ein Need-Flag (`_needs_log_text`, `_needs_metrics_text`, etc.)
- **Verbraucher**: Detail-Delta-Monitoring, UI-Inferenz, Preorder/Listing-Detection setzen Flags
- **Scan-Logik**: OCR wird nur ausgeführt wenn Flag=True UND ROI geändert
- **Cache-First**: Bei ROI unverändert wird Cache verwendet, Flag wird trotzdem zurückgesetzt
- **State-Machine**: Detail-Window hat 3 States (idle/baseline/delta) die Flags steuern
- **Instrumentation**: `_roi_usage_last_scan` und `_roi_usage_session_stats` für Monitoring
```

### Code-Kommentare

Jede Flag-bezogene Code-Stelle erhält ausführliche Kommentare:

```python
# === BEDARFSGESTEUERTE ROI-OCR ===
# Dieses Flag steuert ob Log-ROI-OCR ausgeführt wird.
# 
# GESETZT VON:
#   - process_ocr_text (bei Overview-Fenster)
# 
# VERWENDET VON:
#   - _scan_region (Line 620+) → Skip Log-OCR wenn False
# 
# ZURÜCKGESETZT:
#   - Nach erfolgreichem Log-OCR
#   - NICHT bei Cache-Hit (Flag bleibt True für nächsten Scan)
# 
# RATIONALE:
#   Log-Text ändert sich nur bei neuen Transaktionen.
#   Bei statischen Screens (keine Scroll, keine neuen Einträge)
#   kann Log-OCR übersprungen werden → 151ms Einsparung.
```

## ✅ Akzeptanzkriterien

### Muss-Kriterien (Blocker für Merge)

1. ✅ **Keine verlorenen Transaktionen**
   - Alle existierenden Tests müssen passieren
   - Manual-Tests mit dev-screenshots zeigen identische Ergebnisse
   - Log-Fallback erkennt fehlende Detail-Window-Transaktionen

2. ✅ **Performance-Verbesserung messbar**
   - Benchmark zeigt ≥40% Reduktion der OCR-Aufrufe
   - Session-Test zeigt ≥30% Reduktion der Gesamt-OCR-Zeit
   - Keine Regression bei Scan-Intervall-Timing

3. ✅ **Flag-System funktioniert korrekt**
   - Unit-Tests für alle Helper-Methoden passieren
   - Debug-Logs zeigen konsistente Flag-Transitions
   - Keine Stuck-States (Flags die nie zurückgesetzt werden)

4. ✅ **Detail-Window-Transaktionen robust**
   - Birch-Sap-Test (SOFORT-Kauf) passiert
   - Multi-Buy-Test (5x schnelle Käufe) passiert
   - Relist-Detection funktioniert

### Soll-Kriterien (Nice-to-have)

1. 🎯 **Instrumentation vollständig**
   - ROI-Usage-Summary zeigt detaillierte Statistiken
   - Benchmark-Skript erzeugt vergleichbare Metriken
   - GUI zeigt ROI-Usage-Statistik (optional)

2. 🎯 **Code-Qualität**
   - Alle Helper-Methoden haben Docstrings
   - Flag-bezogene Code-Stellen haben Kommentare
   - AGENTS.md reflektiert neue Architektur

3. 🎯 **User-Experience**
   - Keine spürbaren Verzögerungen bei Detail-Window-Entry
   - Transaktionen werden weiterhin in <100ms erkannt
   - Debug-Logs sind verständlich für Troubleshooting

## 🔄 Rollback-Procedure

Falls kritische Issues in Production auftreten:

### Stufe 1: Flag-Override (Hot-Fix)

```python
# In config.py
FORCE_ALL_ROI_OCR = True  # Deaktiviert Demand-Driven OCR

# In tracker.py __init__
if FORCE_ALL_ROI_OCR:
    self._needs_log_text = True
    self._needs_metrics_text = True
    self._needs_detail_balance = True
    self._needs_detail_warehouse = True
    self._needs_detail_inputs = True
```

### Stufe 2: Feature-Toggle (Config)

```python
# config.py
USE_DEMAND_DRIVEN_ROI_OCR = False

# tracker.py
if not USE_DEMAND_DRIVEN_ROI_OCR:
    # Use legacy always-on OCR logic
    skip_log_ocr = detail_window_detected  # Old behavior
    refresh_metrics = self._pending_metrics_refresh  # Old behavior
```

### Stufe 3: Branch-Revert (Git)

```bash
# Revert to previous stable branch
git revert <commit-hash-of-demand-driven-ocr>
git push origin feature/detail-window-capture
```

## 📅 Zeitplan

| Phase | Dauer | Tasks | Milestone |
|-------|-------|-------|-----------|
| **Phase 1** | 3 Tage | Flag-System + Logging | Merge PR #1 |
| **Phase 2** | 4 Tage | Metrics-Fallback | Merge PR #2 |
| **Phase 3** | 5 Tage | Detail-State-Machine | Merge PR #3 |
| **Phase 4** | 3 Tage | Preorder-Inputs | Merge PR #4 |
| **Testing** | 2 Tage | Integrations-Tests, Manual-QA | QA-Approval |
| **Docs** | 1 Tag | AGENTS.md, Code-Kommentare | Release Ready |
| **Total** | **18 Tage** | | **v1.0-demand-roi** |

## 🎓 Lessons Learned (für zukünftige Optimierungen)

1. **Cache-First ist besser als Skip-First**
   - Auch wenn Flag=False sollte Cache verfügbar bleiben
   - ROI-Signature-Diffing ergänzt Flags (kein Ersatz)

2. **State-Machines für komplexe Logik**
   - Detail-Window-State (idle/baseline/delta) vereinfacht Flag-Management
   - Explizite States sind besser als implizite Boolean-Kombinationen

3. **Instrumentation von Anfang an**
   - ROI-Usage-Tracking hilft bei Debugging und Optimierung
   - Session-Statistiken zeigen reale Performance-Impacts

4. **Rollout in kleinen Schritten**
   - Phase 1 (Logging only) verhindert Breaking-Changes
   - Jede Phase hat eigenen PR → Einfacher Rollback

5. **Safety-Nets beibehalten**
   - Log-Fallback bleibt aktiv auch mit Demand-Driven OCR
   - Plausibility-Checks dürfen nicht deaktiviert werden

---

**Status:** ✅ Ready for Implementation  
**Nächster Schritt:** Phase 1 - Flag-System + Logging implementieren  
**Verantwortlich:** Development Team  
**Review:** Tech Lead + QA Team
### 2.3 Detail-State-Machine abschließen

* Beim Eintritt in ein Detailfenster (`prev_window != wtype` und `wtype in ("buy_item", "sell_item")`) → `_set_detail_metric_state("baseline", "window_transition")`.  
* Sobald Baseline-Werte erfolgreich gesetzt wurden → `_set_detail_metric_state("delta", "baseline_captured")`.  
* Nach jeder erfolgreich gespeicherten Transaktion oder wenn `_detail_confirmation_timeout` triggert → `_set_detail_metric_state("idle", "transaction_committed" bzw. "timeout")`.  
* Wird das Detailfenster verlassen (`wtype` wechselt zurück zu Overview) → `_set_detail_metric_state("idle", "detail_exit")` und `_needs_log_text` wieder aktivieren.  
Diese Übergänge sind zwingend, damit Balance/Warehouse-OCR nicht dauerhaft läuft.
### 2.4 Preorder-/Listing-Inputs koppeln

* `_needs_detail_inputs` bleibt `False`, bis `_monitor_detail_window` im Relist-Kontext feststellt, dass `_detect_preorder_placement` bzw. `_detect_listing_placement` laufen muss (z. B. nach erkanntem Relist-Pattern oder wenn `_detail_cached_input_fields` leer ist).  
* Die Input-ROI (`_extract_preorder_input_fields`) prüft das Flag; wenn `False`, liefert sie sofort das gecachte Ergebnis zurück. Sobald OCR erfolgreich läuft, setzt sie das Flag wieder auf `False`.  
* Bei Sell-Detailfenstern wird das Flag gar nicht erst gesetzt, sofern kein Listing-Relist vorliegt.
## 3. Tests, Instrumentation & Rollout

1. **ROI-Usage-Logging:** Nach jedem Scan schreibt `_roi_usage_last_scan` eine Zeile wie  
   `Scan#842 label=ocr log=cache metrics=skipped detail_balance=ocr detail_warehouse=ocr inputs=skipped`. Bei aktivem Debug-Mode erscheint dies im Log; zusätzlich kann ein CLI-Flag (`--roi-usage`) die Statistik sichern.

2. **Automatisierte Tests / Replays:**  
   - *Detail-Burst ohne Transaktion*: Simulierter Video-Frame-Feed (netcdf oder Mock) stellt sicher, dass Balance/Warehouse nur beim Baseline-Scan OCR ausführen.  
   - *UI-Fallback-Szenario*: Log enthält ausschließlich `placed`, UI zeigt `ordersCompleted` Delta → `_needs_metrics_text` wird genau einmal auf `True` gesetzt und nach dem synthetischen `collect_ui_inferred` wieder `False`.  
   - *Normale Overview-Transaktionen*: Während kontinuierlicher Käufe bleibt `_needs_metrics_text=False`, `_needs_log_text=True`.  
   Diese Tests können als Replay-Skripte unter `tests/manual/roi_demand/` liegen.

3. **Rollout in Etappen:**  
   - **Phase 1**: Flags + Logging ohne Verhaltensänderung (A/B-Vergleich via `roi_usage`).  
   - **Phase 2**: Metrics-Fallback aktivieren, Detail-State-Machine verkabeln.  
   - **Phase 3**: Feintuning (Detail-Inputs, Preorder/Listing).  
   Nach jeder Phase Replay-Läufe (z. B. Trace of Nature Relist, Magical Shard Listing) durchführen und `roi_usage`-Messwerte dokumentieren.
