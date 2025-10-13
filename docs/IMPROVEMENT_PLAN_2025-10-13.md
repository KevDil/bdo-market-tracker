# Market Tracker - Verbesserungsplan 2025-10-13

**Status:** 27/29 Tests bestehen (93% Pass-Rate)  
**Version:** 0.2.4 Beta  
**Datum:** 2025-10-13

---

## 🎯 Executive Summary

Das Projekt ist in sehr gutem Zustand mit 93% Testabdeckung und stabiler Kernfunktionalität. 
Die Hauptverbesserungsbereiche sind:
1. 2 fehlgeschlagene Tests beheben
2. Performance-Optimierung (Cache, Async Pipeline)
3. Code-Qualität & Wartbarkeit verbessern
4. Robustheit & Error-Handling erhöhen

---

## 🐛 P0: Kritische Bugfixes

### Bug #1: test_fast_action_timing - Lion Blood nicht getrackt
**Status:** ❌ FAIL  
**Impact:** 🔴 Hoch - Schnelle Transaktionen gehen verloren  
**Aufwand:** 2-3 Stunden  
**Risiko:** Niedrig

**Problem:**
```
❌ Lion Blood NOT tracked!
   This is the bug we're trying to fix.

✅ Grim Reaper's Elixir tracked (128x @ 26,752,000)
```

**Root Cause Analysis:**
- Transaktion verschwindet zu schnell aus dem Transaction-Log
- Poll-Interval (0.3s) ist möglicherweise zu langsam
- Window-Übergang (buy_item → buy_overview) erfolgt zu schnell

**Fix-Strategie:**
1. Burst-Modus bei Window-Übergang aktivieren (bereits im Code vorhanden!)
2. `_request_immediate_rescan` Mechanismus nutzen
3. Poll-Interval temporär auf 0.1s reduzieren nach erkannter Aktion

**Code-Änderungen:**
- `tracker.py`: Burst-Modus reaktivieren
- `tracker.py`: Window-Change-Detection verbessern

**Testing:**
```bash
python scripts/test_fast_action_timing.py
```

---

### Bug #2: test_historical_placed_with_ui_overview - Fehlende Transaktionen
**Status:** ❌ FAIL  
**Impact:** 🔴 Hoch - Multi-Item-Szenarien unvollständig  
**Aufwand:** 2-4 Stunden  
**Risiko:** Niedrig

**Problem:**
```
❌ Erwartete 2 Transaktionen, gefunden: 1
   - 25x Sealed Black Magic Crystal für 70,250,000.0 Silver
```

**Root Cause Analysis:**
- Parsing-Logik erkennt nicht beide Events im selben OCR-Text
- Mögliche Ursache: Timestamp-Cluster-Zuordnung fehlerhaft
- Alternative: Zweites Event wird als Duplikat gefiltert

**Fix-Strategie:**
1. Test-Input analysieren: Was wird erwartet?
2. OCR-Text-Splitting in `split_text_into_log_entries()` debuggen
3. Event-Anker-Detection verbessern
4. Duplikats-Filter überprüfen

**Code-Änderungen:**
- `parsing.py`: `split_text_into_log_entries()`
- `tracker.py`: Duplikats-Detection

**Testing:**
```bash
python scripts/test_historical_placed_with_ui_overview.py
```

---

## ⚡ P1: Performance-Optimierungen (Quick Wins)

### Opt #1: Screenshot-Cache optimieren
**Impact:** 🟢 Hoch (20-30% Performance-Gewinn)  
**Aufwand:** 30 Minuten  
**Risiko:** Niedrig

**Aktuell:**
```python
CACHE_TTL = 2.0  # Sekunden
MAX_CACHE_SIZE = 10
# Cache-Hit-Rate: ~50%
```

**Verbesserung:**
```python
CACHE_TTL = 5.0  # Market-Window ändert sich selten
MAX_CACHE_SIZE = 20  # Mehr Screenshots im Cache
# Erwartete Cache-Hit-Rate: >70%
```

**Datei:** `utils.py` (Zeilen 40-41)

---

