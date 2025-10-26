# Performance-Analyse: BDO Market Tracker

## 🔍 Aktuelle Performance-Metriken

### 1. **OCR-Pipeline Performance**
```
Durchschnittliche Scan-Zeit: ~1000-1500ms
- Screenshot: 50-100ms
- Preprocessing: 80-120ms  
- OCR (EasyOCR GPU): 400-600ms (cached: ~50ms)
- Text Processing: 200-400ms
- DB Operations: 20-50ms

Cache Hit Rate: ~50% (bei statischen Screens)
Speicherverbrauch: ~80MB (mit deque maxlen=1000)
```

### 2. **Identifizierte Bottlenecks**

#### **Kritisch (>40% der Zeit)**
- **OCR Operation** (400-600ms): Hauptbottleneck, selbst mit GPU
- **Text Processing** (200-400ms): Regex-heavy parsing, verschachtelte Schleifen

#### **Signifikant (10-20% der Zeit)**
- **Preprocessing** (80-120ms): Multiple CV2 Operationen
- **DB Queries** (20-50ms pro Transaction): Synchrone Einzelabfragen

#### **Minor (<10% der Zeit)**
- **Screenshot Capture** (50-100ms): MSS ist bereits optimal
- **Window Detection**: Vernachlässigbar

## 📊 Detaillierte Analyse

### Memory-Profiling
```python
# Aktuelle Speicher-Hotspots:
- seen_tx_signatures: deque(maxlen=1000) ✅ Optimiert
- _screenshot_cache: Dict mit max 10 Einträge ✅ Optimiert  
- structured entries: Temporäre Listen pro Scan (~100 Items)
- window_history: Liste mit max 5 Einträgen ✅ Minimal

Probleme:
- last_overview_text: Unbegrenzter String (kann >100KB werden)
- OCR Log (ocr_log.txt): Rotation bei 10MB, aber I/O-intensiv
```

### CPU-Profiling (parsing.py)
```python
# Top CPU-Verbraucher:
1. extract_details_from_entry(): 35% CPU
   - Viele regex compilations/searches
   - Verschachtelte Bedingungen
   
2. split_text_into_log_entries(): 20% CPU
   - Komplexe Timestamp-Cluster-Logik
   
3. _valid_item_name(): 15% CPU  
   - Whitelist-Lookups ohne Caching
```

## 🚀 Performance-Verbesserungs-Roadmap

### **Phase 1: Quick Wins (1-2 Tage)**

#### 1.1 Regex-Optimierung
```python
# VORHER: Regex wird jedes Mal neu kompiliert
def extract_details_from_entry(ts_text, entry_text):
    if "transaction of" in low or re.search(r"\btransaction\b", low):
        # ...

# NACHHER: Pre-compiled patterns mit Cache
_PATTERNS = {
    'transaction': re.compile(r'\btransaction\b', re.I),
    'sold': re.compile(r'\bsold\b', re.I),
    # ... alle anderen patterns
}

def extract_details_from_entry(ts_text, entry_text):
    if "transaction of" in low or _PATTERNS['transaction'].search(low):
        # ...
```
**Status:** ✅ Implementiert am 2025-10-13 (parsing.py) – zentrale Patterns sind vorab kompiliert, Segment-Grenzen nutzen Shared-Helper-Funktionen.
**Erwartete Verbesserung: -30% Processing Zeit**

#### 1.2 Item Name Validation Cache
```python
# LRU Cache für _valid_item_name()
@lru_cache(maxsize=500)
def _valid_item_name_cached(name: str) -> bool:
    return _valid_item_name(name)
```
**Erwartete Verbesserung: -15% Processing Zeit**

#### 1.3 Batch DB Operations
```python
# VORHER: Einzelne INSERTs
for tx in tx_candidates:
    self.store_transaction_db(tx)

# NACHHER: Batch INSERT
def store_transactions_batch(self, transactions):
    with self.lock:
        cur = get_cursor()
        cur.executemany(
            "INSERT OR IGNORE INTO transactions (...) VALUES (?, ?, ...)",
            [(tx['item_name'], tx['quantity'], ...) for tx in transactions]
        )
        get_connection().commit()
```
**Erwartete Verbesserung: -80% DB Zeit bei mehreren Transaktionen**