### Opt #2: BDO API Retry-Logik
**Impact:** 🟡 Mittel (Robustheit bei Netzwerkfehlern)  
**Aufwand:** 1 Stunde  
**Risiko:** Niedrig

**Aktuell:**
```python
if response.status_code != 200:
    print(f"⚠️  API returned status {response.status_code}")
    return None
```

**Verbesserung:**
```python
import time
from functools import wraps

def retry_with_backoff(max_retries=3, backoff_factor=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    result = func(*args, **kwargs)
                    if result is not None:
                        return result
                except requests.RequestException as e:
                    if attempt == max_retries - 1:
                        raise
                    wait_time = backoff_factor ** attempt
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator

@retry_with_backoff(max_retries=3, backoff_factor=1.5)
def get_item_price_range(item_id: str, use_cache: bool = True):
    # ... existing code ...
```

**Datei:** `bdo_api_client.py`

---

### Opt #3: Focus-Detection optimieren
**Impact:** 🟡 Mittel (Weniger CPU-Overhead)  
**Aufwand:** 15 Minuten  
**Risiko:** Niedrig

**Problem:**
```python
def _get_foreground_window_title_windows() -> str:
    try:
        import ctypes  # ❌ Import bei jedem Aufruf!
```

**Fix:**
```python
# Am Anfang von utils.py
import ctypes
from ctypes import wintypes

def _get_foreground_window_title_windows() -> str:
    # ... ohne try/import ...
```

**Datei:** `utils.py` (Zeilen 75-80)

---

## 🔧 P2: Code-Qualität & Wartbarkeit

### Quality #1: Exception-Handling verbessern
**Impact:** 🟡 Mittel (Besseres Debugging)  
**Aufwand:** 2-3 Stunden  
**Risiko:** Niedrig

**Problem:**
```python
except Exception:  # ❌ Zu generisch!
    return False
```

**Lösung:**
```python
except (sqlite3.DatabaseError, ValueError) as e:
    log_debug(f"[DB] Error updating timestamp: {e}")
    return False
except Exception as e:
    log_debug(f"[DB] Unexpected error: {e}", exc_info=True)
    return False
```

**Betroffene Dateien:**
- `database.py` (10+ Stellen)
- `tracker.py` (5+ Stellen)
- `utils.py` (3+ Stellen)

**Systematisches Vorgehen:**
1. `grep -n "except Exception:" *.py` ausführen
2. Jede Stelle analysieren: Welche spezifischen Exceptions?
3. Logging hinzufügen
4. Exception-Kette beibehalten (`from e`)

---

### Quality #2: Type-Hints vervollständigen
**Impact:** 🟡 Mittel (Bessere IDE-Unterstützung)  
**Aufwand:** 3-4 Stunden  
**Risiko:** Niedrig

**Beispiele:**
```python
# Vorher
def _find_boundary_offset(patterns, text):
    """Return earliest match start position."""

# Nachher
def _find_boundary_offset(patterns: list[re.Pattern], text: str) -> Optional[int]:
    """Return earliest match start position across compiled patterns."""
```

**Priorität nach Datei:**
1. `parsing.py` - 20+ Funktionen ohne Type-Hints
2. `utils.py` - 15+ Funktionen
3. `tracker.py` - 10+ Funktionen
4. `database.py` - Bereits gut (nur 5 Stellen)

**Validation:**
```bash
pip install mypy
mypy --strict parsing.py
```

---

### Quality #3: Magic Numbers eliminieren
**Impact:** 🟢 Niedrig (Bessere Lesbarkeit)  
**Aufwand:** 1 Stunde  
**Risiko:** Sehr niedrig

**Beispiele:**
```python
# parsing.py
MAX_EVENT_LENGTH = 300  # Max characters per log entry
event_end = anchor_end + MAX_EVENT_LENGTH

# utils.py
LOG_ROTATION_SIZE_MB = 10
SCREENSHOT_ROI_TOP_PERCENT = 0.3

# tracker.py
WINDOW_HISTORY_SIZE = 5
SEEN_TX_SIGNATURES_MAX = 1000
ERROR_DECAY_RATE = 1  # Errors decrease by 1 per successful scan
```

**Datei:** Neue `constants.py` erstellen oder in `config.py` einfügen

---

## 🛡️ P2: Stabilität & Robustheit

### Stab #1: Memory-Leak-Prevention für Caches
**Impact:** 🟡 Mittel (Langzeit-Stabilität)  
**Aufwand:** 1-2 Stunden  
**Risiko:** Niedrig

**Problem:**
```python
self._unit_price_cache = {}  # ❌ Unbegrenztes Wachstum!
self._missing_price_items = set()  # ❌ Unbegrenztes Wachstum!
```

**Lösung 1: LRU-Cache**
```python
from functools import lru_cache

@lru_cache(maxsize=500)
def check_price_plausibility_cached(item_name: str, unit_price: float, quantity: int):
    return check_price_plausibility(item_name, unit_price, quantity)
```

**Lösung 2: TTL-basierter Cache**
```python
from collections import OrderedDict
import time

class TTLCache:
    def __init__(self, maxsize=500, ttl=3600):
        self.cache = OrderedDict()
        self.maxsize = maxsize
        self.ttl = ttl
    
    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        if len(self.cache) >= self.maxsize:
            self.cache.popitem(last=False)
        self.cache[key] = (value, time.time())
```

**Dateien:** `tracker.py`, `utils.py`

---

### Stab #2: Window Focus Race Condition
**Impact:** 🟡 Mittel (Verhindert fehlerhafte Scans)  
**Aufwand:** 1 Stunde  
**Risiko:** Niedrig

**Problem:**
- Bei schnellem Alt+Tab kann Scan während Fensterübergang erfolgen
- OCR-Text ist dann inkonsistent (Mix aus zwei Windows)

**Lösung: Grace Period**
```python
FOCUS_GRACE_PERIOD_MS = 200  # Wait 200ms after focus change

def _capture_frame(self):
    if FOCUS_REQUIRED:
        is_focused, current_title = is_bdo_window_in_foreground(FOCUS_WINDOW_TITLES)
        
        # Track focus changes
        focus_changed = (self._last_focus_state != is_focused)
        if focus_changed:
            self._focus_change_time = time.time()
            log_debug(f"[FOCUS] Focus changed: {is_focused}")
        
        # Grace period after focus change
        if focus_changed and is_focused:
            time_since_change = (time.time() - self._focus_change_time) * 1000
            if time_since_change < FOCUS_GRACE_PERIOD_MS:
                return None  # Skip scan during grace period
        
        if not is_focused:
            # ... existing code ...
```

**Datei:** `tracker.py` (Zeilen 154-168)

---

### Stab #3: Database-Backup-Strategie
**Impact:** 🟢 Niedrig (Datensicherheit)  
**Aufwand:** 2 Stunden  
**Risiko:** Niedrig

**Aktuell:** README erwähnt `backups/`, aber kein automatisches Backup

**Implementierung:**
```python
import shutil
from pathlib import Path
import datetime

def backup_database(db_path: str, backup_dir: str = "backups"):
    """Create timestamped backup of database."""
    Path(backup_dir).mkdir(exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{backup_dir}/bdo_tracker_{timestamp}.db"
    
    try:
        shutil.copy2(db_path, backup_path)
        log_debug(f"[BACKUP] Created: {backup_path}")
        
        # Keep only last 10 backups
        cleanup_old_backups(backup_dir, keep=10)
        return True
    except Exception as e:
        log_debug(f"[BACKUP] Failed: {e}")
        return False

def cleanup_old_backups(backup_dir: str, keep: int = 10):
    """Keep only N most recent backups."""
    backups = sorted(Path(backup_dir).glob("bdo_tracker_*.db"))
    for old_backup in backups[:-keep]:
        old_backup.unlink()
```

**Trigger-Punkte:**
1. Vor DB-Schema-Migrationen (in `database.py`)
2. Täglich beim ersten Start (`tracker.py`)
3. Manuell über GUI-Button

**Datei:** Neue `backup.py` + Integration in `database.py` und `gui.py`

---

## 📊 P2: Monitoring & Observability