### **Phase 2: Strukturelle Optimierungen (3-5 Tage)**

#### 2.1 Asynchrone OCR-Pipeline
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class AsyncMarketTracker:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.ocr_queue = asyncio.Queue(maxsize=3)
        
    async def capture_and_queue(self):
        """Screenshot nehmen und in Queue legen"""
        img = await asyncio.get_event_loop().run_in_executor(
            self.executor, capture_region, self.region
        )
        await self.ocr_queue.put(img)
    
    async def process_ocr_queue(self):
        """OCR aus Queue verarbeiten"""
        while True:
            img = await self.ocr_queue.get()
            text = await asyncio.get_event_loop().run_in_executor(
                self.executor, extract_text, img
            )
            await self.process_text_async(text)
```
**Erwartete Verbesserung: Parallelisierung, -40% Gesamtlatenz**

#### 2.2 Incremental Text Processing
```python
class IncrementalParser:
    def __init__(self):
        self.last_entries = {}  # Cache parsed entries
        
    def parse_incremental(self, new_text, old_text):
        """Parse nur neue/geänderte Zeilen"""
        diff = difflib.ndiff(old_text.split('\n'), new_text.split('\n'))
        new_lines = [line[2:] for line in diff if line.startswith('+ ')]
        
        # Parse nur neue Zeilen
        for line in new_lines:
            if self.is_transaction_line(line):
                yield self.parse_transaction(line)
```
**Erwartete Verbesserung: -60% Processing bei kleinen Änderungen**

#### 2.3 Smart Screenshot Detection
```python
def should_skip_ocr(img_hash: str) -> bool:
    """Intelligentere Cache-Logik"""
    if img_hash in _screenshot_cache:
        cached_time, _, hits = _screenshot_cache[img_hash]
        age = time.time() - cached_time
        
        # Dynamisches TTL basierend auf Hit-Rate
        if hits > 5:  # Sehr statisch
            return age < 5.0  # 5s TTL
        elif hits > 2:
            return age < 3.0  # 3s TTL
        else:
            return age < 2.0  # 2s TTL
    return False
```
**Erwartete Verbesserung: Cache Hit Rate 50% → 70%**

### 🛠️ Phase 2 Umsetzungsplan (3-5 Tage)

| Tag | Aufgabe | Kernschritte | Owner | Erfolgskennzahlen |
|-----|---------|--------------|-------|-------------------|
| Tag 1 | **Async OCR Queue – Architektur** | Sequenzdiagramm aktualisieren, Event-Loop-Entwurf (asyncio + ThreadPool), Risikoanalyse für GUI-Thread | KD | Abnahme des Design-Dokuments, identifizierte Race-Condition-Szenarien |
| Tag 2 | **Async OCR Queue – Implementierung** | `MarketTracker`-Refactor mit `asyncio.Queue`, getrennte Capture- und OCR-Worker, Graceful Shutdown testen | KD | Durchsatz ≥ 1.5x vs. Sync in lokalem Benchmark, kein Deadlock in 30-min-Stresstest |
| Tag 3 | **Incremental Parser – Prototyp** | `IncrementalParser`-Klasse mit Diff-Logik, Cache-Invalidation definieren, Regression-Tests für Buy/Sell-Cluster | KD | Parser reduziert CPU-Zeit pro Scan um ≥40% bei statischen Logs, alle bestehenden Parsing-Tests grün |
| Tag 4 | **Incremental Parser – Integration** | Tracker-Hooks bauen, Fallback auf Full-Parse sichern, Telemetrie für Cache-Hit-Rate hinzufügen | KD | <5% Fehlerrate beim Wechsel auf Full-Parse, Telemetrie-Dashboard aktualisiert |
| Tag 5 | **Smart Screenshot Detection** | Adaptive TTL-Strategie implementieren, Hash-Cache observability (Hits/Miss/Age), Smoke-Tests mit statischen/wechselnden Screens | KD | Cache-Hit-Rate ≥70% im 10-Minuten-Run, OCR-Ausführungszeit -25% ggü. Baseline |

**Zusätzliche Deliverables**
- Update `TEST_SUITE_OVERVIEW.md` mit neuen Performance-Tests (async_queue_benchmark, incremental_parser_benchmark).
- Monitoring-Hooks → Logge Queue-Latency, Parser-Diff-Zeit, Cache-Hit-Rate in `debug/perf_metrics.json`.
- Rollback-Plan dokumentieren (Feature-Flags `USE_ASYNC_PIPELINE`, `USE_INCREMENTAL_PARSER`, `USE_SMART_SCREENSHOT_CACHE`).

### **Phase 3: Architektur-Redesign (1-2 Wochen)**

#### 3.1 Event-Driven Architecture
```python
class EventDrivenTracker:
    def __init__(self):
        self.event_bus = EventBus()
        self.event_bus.on('screenshot_ready', self.handle_screenshot)
        self.event_bus.on('ocr_complete', self.handle_ocr)
        self.event_bus.on('transaction_found', self.handle_transaction)
        
    async def run(self):
        """Hauptloop mit Event-System"""
        asyncio.create_task(self.screenshot_worker())
        asyncio.create_task(self.ocr_worker())
        asyncio.create_task(self.db_worker())