### Mon #1: Strukturiertes Logging einführen
**Impact:** 🟡 Mittel (Bessere Analyse)  
**Aufwand:** 3-4 Stunden  
**Risiko:** Mittel (Breaking Change)

**Aktuell:**
- Mix aus `print()`, `log_debug()`, `log_text()`
- Keine Log-Levels
- Keine strukturierten Metadaten

**Ziel:**
```python
import logging
from logging.handlers import RotatingFileHandler

# Setup
logger = logging.getLogger('market_tracker')
logger.setLevel(logging.DEBUG)

# Console Handler (nur INFO+)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s'
))
logger.addHandler(console_handler)

# File Handler (alles, mit Rotation)
file_handler = RotatingFileHandler(
    'market_tracker.log',
    maxBytes=10*1024*1024,  # 10 MB
    backupCount=5
)
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s'
))
logger.addHandler(file_handler)

# Usage
logger.debug("[OCR] Text extracted: %s chars", len(text))
logger.info("[SCAN] Transaction detected: %s", tx_summary)
logger.warning("[PRICE] Plausibility check failed: %s", item_name)
logger.error("[DB] Failed to save transaction: %s", exc)
```

**Migration-Strategie:**
1. Phase 1: Neues Logging-System parallel einführen
2. Phase 2: Alle `log_debug()` → `logger.debug()`
3. Phase 3: Alle `print()` → entsprechendes Level
4. Phase 4: `log_text()` und `log_debug()` deprecaten

**Breaking Change:** Ja - Log-Format ändert sich

---

### Mon #2: Performance-Metriken sammeln
**Impact:** 🟢 Hoch (Datengetriebene Optimierung)  
**Aufwand:** 2-3 Stunden  
**Risiko:** Niedrig

**Neue Metriken:**
```python
class PerformanceMetrics:
    def __init__(self):
        self.ocr_times = deque(maxlen=100)
        self.scan_times = deque(maxlen=100)
        self.cache_hits = 0
        self.cache_misses = 0
        self.transactions_detected = 0
        self.api_calls = 0
        self.api_errors = 0
        self.start_time = time.time()
    
    def get_stats(self) -> dict:
        uptime = time.time() - self.start_time
        total_scans = len(self.scan_times)
        
        return {
            'uptime_seconds': uptime,
            'total_scans': total_scans,
            'scans_per_minute': (total_scans / uptime) * 60 if uptime > 0 else 0,
            'avg_scan_time_ms': statistics.mean(self.scan_times) if self.scan_times else 0,
            'avg_ocr_time_ms': statistics.mean(self.ocr_times) if self.ocr_times else 0,
            'cache_hit_rate': self.cache_hits / (self.cache_hits + self.cache_misses) if (self.cache_hits + self.cache_misses) > 0 else 0,
            'transactions_detected': self.transactions_detected,
            'api_success_rate': 1 - (self.api_errors / self.api_calls) if self.api_calls > 0 else 1,
        }
```

**GUI-Integration:**
```python
# Neuer Tab in GUI: "Performance"
def show_performance_stats():
    stats = tracker.metrics.get_stats()
    
    stats_text = f"""
    ⏱️  Uptime: {stats['uptime_seconds']:.0f}s
    📊 Total Scans: {stats['total_scans']}
    ⚡ Scans/Min: {stats['scans_per_minute']:.1f}
    🕐 Avg Scan Time: {stats['avg_scan_time_ms']:.1f}ms
    🔍 Avg OCR Time: {stats['avg_ocr_time_ms']:.1f}ms
    💾 Cache Hit Rate: {stats['cache_hit_rate']*100:.1f}%
    📦 Transactions: {stats['transactions_detected']}
    🌐 API Success: {stats['api_success_rate']*100:.1f}%
    """
    
    messagebox.showinfo("Performance Stats", stats_text)
```

**Datei:** Neue `metrics.py` + Integration in `tracker.py` und `gui.py`

---

## 🎨 P3: GUI-Verbesserungen

### GUI #1: Error-Display verbessern
**Impact:** 🟡 Mittel (Bessere UX)  
**Aufwand:** 1-2 Stunden  
**Risiko:** Niedrig

**Aktuell:**
- Nur Farbindikatoren (🟢🟡🔴)
- Keine Details zu Fehlern

**Verbesserung:**
```python
# Tooltip bei Hover über Health-Status
def show_error_tooltip(event):
    if tracker.error_count > 0:
        tooltip = tk.Toplevel()
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
        
        error_info = f"""
        Errors: {tracker.error_count}
        Last Error: {tracker.last_error_message}
        Time: {tracker.last_error_time.strftime('%H:%M:%S')}
        """
        
        label = tk.Label(tooltip, text=error_info, bg="lightyellow", relief="solid", borderwidth=1)
        label.pack()
        
        # Auto-close after 3 seconds
        tooltip.after(3000, tooltip.destroy)

health_label.bind("<Enter>", show_error_tooltip)

# "Show Errors" Button
def show_error_log():
    # Öffne ocr_log.txt und zeige letzte 50 Zeilen mit [ERROR]
    try:
        with open(LOG_PATH, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        error_lines = [line for line in lines if '[ERROR]' in line][-50:]
        
        error_window = tk.Toplevel(root)
        error_window.title("Error Log")
        error_window.geometry("800x400")
        
        text_widget = tk.Text(error_window, wrap='word')
        text_widget.pack(fill='both', expand=True)
        text_widget.insert('1.0', ''.join(error_lines))
        text_widget.config(state='disabled')
    except Exception as e:
        messagebox.showerror("Error", f"Failed to load error log: {e}")

tk.Button(root, text="Show Errors", command=show_error_log).pack(pady=2)
```

**Datei:** `gui.py`

---

### GUI #2: Config-GUI hinzufügen
**Impact:** 🟢 Niedrig (Convenience)  
**Aufwand:** 4-6 Stunden  
**Risiko:** Niedrig

**Features:**
```python
def open_settings():
    settings_window = tk.Toplevel(root)
    settings_window.title("Settings")
    settings_window.geometry("400x500")
    
    # Poll Interval
    tk.Label(settings_window, text="Poll Interval (seconds):").pack()
    poll_var = tk.DoubleVar(value=tracker.poll_interval)
    tk.Scale(settings_window, from_=0.1, to=2.0, resolution=0.1, 
             orient='horizontal', variable=poll_var).pack()
    
    # GPU Toggle
    gpu_var = tk.BooleanVar(value=USE_GPU)
    tk.Checkbutton(settings_window, text="Use GPU Acceleration", 
                   variable=gpu_var).pack()
    
    # Cache Size
    tk.Label(settings_window, text="Screenshot Cache Size:").pack()
    cache_var = tk.IntVar(value=MAX_CACHE_SIZE)
    tk.Scale(settings_window, from_=5, to=50, resolution=5, 
             orient='horizontal', variable=cache_var).pack()
    
    # Debug Mode
    debug_var = tk.BooleanVar(value=tracker.debug)
    tk.Checkbutton(settings_window, text="Debug Mode", 
                   variable=debug_var).pack()
    
    def save_settings():
        tracker.poll_interval = poll_var.get()
        tracker.debug = debug_var.get()
        # Save to config file
        save_config_to_file({
            'POLL_INTERVAL': poll_var.get(),
            'USE_GPU': gpu_var.get(),
            'MAX_CACHE_SIZE': cache_var.get(),
        })
        messagebox.showinfo("Settings", "Settings saved! Restart required for some changes.")
        settings_window.destroy()
    
    tk.Button(settings_window, text="Save", command=save_settings).pack(pady=20)
    tk.Button(settings_window, text="Cancel", command=settings_window.destroy).pack()

tk.Button(root, text="Settings", command=open_settings).pack(pady=6)
```

**Zusätzlich:** Config-File-Handling
```python
import json

def load_config_from_file(path='config.json'):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_config_to_file(config, path='config.json'):
    with open(path, 'w') as f:
        json.dump(config, f, indent=2)
```

**Datei:** `gui.py` + neue `config.json`

---

## 🚀 P3: Advanced Features