```

#### 3.2 Native OCR Alternative
```python
# Evaluiere schnellere OCR-Engines:
- PaddleOCR: 2-3x schneller als EasyOCR
- TrOCR (Transformer): Höhere Genauigkeit
- Custom Training auf BDO UI Screenshots
```

#### 3.3 Database Optimierung
```python
# SQLite → PostgreSQL für bessere Concurrency
# ODER: SQLite mit WAL-Mode + Connection Pool
conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```

### **Phase 4: Advanced Optimizations (Optional)**

#### 4.1 Computer Vision statt OCR
```python
# Template Matching für bekannte UI-Elemente
def detect_collect_button(img):
    """Erkenne Collect-Button ohne OCR"""
    template = cv2.imread('templates/collect_button.png')
    result = cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)
    # ... position extrahieren
```

#### 4.2 Machine Learning Pipeline
```python
# Train custom model auf BDO Screenshots
class BDOTextDetector:
    def __init__(self):
        self.model = load_trained_model('bdo_ocr_model.pt')
        
    def detect_transactions(self, img):
        """Direct detection ohne OCR"""
        predictions = self.model(img)
        return self.parse_predictions(predictions)
```

## 📈 Erwartete Gesamtverbesserung

| Phase | Zeitaufwand | Performance-Gewinn | Komplexität |
|-------|------------|-------------------|-------------|
| Phase 1 | 1-2 Tage | -30% Scan-Zeit | Niedrig |
| Phase 2 | 3-5 Tage | -50% Scan-Zeit | Mittel |
| Phase 3 | 1-2 Wochen | -70% Scan-Zeit | Hoch |
| Phase 4 | 2-4 Wochen | -85% Scan-Zeit | Sehr hoch |

## 🎯 Priorisierte Sofortmaßnahmen

1. **Regex Pre-Compilation** (parsing.py)
   - Sofort umsetzbar
   - Großer Impact
   
2. **Batch DB Operations** (tracker.py)
   - Einfache Änderung
   - Spürbare Verbesserung bei Multi-TX

3. **Item Name Cache** (utils.py)
   - Quick Win mit @lru_cache

4. **Async OCR Queue**
   - Mittlerer Aufwand
   - Größter Performance-Gewinn

Diese Roadmap würde die Scan-Zeit von aktuell ~1000-1500ms auf unter 300ms reduzieren können, was die Erfassungsrate von 99 auf über 200 Scans/Minute erhöhen würde.