### Feat #1: Async Pipeline vollständig aktivieren
**Impact:** 🟢 Hoch (30-50% schneller)  
**Aufwand:** 6-8 Stunden  
**Risiko:** Mittel

**Status:** Feature-Flag existiert, aber Code ist unvollständig

**Vorbereitete Infrastruktur:**
```python
# config.py
USE_ASYNC_PIPELINE = True
ASYNC_QUEUE_MAXSIZE = 3
ASYNC_WORKER_COUNT = 1

# tracker.py
self._async_controller = None  # Placeholder
```

**Implementierung:**
```python
import asyncio
from queue import Queue
from threading import Thread

class AsyncOCRController:
    def __init__(self, tracker, worker_count=1, queue_maxsize=3):
        self.tracker = tracker
        self.queue = Queue(maxsize=queue_maxsize)
        self.workers = []
        self.running = False
        
        for _ in range(worker_count):
            worker = Thread(target=self._worker_loop, daemon=True)
            self.workers.append(worker)
    
    def start(self):
        self.running = True
        for worker in self.workers:
            worker.start()
    
    def stop(self):
        self.running = False
        for _ in self.workers:
            self.queue.put(None)  # Poison pill
        for worker in self.workers:
            worker.join(timeout=1.0)
    
    def submit_frame(self, frame):
        """Non-blocking submit of screenshot for processing."""
        if not self.queue.full():
            self.queue.put(frame)
            return True
        return False
    
    def _worker_loop(self):
        """Worker thread processes frames from queue."""
        while self.running:
            try:
                frame = self.queue.get(timeout=0.5)
                if frame is None:  # Poison pill
                    break
                
                # Process frame
                self.tracker._process_image(frame, context='async', allow_debug=False)
                
            except Empty:
                continue
            except Exception as e:
                log_debug(f"[ASYNC] Worker error: {e}")

# In MarketTracker.__init__:
if USE_ASYNC_PIPELINE:
    self._async_controller = AsyncOCRController(
        self,
        worker_count=ASYNC_WORKER_COUNT,
        queue_maxsize=ASYNC_QUEUE_MAXSIZE
    )

# In auto_track():
if USE_ASYNC_PIPELINE and self._async_controller:
    self._async_controller.start()
    
    while self.running:
        frame = self._capture_frame()
        if frame is not None:
            submitted = self._async_controller.submit_frame(frame)
            if not submitted:
                log_debug("[ASYNC] Queue full, dropping frame")
        
        time.sleep(self._get_next_sleep_interval())
    
    self._async_controller.stop()
```

**Testing:**
1. A/B-Test: Sync vs Async mit gleicher Workload
2. Metriken: Throughput, Latenz, CPU-Auslastung
3. Edge-Cases: Burst-Szenarien, Queue-Overflow

**Risiken:**
- Race Conditions bei Shared State (`seen_tx_signatures`, `last_overview_text`)
- Memory-Overhead durch Queue
- Komplexere Debug-Szenarien

**Datei:** `tracker.py` + neue `async_pipeline.py`

---

## 📋 Implementation Roadmap

### Sprint 1: Bugfixes & Quick Wins (1 Woche)
- [ ] Bug #1: test_fast_action_timing
- [ ] Bug #2: test_historical_placed_with_ui_overview
- [ ] Opt #1: Screenshot-Cache optimieren
- [ ] Opt #2: BDO API Retry-Logik
- [ ] Opt #3: Focus-Detection optimieren

**Ziel:** 29/29 Tests grün, 15-20% Performance-Gewinn

---

### Sprint 2: Code-Qualität (1 Woche)
- [ ] Quality #1: Exception-Handling (Prio: database.py, tracker.py)
- [ ] Quality #2: Type-Hints (Prio: parsing.py, utils.py)
- [ ] Quality #3: Magic Numbers eliminieren
- [ ] Stab #1: Memory-Leak-Prevention

**Ziel:** Bessere Wartbarkeit, mypy --strict ready

---

### Sprint 3: Stabilität & Monitoring (1 Woche)
- [ ] Stab #2: Window Focus Race Condition
- [ ] Stab #3: Database-Backup-Strategie
- [ ] Mon #1: Strukturiertes Logging (Phase 1+2)
- [ ] Mon #2: Performance-Metriken

**Ziel:** Production-Ready Stability

---

### Sprint 4: GUI & UX (Optional, 1 Woche)
- [ ] GUI #1: Error-Display verbessern
- [ ] GUI #2: Config-GUI hinzufügen
- [ ] Mon #1: Logging (Phase 3+4 - Migration abschließen)

**Ziel:** Bessere User Experience

---

### Sprint 5: Advanced Features (Optional, 2 Wochen)
- [ ] Feat #1: Async Pipeline vollständig aktivieren
- [ ] Weitere Roadmap-Items aus README.md

**Ziel:** Next-Level Performance

---

## 📊 Success Metrics

### Performance
- ✅ 29/29 Tests grün (aktuell: 27/29)
- ✅ Scan-Rate: >100 scans/min (aktuell: ~99)
- ✅ Cache-Hit-Rate: >70% (aktuell: ~50%)
- ✅ Memory: Stabil <100MB (aktuell: ~80MB)
- ✅ API-Fehlerrate: <1%

### Code-Qualität
- ✅ Type-Hints: >80% Abdeckung
- ✅ Mypy: 0 Fehler im --strict Modus
- ✅ Exception-Handling: Spezifisch + Logging
- ✅ Magic Numbers: <10 im gesamten Projekt

### Stabilität
- ✅ Uptime: >24h ohne Neustart
- ✅ Auto-Backup: Täglich
- ✅ Fehler-Recovery: Automatisch nach Scan-Fehler

---

## 🎯 Prioritäts-Matrix (Zusammenfassung)

| ID | Task | Impact | Aufwand | Risiko | Sprint |
|----|------|--------|---------|--------|--------|
| Bug #1 | test_fast_action_timing | 🔴 Hoch | 2-3h | Niedrig | 1 |
| Bug #2 | test_historical_placed | 🔴 Hoch | 2-4h | Niedrig | 1 |
| Opt #1 | Screenshot-Cache | 🟢 Hoch | 30min | Niedrig | 1 |
| Opt #2 | API Retry | 🟡 Mittel | 1h | Niedrig | 1 |
| Opt #3 | Focus-Detection | 🟡 Mittel | 15min | Niedrig | 1 |
| Quality #1 | Exception-Handling | 🟡 Mittel | 2-3h | Niedrig | 2 |
| Quality #2 | Type-Hints | 🟡 Mittel | 3-4h | Niedrig | 2 |
| Quality #3 | Magic Numbers | 🟢 Niedrig | 1h | Sehr niedrig | 2 |
| Stab #1 | Memory-Leak-Prevention | 🟡 Mittel | 1-2h | Niedrig | 2 |
| Stab #2 | Focus Race Condition | 🟡 Mittel | 1h | Niedrig | 3 |
| Stab #3 | Database-Backup | 🟢 Niedrig | 2h | Niedrig | 3 |
| Mon #1 | Strukturiertes Logging | 🟡 Mittel | 3-4h | Mittel | 3 |
| Mon #2 | Performance-Metriken | 🟢 Hoch | 2-3h | Niedrig | 3 |
| GUI #1 | Error-Display | 🟡 Mittel | 1-2h | Niedrig | 4 |
| GUI #2 | Config-GUI | 🟢 Niedrig | 4-6h | Niedrig | 4 |
| Feat #1 | Async Pipeline | 🟢 Hoch | 6-8h | Mittel | 5 |

---

## 📞 Kontakt & Review

**Author:** AI Code Analysis  
**Date:** 2025-10-13  
**Review:** Empfohlen nach Sprint 1 & 2

**Feedback gewünscht zu:**
- Priorisierung korrekt?
- Weitere Pain-Points?
- Performance-Engpässe in der Praxis?

---

## 📚 Referenzen

- Projektdokumentation: `instructions.md`
- Test-Suite: `scripts/run_all_tests.py`
- Performance-Analyse: `docs/PERFORMANCE_ANALYSIS_2025-10-12.md`
- OCR-Dokumentation: `docs/OCR_V2_README.md`
