# Detail-Fenster Transaktionserkennung - Implementierungsplan

## Übersicht

Dieses Dokument beschreibt die Implementierung einer neuen Funktion zur Erkennung von Transaktionen direkt im Item-Detail-Fenster (Buy/Sell-Item-Fenster), wenn das Transaktionslog nach der Transaktion nicht sichtbar ist.

**Status**: ENTWURF  
**Version**: 1.0  
**Datum**: 2025-10-20  
**Autor**: AI Assistant (basierend auf Codebase-Analyse)

---

## 1. Problemstellung

### 1.1 Aktuelles Verhalten
- Transaktionen werden ausschließlich durch Auslesen des Transaktionslogs (`detect_log_roi`) erfasst
- Wenn der Benutzer nach einer Transaktion das Detail-Fenster nicht verlässt, wird die Transaktion NICHT gespeichert
- Das Bestätigungsfenster ("Yes(ENTER)") ist nur kurz sichtbar und kann nicht zur Auswertung genutzt werden

### 1.2 Gewünschtes Verhalten
1. Benutzer öffnet Detail-Fenster (Buy-Item oder Sell-Item)
2. Wählt Preis/Menge aus und klickt "Buy" oder "Register"
3. Bestätigt mit "Yes(ENTER)"
4. **NEU**: Anwendung erkennt Transaktion durch Überwachung von:
   - **Kontostand** (Balance) → Ändert sich nach Bestätigung
   - **Lagerbestand** (Warehouse Quantity) → Ändert sich bei Buy/Sell
5. Menge und Preis werden aus den Deltas berechnet
6. Transaktion wird mit System-Timestamp gespeichert

---

## 2. Architektur-Analyse

### 2.1 Bestehende Komponenten

#### 2.1.1 Window Detection (`utils.py::detect_window_type`)
```python
def detect_window_type(ocr_text: str) -> str:
    """
    Erkennt 4 Marktfenster:
    - 'sell_overview': Sales Completed, Items Listed
    - 'buy_overview': Orders Completed, Orders
    - 'sell_item': Set Price + MAX/MIN Scale
    - 'buy_item': Desired Price + MAX/MIN Scale
    """
```

**Status**: ✅ Bereits implementiert und funktioniert zuverlässig  
**Verwendet in**: `tracker.py::process_ocr_text`

#### 2.1.2 ROI Detection (`utils.py`)
```python
def detect_log_roi(img):        # 0-32% Höhe - Transaktionslog
def detect_window_label_roi(img): # 33-65% Höhe - Fenstertyp
def detect_metrics_roi(img):     # 33-97% Höhe - UI-Metriken
```

**Status**: ✅ Bereits implementiert  
**Anmerkung**: `detect_metrics_roi` wird aktuell für Overview-Fenster verwendet

#### 2.1.3 Metrics Extraction (`tracker.py`)
```python
def _extract_buy_ui_metrics(self, full_text):
    """
    Extrahiert aus Buy-Overview:
    - orders
    - ordersCompleted
    - remainingPrice
    """

def _extract_sell_ui_metrics(self, full_text):
    """
    Extrahiert aus Sell-Overview:
    - salesCompleted
    - price
    """
```

**Status**: ✅ Bereits implementiert für Overview-Fenster  
**TODO**: Neue Funktion für Detail-Fenster-Metriken benötigt

#### 2.1.4 Deduplication System (`tracker.py`)
```python
def make_content_hash(self, tx):
    """
    Generiert content-based Hash für Deduplizierung
    Verhindert doppelte Speicherung identischer Transaktionen
    """

def store_transaction_db(self, tx):
    """
    Speichert Transaktion mit umfangreichen Duplikat-Checks:
    - content_hash (20-Minuten-Toleranz)
    - seen_tx_signatures (Session-basiert)
    - transaction_exists_by_values_near_time (5-Minuten-Toleranz)
    """
```

**Status**: ✅ Bereits implementiert und robust  
**Anmerkung**: Muss für Detail-Fenster-Transaktionen erweitert werden

---

### 2.2 Datenfluss (aktuell)

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. capture_region() → Screenshot (BGR)                          │
└───────────────────┬─────────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────────┐
│ 2. preprocess() → Grayscale + CLAHE + Sharpening               │
└───────────────────┬─────────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────────┐
│ 3. ROI Detection                                                 │
│    - detect_log_roi()        → Log-Bereich (0-32%)             │
│    - detect_window_label_roi() → Label-Bereich (33-65%)        │
│    - detect_metrics_roi()    → Metrics-Bereich (33-97%)        │
└───────────────────┬─────────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────────┐
│ 4. OCR Processing (cached)                                      │
│    - Label → detect_window_type()                               │
│    - Log → split_text_into_log_entries() [NUR Overview]        │
│    - Metrics → _extract_buy/sell_ui_metrics() [NUR Overview]   │
└───────────────────┬─────────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────────┐
│ 5. Transaction Processing                                       │
│    - extract_details_from_entry()                               │
│    - Clustering (transaction + placed/withdrew/listed)          │
│    - Case Determination (collect/relist_full/relist_partial)    │
└───────────────────┬─────────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────────┐
│ 6. Deduplication & Persistence                                  │
│    - make_content_hash()                                        │
│    - transaction_exists_*() Checks                              │
│    - store_transaction_db()                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Implementierungsplan

### 3.1 Phase 1: Detail-Fenster Metriken-Extraktion

#### 3.1.1 Neue ROI für Detail-Fenster

**Datei**: `utils.py`

```python
def detect_detail_item_name_roi(img):
    """
    ROI für Item-Name im Detail-Fenster.
    
    Position (basierend auf sell_item_marked.png / buy_item_marked.png):
    - Oben links im Detail-Fenster
    - Text: Item-Name (z.B. "Powder of Darkness", "Brutal Death Elixir")
    
    Returns:
        tuple (x, y, width, height) oder None
    """
    try:
        h, w = _shape_hw(img)
        # Item-Name ist immer oben links im Detail-Fenster
        # Geschätzte Position: 5-40% Breite, 5-20% Höhe
        x_start = int(w * 0.05)
        x_end = int(w * 0.40)
        y_start = int(h * 0.05)
        y_end = int(h * 0.20)
        
        width = x_end - x_start
        height = y_end - y_start
        return (x_start, y_start, width, height)
    except Exception:
        return None


def detect_detail_balance_roi(img):
    """
    ROI für Kontostand (Balance) im Detail-Fenster.
    
    Position (basierend auf sell_item_marked.png / buy_item_marked.png):
    - Violettes Rechteck: Mittig links
    - Text: "Balance: <amount> Silver"
    
    Returns:
        tuple (x, y, width, height) oder None
    """
    try:
        h, w = _shape_hw(img)
        # Kontostand ist immer mittig-links im Detail-Fenster
        # Geschätzte Position: 10-30% Breite, 35-50% Höhe
        x_start = int(w * 0.10)
        x_end = int(w * 0.35)
        y_start = int(h * 0.35)
        y_end = int(h * 0.50)
        
        width = x_end - x_start
        height = y_end - y_start
        return (x_start, y_start, width, height)
    except Exception:
        return None


def detect_detail_warehouse_roi(img, window_type: str):
    """
    ROI für Lagerbestand (Warehouse Quantity) im Detail-Fenster.
    
    Position abhängig von Fenstertyp:
    - Sell-Item: Relativ weit oben links (gelbes Rechteck in sell_item_marked.png)
    - Buy-Item: Relativ weit unten links (gelbes Rechteck in buy_item_marked.png)
    
    Args:
        img: Preprocessed image
        window_type: 'sell_item' oder 'buy_item'
    
    Returns:
        tuple (x, y, width, height) oder None
    """
    try:
        h, w = _shape_hw(img)
        
        if window_type == 'sell_item':
            # Sell-Item: Warehouse oben links
            # Geschätzte Position: 5-30% Breite, 15-35% Höhe
            x_start = int(w * 0.05)
            x_end = int(w * 0.30)
            y_start = int(h * 0.15)
            y_end = int(h * 0.35)
        elif window_type == 'buy_item':
            # Buy-Item: Warehouse unten links
            # Geschätzte Position: 5-30% Breite, 65-85% Höhe
            x_start = int(w * 0.05)
            x_end = int(w * 0.30)
            y_start = int(h * 0.65)
            y_end = int(h * 0.85)
        else:
            return None
        
        width = x_end - x_start
        height = y_end - y_start
        return (x_start, y_start, width, height)
    except Exception:
        return None
```

**Risiko**: ROI-Positionen müssen anhand der Screenshots kalibriert werden  
**Mitigation**: Kalibrierungs-Script `scripts/utils/calibrate_detail_roi.py` erstellen

---

#### 3.1.2 Detail-Fenster Metriken-Extraktion

**Datei**: `tracker.py`

```python
def _extract_detail_window_metrics(self, ocr_text: str) -> dict | None:
    """
    Extrahiert Metriken aus Detail-Fenster (Buy-Item / Sell-Item).
    
    Extrahierte Daten:
    - balance: Aktueller Kontostand (Silver)
    - warehouse_qty: Aktueller Lagerbestand (Anzahl Items)
    - item_name: Name des Items (falls erkannt)
    - set_price: Eingestellter Preis (bei Sell-Item)
    - desired_price: Gewünschter Preis (bei Buy-Item)
    - quantity: Eingestellte Menge
    
    Args:
        ocr_text: OCR-Text aus Metrics-ROI + Balance-ROI + Warehouse-ROI
    
    Returns:
        dict mit Metriken oder None
    
    Beispiel (Sell-Item):
        {
            'balance': 1234567890,
            'warehouse_qty': 50,
            'item_name': 'Powder of Darkness',
            'set_price': 15000,
            'quantity': 100
        }
    
    Beispiel (Buy-Item):
        {
            'balance': 1234567890,
            'warehouse_qty': 10,
            'item_name': 'Brutal Death Elixir',
            'desired_price': 4500000,
            'quantity': 5
        }
    """
    if not ocr_text:
        return None
    
    # Normalisiere Text
    s = re.sub(r'\s+', ' ', ocr_text)
    s = s.replace('：', ':').replace('．', '.').replace('／', '/')
    
    metrics = {}
    
    # 1. Balance extrahieren
    # Pattern: "Balance: 1,234,567,890 Silver"
    balance_pattern = re.compile(
        r'Balance\s*[:;]?\s*([0-9,\.]+)\s*Silver',
        re.IGNORECASE
    )
    m = balance_pattern.search(s)
    if m:
        metrics['balance'] = normalize_numeric_str(m.group(1))
    
    # 2. Warehouse Quantity extrahieren
    # Pattern: "Warehouse Quantity: 50" oder "Warehouse: 50" oder "WH: 50"
    warehouse_pattern = re.compile(
        r'(?:Warehouse\s*(?:Quantity)?|WH)\s*[:;]?\s*([0-9,\.]+)',
        re.IGNORECASE
    )
    m = warehouse_pattern.search(s)
    if m:
        metrics['warehouse_qty'] = normalize_numeric_str(m.group(1))
    
    # 3. Set Price / Desired Price extrahieren
    # Sell-Item: "Set Price: 15,000 Silver"
    # Buy-Item: "Desired Price: 4,500,000 Silver"
    price_pattern = re.compile(
        r'(?:Set\s+Price|Desired\s+Price)\s*[:;]?\s*([0-9,\.]+)\s*Silver',
        re.IGNORECASE
    )
    m = price_pattern.search(s)
    if m:
        price_val = normalize_numeric_str(m.group(1))
        if 'set price' in s.lower():
            metrics['set_price'] = price_val
        else:
            metrics['desired_price'] = price_val
    
    # 4. Register Quantity / Desired Amount extrahieren
    # Sell-Item: "Register Quantity: 100"
    # Buy-Item: "Desired Amount: 5"
    qty_pattern = re.compile(
        r'(?:Register\s+Quantity|Desired\s+Amount)\s*[:;]?\s*([0-9,\.]+)',
        re.IGNORECASE
    )
    m = qty_pattern.search(s)
    if m:
        metrics['quantity'] = normalize_numeric_str(m.group(1))
    
    # 5. Item-Name extrahieren (aus Label-ROI oder oberem Bereich)
    # Dies ist schwierig, da der Item-Name oft weit oben steht
    # → Besser: Item-Name aus vorherigem Scan cachen
    
    # Item-Name Extraktion (oben links im Detail-Fenster)
    # Pattern: Einfach der erste große Text-Block oben links
    # Oft Format: "<ItemName>" oder "[Grade] ItemName"
    item_name_pattern = re.compile(
        r'^\s*(\[.+?\])?\s*([A-Za-z0-9\[\]\'\-\:\(\)\s]+)',
        re.MULTILINE
    )
    m = item_name_pattern.search(s)
    if m:
        # Group 1 = Optional grade bracket "[Party]"
        # Group 2 = Item name
        name = m.group(2).strip() if m.group(2) else None
        if name:
            # Clean item name
            from utils import clean_item_name
            metrics['item_name'] = clean_item_name(name)
    
    return metrics if metrics else None
```

---

### 3.2 Phase 2: Transaktionserkennung durch Delta-Überwachung

#### 3.2.1 State-Management für Detail-Fenster

**Datei**: `tracker.py` (Erweiterung der `__init__` Methode)

```python
class MarketTracker:
    def __init__(self, ...):
        # ... existing code ...
        
        # Detail-Fenster State
        self._detail_window_active = False
        self._detail_window_type = None  # 'sell_item' oder 'buy_item'
        self._detail_window_item = None  # Name des Items (aus Item-Name-ROI)
        self._detail_baseline_balance = None
        self._detail_baseline_warehouse = None
        self._detail_last_metrics = None
        self._detail_confirmation_pending = False
        self._detail_confirmation_timestamp = None
        
        # Timeout für Bestätigung: Wenn nach 5 Sekunden keine Änderung,
        # dann wurde die Transaktion abgebrochen
        self._detail_confirmation_timeout = 5.0  # Sekunden
```

#### 3.2.2 Detail-Fenster Überwachung

**Datei**: `tracker.py` (neue Methode)

```python
def _monitor_detail_window(self, window_type: str, ocr_text: str):
    """
    Überwacht Detail-Fenster und erkennt Transaktionen durch Balance/Warehouse-Deltas.
    
    State-Machine:
    1. IDLE → Detail-Fenster erkannt → Baseline erfassen → MONITORING
    2. MONITORING → "Buy"/"Register" geklickt (keine direkte Erkennung) → Weiter MONITORING
    3. MONITORING → Bestätigungsfenster (keine Erkennung) → Weiter MONITORING
    4. MONITORING → Balance-Änderung erkannt → TRANSACTION_DETECTED
    5. TRANSACTION_DETECTED → Transaktion speichern → IDLE
    
    Args:
        window_type: 'sell_item' oder 'buy_item'
        ocr_text: Kombinierter OCR-Text (Label + Balance + Warehouse)
    
    Returns:
        None (speichert Transaktion direkt wenn erkannt)
    """
    now = datetime.datetime.now()
    
    # Extrahiere aktuelle Metriken
    current_metrics = self._extract_detail_window_metrics(ocr_text)
    
    if not current_metrics:
        # Keine gültigen Metriken → Reset
        self._reset_detail_window_state()
        return
    
    # 1. Detail-Fenster-Eintritt: Baseline setzen
    if not self._detail_window_active:
        self._detail_window_active = True
        self._detail_window_type = window_type
        self._detail_baseline_balance = current_metrics.get('balance')
        self._detail_baseline_warehouse = current_metrics.get('warehouse_qty')
        self._detail_window_item = current_metrics.get('item_name')  # Item-Name aus ROI
        self._detail_last_metrics = current_metrics
        self._detail_confirmation_pending = False
        
        if self.debug:
            log_debug(
                f"[DETAIL] Window entered: {window_type}, "
                f"item={self._detail_window_item}, "
                f"baseline_balance={self._detail_baseline_balance}, "
                f"baseline_warehouse={self._detail_baseline_warehouse}"
            )
        return
    
    # 2. Überprüfe ob Fenstertyp geändert hat (sollte nicht passieren)
    if self._detail_window_type != window_type:
        if self.debug:
            log_debug(f"[DETAIL] Window type changed: {self._detail_window_type} → {window_type}")
        self._reset_detail_window_state()
        return
    
    # 3. Vergleiche Balance und Warehouse mit Baseline
    current_balance = current_metrics.get('balance')
    current_warehouse = current_metrics.get('warehouse_qty')
    
    if current_balance is None or current_warehouse is None:
        # Unvollständige Metriken → Weiter warten
        return
    
    # 4. Prüfe ob Änderung vorhanden
    balance_changed = (
        self._detail_baseline_balance is not None and
        current_balance != self._detail_baseline_balance
    )
    warehouse_changed = (
        self._detail_baseline_warehouse is not None and
        current_warehouse != self._detail_baseline_warehouse
    )
    
    if not balance_changed and not warehouse_changed:
        # Keine Änderung → Weiter warten
        # Timeout-Check: Wenn Bestätigung pending ist und Timeout überschritten
        if self._detail_confirmation_pending:
            if self._detail_confirmation_timestamp:
                elapsed = (now - self._detail_confirmation_timestamp).total_seconds()
                if elapsed > self._detail_confirmation_timeout:
                    if self.debug:
                        log_debug("[DETAIL] Confirmation timeout - transaction aborted")
                    self._reset_detail_window_state()
        return
    
    # 5. Änderung erkannt → Transaktion verarbeiten
    if self.debug:
        log_debug(
            f"[DETAIL] Transaction detected: "
            f"balance {self._detail_baseline_balance} → {current_balance}, "
            f"warehouse {self._detail_baseline_warehouse} → {current_warehouse}"
        )
    
    # 6. Berechne Deltas
    balance_delta = current_balance - self._detail_baseline_balance if self._detail_baseline_balance else 0
    warehouse_delta = current_warehouse - self._detail_baseline_warehouse if self._detail_baseline_warehouse else 0
    
    # 7. Bestimme Transaktionstyp und -werte
    transaction = self._infer_transaction_from_deltas(
        window_type,
        balance_delta,
        warehouse_delta,
        current_metrics,
        self._detail_last_metrics
    )
    
    if transaction:
        # 8. Speichere Transaktion
        self.store_transaction_db(transaction)
        
        if self.debug:
            log_debug(
                f"[DETAIL] Transaction saved: {transaction['transaction_type']} "
                f"{transaction['quantity']}x {transaction['item_name']} "
                f"for {transaction['price']} Silver"
            )
    
    # 9. Reset State für nächste Transaktion
    # Update Baseline mit aktuellen Werten
    self._detail_baseline_balance = current_balance
    self._detail_baseline_warehouse = current_warehouse
    self._detail_last_metrics = current_metrics
    self._detail_confirmation_pending = False


def _reset_detail_window_state(self):
    """Reset Detail-Fenster State."""
    self._detail_window_active = False
    self._detail_window_type = None
    self._detail_window_item = None
    self._detail_baseline_balance = None
    self._detail_baseline_warehouse = None
    self._detail_last_metrics = None
    self._detail_confirmation_pending = False
    self._detail_confirmation_timestamp = None
```

---

#### 3.2.3 Transaktion aus Deltas ableiten

**Datei**: `tracker.py` (neue Methode)

```python
def _infer_transaction_from_deltas(
    self,
    window_type: str,
    balance_delta: int,
    warehouse_delta: int,
    current_metrics: dict,
    last_metrics: dict
) -> dict | None:
    """
    Leitet Transaktion aus Balance- und Warehouse-Deltas ab.
    
    Regeln:
    
    Sell-Item Window:
    - Balance steigt → Verkauf erfolgreich
    - Warehouse sinkt → Ware wurde entnommen
    - Preis = Balance-Delta / (Tax-Factor = 0.88725)
    - Menge = abs(Warehouse-Delta)
    - Typ = 'sell'
    
    Buy-Item Window:
    - Balance sinkt → Kauf erfolgreich
    - Warehouse steigt → Ware wurde eingelagert
    - Preis = abs(Balance-Delta)
    - Menge = Warehouse-Delta
    - Typ = 'buy'
    
    Args:
        window_type: 'sell_item' oder 'buy_item'
        balance_delta: Änderung des Kontostands (positiv/negativ)
        warehouse_delta: Änderung des Lagerbestands (positiv/negativ)
        current_metrics: Aktuelle Metriken
        last_metrics: Vorherige Metriken
    
    Returns:
        dict mit Transaktionsdaten oder None bei Fehler
    """
    # Validierung
    if balance_delta == 0 and warehouse_delta == 0:
        return None
    
    transaction = {
        'timestamp': datetime.datetime.now(),
        'tx_case': 'detail_window_direct',
        '_from_detail_window': True,
        'raw_related': [],
        'occurrence_index': 0,
    }
    
    # Item-Name aus Metriken oder Cache holen
    item_name = current_metrics.get('item_name')
    if not item_name and self._detail_window_item:
        item_name = self._detail_window_item
    
    if not item_name:
        if self.debug:
            log_debug("[DETAIL] Cannot infer transaction: item_name unknown")
        return None
    
    transaction['item_name'] = item_name
    
    # Sell-Transaction
    if window_type == 'sell_item':
        if balance_delta <= 0:
            if self.debug:
                log_debug(f"[DETAIL] Invalid sell: balance_delta={balance_delta} <= 0")
            return None
        
        if warehouse_delta >= 0:
            if self.debug:
                log_debug(f"[DETAIL] Invalid sell: warehouse_delta={warehouse_delta} >= 0")
            return None
        
        # Menge = abs(Warehouse-Delta)
        quantity = abs(warehouse_delta)
        
        # Preis (brutto) = Balance-Delta / Tax-Factor
        # Tax-Factor = 0.88725 (Net proceeds nach Marketplace-Tax)
        price_gross = int(round(balance_delta / MARKET_SELL_NET_FACTOR))
        
        # Alternative: Nutze set_price aus Metriken falls vorhanden
        set_price = current_metrics.get('set_price') or last_metrics.get('set_price')
        if set_price:
            # Berechne erwarteten Preis und vergleiche mit Balance-Delta
            expected_net = int(round(set_price * quantity * MARKET_SELL_NET_FACTOR))
            if abs(expected_net - balance_delta) < balance_delta * 0.05:  # 5% Toleranz
                price_gross = set_price * quantity
        
        transaction['quantity'] = quantity
        transaction['price'] = price_gross
        transaction['transaction_type'] = 'sell'
    
    # Buy-Transaction
    elif window_type == 'buy_item':
        if balance_delta >= 0:
            if self.debug:
                log_debug(f"[DETAIL] Invalid buy: balance_delta={balance_delta} >= 0")
            return None
        
        if warehouse_delta <= 0:
            if self.debug:
                log_debug(f"[DETAIL] Invalid buy: warehouse_delta={warehouse_delta} <= 0")
            return None
        
        # Menge = Warehouse-Delta
        quantity = warehouse_delta
        
        # Preis (gesamt) = abs(Balance-Delta)
        price_total = abs(balance_delta)
        
        # Alternative: Nutze desired_price aus Metriken falls vorhanden
        desired_price = current_metrics.get('desired_price') or last_metrics.get('desired_price')
        if desired_price:
            # Berechne erwarteten Preis und vergleiche mit Balance-Delta
            expected_total = desired_price * quantity
            if abs(expected_total - price_total) < price_total * 0.05:  # 5% Toleranz
                price_total = expected_total
        
        transaction['quantity'] = quantity
        transaction['price'] = price_total
        transaction['transaction_type'] = 'buy'
    
    else:
        return None
    
    # Plausibilitätsprüfung
    if transaction['quantity'] <= 0 or transaction['quantity'] > MAX_ITEM_QUANTITY:
        if self.debug:
            log_debug(f"[DETAIL] Invalid quantity: {transaction['quantity']}")
        return None
    
    if transaction['price'] <= 0:
        if self.debug:
            log_debug(f"[DETAIL] Invalid price: {transaction['price']}")
        return None
    
    # Unit-Price Plausibility Check
    unit_price = transaction['price'] // transaction['quantity']
    if not self._is_unit_price_plausible(item_name, unit_price):
        if self.debug:
            log_debug(
                f"[DETAIL] Implausible unit price: {unit_price} for {item_name}"
            )
        return None
    
    return transaction
```

---

### 3.3 Phase 3: Integration in Hauptpipeline

#### 3.3.1 Anpassung `process_ocr_text`

**Datei**: `tracker.py` (Methode `process_ocr_text` erweitern)

```python
def process_ocr_text(self, full_text):
    """
    Hauptfunktion für OCR-Verarbeitung.
    """
    # ... existing validation und window detection ...
    
    wtype = detect_window_type(full_text)
    self.current_window = wtype
    
    # NEU: Detail-Fenster Überwachung
    if wtype in ('sell_item', 'buy_item'):
        self._monitor_detail_window(wtype, full_text)
        # WICHTIG: Kein Return hier - Detail-Fenster können auch
        # normale Transaktionen im Log haben (z.B. bei Tab-Wechsel)
    
    # Reset Detail-State wenn Overview-Fenster aktiv
    if wtype in ('sell_overview', 'buy_overview'):
        if self._detail_window_active:
            self._reset_detail_window_state()
    
    # ... existing overview processing ...
```

---

#### 3.3.2 Deduplication für Detail-Transaktionen

**Datei**: `tracker.py` (Methode `store_transaction_db` erweitern)

```python
def store_transaction_db(self, tx):
    """
    Speichert Transaktion mit Deduplizierung.
    """
    # ... existing deduplication checks ...
    
    # NEU: Spezielle Behandlung für Detail-Fenster-Transaktionen
    from_detail = tx.get('_from_detail_window', False)
    
    if from_detail:
        # Detail-Transaktionen verwenden System-Timestamp
        # → Zusätzlicher Check gegen ähnliche Transaktionen in den letzten 10 Sekunden
        try:
            db_cur = get_cursor()
            db_cur.execute(
                """
                SELECT id, timestamp FROM transactions
                WHERE item_name = ? AND quantity = ? AND price = ? AND transaction_type = ?
                  AND timestamp >= datetime('now', '-10 seconds')
                LIMIT 1
                """,
                (tx['item_name'], tx['quantity'], tx['price'], tx['transaction_type'])
            )
            existing = db_cur.fetchone()
            if existing:
                if self.debug:
                    log_debug(
                        f"[DETAIL] Duplicate prevented: {tx['item_name']} "
                        f"within 10 seconds"
                    )
                return False
        except Exception as e:
            if self.debug:
                log_debug(f"[DETAIL] Deduplication check failed: {e}")
    
    # ... existing storage logic ...
```

---

### 3.4 Phase 4: ROI-Kalibrierung und Testing

#### 3.4.1 ROI-Kalibrierungs-Script

**Datei**: `scripts/utils/calibrate_detail_roi.py` (NEU)

```python
"""
ROI-Kalibrierung für Detail-Fenster.

Dieses Script hilft bei der Kalibrierung der ROI-Positionen für:
- Balance (Kontostand)
- Warehouse Quantity (Lagerbestand)

Usage:
    python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/sell_item.png
    python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/buy_item.png
"""

import argparse
import cv2
import numpy as np
from pathlib import Path
from utils import preprocess, detect_detail_balance_roi, detect_detail_warehouse_roi


def visualize_roi(image_path: str, window_type: str):
    """
    Visualisiert ROI-Positionen auf Screenshot.
    """
    # Load image
    img = cv2.imread(str(image_path))
    if img is None:
        print(f"Error: Could not load image {image_path}")
        return
    
    # Preprocess
    proc = preprocess(img, adaptive=True, denoise=False, fast_mode=False)
    
    # Get ROIs
    item_name_roi = detect_detail_item_name_roi(proc)
    balance_roi = detect_detail_balance_roi(proc)
    warehouse_roi = detect_detail_warehouse_roi(proc, window_type)
    
    # Draw ROIs on original image
    output = img.copy()
    
    if item_name_roi:
        x, y, w, h = item_name_roi
        cv2.rectangle(output, (x, y), (x + w, y + h), (0, 255, 0), 3)  # Grün
        cv2.putText(output, "Item Name ROI", (x, y - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
    if balance_roi:
        x, y, w, h = balance_roi
        cv2.rectangle(output, (x, y), (x + w, y + h), (255, 0, 255), 3)  # Violett
        cv2.putText(output, "Balance ROI", (x, y - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
    
    if warehouse_roi:
        x, y, w, h = warehouse_roi
        cv2.rectangle(output, (x, y), (x + w, y + h), (0, 255, 255), 3)  # Gelb
        cv2.putText(output, "Warehouse ROI", (x, y - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
    # Save output
    output_path = Path("debug") / f"calibrate_{window_type}_roi.png"
    output_path.parent.mkdir(exist_ok=True)
    cv2.imwrite(str(output_path), output)
    
    print(f"✅ ROI visualization saved to: {output_path}")
    print(f"   Item Name ROI: {item_name_roi}")
    print(f"   Balance ROI: {balance_roi}")
    print(f"   Warehouse ROI: {warehouse_roi}")


def main():
    parser = argparse.ArgumentParser(description="Calibrate Detail Window ROIs")
    parser.add_argument("--image", required=True, help="Path to screenshot")
    parser.add_argument("--type", choices=['sell_item', 'buy_item'], required=True,
                       help="Window type")
    
    args = parser.parse_args()
    
    visualize_roi(args.image, args.type)


if __name__ == "__main__":
    main()
```

**Usage**:
```powershell
# Sell-Item Window
python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/sell_item_marked.png --type sell_item

# Buy-Item Window
python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/buy_item_marked.png --type buy_item
```

---

#### 3.4.2 Unit-Tests

**Datei**: `tests/unit/test_detail_window_transactions.py` (NEU)

```python
"""
Unit-Tests für Detail-Fenster Transaktionserkennung.
"""

import pytest
import datetime
from tracker import MarketTracker
from utils import normalize_numeric_str


class TestDetailWindowMetrics:
    """Tests für _extract_detail_window_metrics."""
    
    def test_extract_balance(self):
        """Test Balance-Extraktion."""
        tracker = MarketTracker(debug=True)
        
        ocr_text = "Balance: 1,234,567,890 Silver"
        metrics = tracker._extract_detail_window_metrics(ocr_text)
        
        assert metrics is not None
        assert metrics['balance'] == 1234567890
    
    def test_extract_warehouse_qty(self):
        """Test Warehouse-Quantity-Extraktion."""
        tracker = MarketTracker(debug=True)
        
        ocr_text = "Warehouse Quantity: 50"
        metrics = tracker._extract_detail_window_metrics(ocr_text)
        
        assert metrics is not None
        assert metrics['warehouse_qty'] == 50
    
    def test_extract_set_price(self):
        """Test Set-Price-Extraktion (Sell-Item)."""
        tracker = MarketTracker(debug=True)
        
        ocr_text = "Set Price: 15,000 Silver Register Quantity: 100"
        metrics = tracker._extract_detail_window_metrics(ocr_text)
        
        assert metrics is not None
        assert metrics['set_price'] == 15000
        assert metrics['quantity'] == 100
    
    def test_extract_desired_price(self):
        """Test Desired-Price-Extraktion (Buy-Item)."""
        tracker = MarketTracker(debug=True)
        
        ocr_text = "Desired Price: 4,500,000 Silver Desired Amount: 5"
        metrics = tracker._extract_detail_window_metrics(ocr_text)
        
        assert metrics is not None
        assert metrics['desired_price'] == 4500000
        assert metrics['quantity'] == 5


class TestTransactionInference:
    """Tests für _infer_transaction_from_deltas."""
    
    def test_sell_transaction_inference(self):
        """Test Sell-Transaktion aus Deltas."""
        tracker = MarketTracker(debug=True)
        tracker._detail_window_item = "Powder of Darkness"
        
        # Sell: Balance +1,500,000 (net), Warehouse -100
        transaction = tracker._infer_transaction_from_deltas(
            window_type='sell_item',
            balance_delta=1500000,
            warehouse_delta=-100,
            current_metrics={'balance': 100000000, 'warehouse_qty': 400},
            last_metrics={'balance': 98500000, 'warehouse_qty': 500}
        )
        
        assert transaction is not None
        assert transaction['transaction_type'] == 'sell'
        assert transaction['quantity'] == 100
        assert transaction['item_name'] == "Powder of Darkness"
        # Preis (brutto) = 1,500,000 / 0.88725 ≈ 1,690,359
        assert 1680000 <= transaction['price'] <= 1700000
    
    def test_buy_transaction_inference(self):
        """Test Buy-Transaktion aus Deltas."""
        tracker = MarketTracker(debug=True)
        tracker._detail_window_item = "Brutal Death Elixir"
        
        # Buy: Balance -22,500,000, Warehouse +5
        transaction = tracker._infer_transaction_from_deltas(
            window_type='buy_item',
            balance_delta=-22500000,
            warehouse_delta=5,
            current_metrics={'balance': 77500000, 'warehouse_qty': 15},
            last_metrics={'balance': 100000000, 'warehouse_qty': 10}
        )
        
        assert transaction is not None
        assert transaction['transaction_type'] == 'buy'
        assert transaction['quantity'] == 5
        assert transaction['item_name'] == "Brutal Death Elixir"
        assert transaction['price'] == 22500000
    
    def test_invalid_sell_positive_warehouse(self):
        """Test: Sell mit positivem Warehouse-Delta ist ungültig."""
        tracker = MarketTracker(debug=True)
        tracker._detail_window_item = "Test Item"
        
        transaction = tracker._infer_transaction_from_deltas(
            window_type='sell_item',
            balance_delta=1000000,
            warehouse_delta=10,  # Positiv → Ungültig für Sell
            current_metrics={},
            last_metrics={}
        )
        
        assert transaction is None
    
    def test_invalid_buy_negative_warehouse(self):
        """Test: Buy mit negativem Warehouse-Delta ist ungültig."""
        tracker = MarketTracker(debug=True)
        tracker._detail_window_item = "Test Item"
        
        transaction = tracker._infer_transaction_from_deltas(
            window_type='buy_item',
            balance_delta=-1000000,
            warehouse_delta=-10,  # Negativ → Ungültig für Buy
            current_metrics={},
            last_metrics={}
        )
        
        assert transaction is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

**Run Tests**:
```powershell
python -m pytest tests/unit/test_detail_window_transactions.py -v
```

---

### 3.5 Phase 5: Integration Testing & Validation

#### 3.5.1 Manual End-to-End Test

**Datei**: `tests/manual/test_detail_window_e2e.md` (NEU)

```markdown
# Detail-Fenster End-to-End Test

## Voraussetzungen
1. Spiel gestartet
2. Marketplace geöffnet
3. Auto-Track aktiviert

## Test 1: Sell-Transaction im Detail-Fenster

### Schritte
1. Öffne Sell-Overview
2. Wähle Item aus Liste (z.B. "Powder of Darkness")
3. Klicke "Sell" → Detail-Fenster öffnet sich
4. Notiere:
   - Warehouse Quantity (vor Verkauf): ______
   - Balance (vor Verkauf): ______
5. Stelle Preis und Menge ein
   - Set Price: ______
   - Register Quantity: ______
6. Klicke "Register" → Bestätigungsfenster
7. Klicke "Yes (ENTER)"
8. Warte bis Bestätigungsfenster schließt

### Erwartetes Ergebnis
- ✅ Transaktion wird in Datenbank gespeichert
- ✅ tx_case = 'detail_window_direct'
- ✅ transaction_type = 'sell'
- ✅ Menge = Register Quantity
- ✅ Preis ≈ (Set Price × Quantity) / 0.88725
- ✅ Timestamp = System-Zeit (nicht Game-Zeit)

### Verifikation
```sql
SELECT * FROM transactions 
WHERE tx_case = 'detail_window_direct' 
  AND transaction_type = 'sell'
ORDER BY timestamp DESC 
LIMIT 1;
```

---

## Test 2: Buy-Transaction im Detail-Fenster

### Schritte
1. Öffne Buy-Overview
2. Wähle Item aus Liste (z.B. "Brutal Death Elixir")
3. Klicke "Buy" → Detail-Fenster öffnet sich
4. Notiere:
   - Warehouse Quantity (vor Kauf): ______
   - Balance (vor Kauf): ______
5. Stelle Preis und Menge ein
   - Desired Price: ______
   - Desired Amount: ______
6. Klicke "Buy" → Bestätigungsfenster
7. Klicke "Yes (ENTER)"
8. Warte bis Bestätigungsfenster schließt

### Erwartetes Ergebnis
- ✅ Transaktion wird in Datenbank gespeichert
- ✅ tx_case = 'detail_window_direct'
- ✅ transaction_type = 'buy'
- ✅ Menge = Desired Amount
- ✅ Preis = Desired Price × Menge
- ✅ Timestamp = System-Zeit (nicht Game-Zeit)

---

## Test 3: Abgebrochene Transaktion

### Schritte
1. Öffne Detail-Fenster (Sell oder Buy)
2. Stelle Preis und Menge ein
3. Klicke "Register"/"Buy"
4. **ABBRUCH**: Klicke "No" oder drücke ESC
5. Warte 6 Sekunden

### Erwartetes Ergebnis
- ✅ Keine Transaktion gespeichert
- ✅ Detail-State wird nach Timeout zurückgesetzt

---

## Test 4: Duplikat-Prävention

### Schritte
1. Führe Sell-Transaktion durch (Test 1)
2. Öffne **unmittelbar danach** das Overview-Fenster
3. Warte bis Log-OCR die Transaktion erkennt

### Erwartetes Ergebnis
- ✅ Transaktion wird NICHT doppelt gespeichert
- ✅ Nur 1 Eintrag in Datenbank
- ✅ Log zeigt: "[DETAIL] Duplicate prevented"

---

## Troubleshooting

### Problem: Balance/Warehouse nicht erkannt
**Diagnose**:
```powershell
python scripts/utils/calibrate_detail_roi.py --image debug/debug_orig.png --type sell_item
```
**Lösung**: ROI-Positionen in `utils.py` anpassen

### Problem: Transaktion wird doppelt gespeichert
**Diagnose**: Check `ocr_log.txt` für Duplikat-Checks
**Lösung**: Deduplication-Timeout erhöhen in `store_transaction_db`

### Problem: Ungültige Preise/Mengen
**Diagnose**: Check OCR-Extraktion mit `analyze_ocr.py`
**Lösung**: OCR-Parameter tunen oder Plausibilitätsprüfung adjustieren
```

---

## 4. Risiko-Analyse & Mitigationen

### 4.1 Risiko: ROI-Positionen variieren

**Beschreibung**: Die Position von Balance und Warehouse-Quantity kann je nach Bildschirmauflösung oder UI-Skalierung variieren.

**Wahrscheinlichkeit**: Hoch  
**Impact**: Kritisch (Feature funktioniert nicht)

**Mitigation**:
1. **ROI-Kalibrierungs-Tool** (`calibrate_detail_roi.py`)
2. **Prozentuale Positionen** statt absoluter Pixel
3. **Fallback auf größere ROIs** wenn Extraktion fehlschlägt
4. **User-Setting**: Erlaubt manuelle ROI-Anpassung in GUI

---

### 4.2 Risiko: OCR-Fehler bei Balance/Warehouse

**Beschreibung**: OCR kann Zahlen falsch lesen (z.B. "1,234,567" → "1,234,S67").

**Wahrscheinlichkeit**: Mittel  
**Impact**: Hoch (Falsche Transaktionswerte)

**Mitigation**:
1. **Retry-Logik**: 2-3 OCR-Läufe mit Majority-Vote
2. **Plausibilitätsprüfung**: Vergleich mit set_price/desired_price aus UI
3. **Delta-Validierung**: Prüfe ob Delta plausibel ist (nicht zu groß/klein)
4. **User-Feedback**: Zeige erkannte Werte in GUI an vor Speicherung

---

### 4.3 Risiko: Race-Condition bei schnellen Transaktionen

**Beschreibung**: Benutzer führt mehrere Transaktionen direkt hintereinander durch, bevor Balance/Warehouse aktualisiert wird.

**Wahrscheinlichkeit**: Niedrig  
**Impact**: Mittel (Fehlende oder falsche Transaktionen)

**Mitigation**:
1. **Transaction Queue**: Speichere Deltas in Queue statt direkt zu verarbeiten
2. **Timestamp-Tracking**: Verfolge letzte bekannte Änderung
3. **Debouncing**: Warte 1-2 Sekunden nach letzter Änderung bevor Processing
4. **Transaction-IDs**: Vergebe eindeutige IDs für jede erkannte Änderung

---

### 4.4 Risiko: Doppelte Speicherung (Detail + Log)

**Beschreibung**: Transaktion wird sowohl im Detail-Fenster als auch später im Log erkannt und zweimal gespeichert.

**Wahrscheinlichkeit**: Hoch  
**Impact**: Hoch (Falsche Statistiken)

**Mitigation**:
1. **Content-Hash**: Verwende bestehenden `make_content_hash` für Deduplizierung
2. **10-Sekunden-Window**: Verhindere gleiche Transaktion innerhalb 10s
3. **Flag `_from_detail_window`**: Markiere Detail-Transaktionen explizit
4. **Session-Cache**: Erweitere `seen_tx_signatures` um Detail-Transaktionen

---

### 4.5 Risiko: System-Timestamp statt Game-Timestamp

**Beschreibung**: Detail-Transaktionen verwenden System-Zeit, nicht Game-Zeit. Dies kann bei Zeitzonenunterschieden oder Latenz zu Inkonsistenzen führen.

**Wahrscheinlichkeit**: Mittel  
**Impact**: Niedrig (Nur Sortierung betroffen)

**Mitigation**:
1. **Explizite Markierung**: `tx_case = 'detail_window_direct'` zeigt System-Timestamp
2. **Relativer Timestamp**: Speichere zusätzlich Game-Timestamp falls verfügbar
3. **GUI-Hinweis**: Zeige in History an dass Timestamp geschätzt ist
4. **Export-Warnung**: CSV/JSON-Export enthält Hinweis auf System-Timestamps

---

## 5. Performance-Analyse

### 5.1 OCR-Overhead

**Zusätzliche OCR-Läufe pro Scan** (nur bei Detail-Fenstern):
- Item-Name-ROI: ~50-100ms (kleine ROI, nur beim Fenster-Eintritt)
- Balance-ROI: ~50-100ms (kleine ROI)
- Warehouse-ROI: ~50-100ms (kleine ROI)
- **Gesamt**: +150-300ms pro Scan (nur Detail-Fenster)

**Aktueller Scan-Zyklus**: ~150ms (POLL_INTERVAL)  
**Nach Implementation**: 
- Overview-Fenster: ~150ms (unverändert)
- Detail-Fenster: ~300-450ms (+150-300ms)

**Mitigation**:
- Item-Name nur beim Fenster-Eintritt auslesen (gecacht für Session)
- Balance und Warehouse-ROIs parallel verarbeiten (Threading)
- OCR-Cache für statische ROIs (Balance ändert sich nur bei Transaktion)
- ROI-Diffing: Nur OCR wenn ROI sich visuell geändert hat

---

### 5.2 Memory-Footprint

**Neue State-Variablen**:
- `_detail_baseline_balance`: int (8 bytes)
- `_detail_baseline_warehouse`: int (8 bytes)
- `_detail_last_metrics`: dict (~500 bytes)

**Gesamt**: <1 KB zusätzlich → Vernachlässigbar

---

### 5.3 Burst-Scan-Impact

**Aktuelles Verhalten**: Detail-Fenster löst Burst-Scan aus (4 Sekunden @ 80ms Intervall)

**Nach Implementation**: Detail-Fenster bleibt aktiv, Burst-Scan weiter aktiv

**Risiko**: Erhöhte CPU/GPU-Last während Detail-Fenster  
**Mitigation**: 
- Reduziere Burst-Interval auf 150ms (statt 80ms)
- Deaktiviere Log-ROI-OCR während Detail-Fenster

---

## 6. Implementierungs-Zeitplan

### Phase 1: ROI-Definition & Metriken (2-3 Tage)
- [ ] `detect_detail_balance_roi` implementieren
- [ ] `detect_detail_warehouse_roi` implementieren
- [ ] `_extract_detail_window_metrics` implementieren
- [ ] ROI-Kalibrierungs-Script erstellen
- [ ] Unit-Tests für Metriken-Extraktion

### Phase 2: Transaktions-Inferenz (2-3 Tage)
- [ ] `_monitor_detail_window` State-Machine implementieren
- [ ] `_infer_transaction_from_deltas` Logik implementieren
- [ ] Unit-Tests für Inferenz-Logik
- [ ] Integration in `process_ocr_text`

### Phase 3: Deduplication (1-2 Tage)
- [ ] Erweitere `store_transaction_db` für Detail-Transaktionen
- [ ] 10-Sekunden-Window Deduplizierung
- [ ] Test mit echten Daten

### Phase 4: Testing & Validation (3-5 Tage)
- [ ] Manual E2E-Tests durchführen
- [ ] ROI-Positionen kalibrieren
- [ ] Edge-Cases testen (Abbruch, Duplikate, etc.)
- [ ] Performance-Profiling

### Phase 5: GUI-Integration (1-2 Tage)
- [ ] Detail-Transaction-Indicator in GUI
- [ ] Export-Funktionalität erweitern
- [ ] History-View aktualisieren

**Geschätzte Gesamtdauer**: 9-15 Arbeitstage

---

## 7. Offene Fragen & Entscheidungen

### 7.1 Item-Name Erkennung

**Problem**: Item-Name steht oben links im Detail-Fenster.

**Lösung**: ✅ **Dedizierte Item-Name-ROI**
- Neue ROI-Funktion `detect_detail_item_name_roi(img)` 
- Position: Oben links im Detail-Fenster
- Geschätzt: 5-40% Breite, 5-20% Höhe
- Wird zusammen mit Balance/Warehouse ausgelesen

---

### 7.2 Bestätigungs-Erkennung

**Problem**: Bestätigungsfenster ("Yes(ENTER)") ist nur kurz sichtbar.

**Lösung**: ✅ **Ignorieren** 
- Nur Balance/Warehouse-Deltas nutzen
- Deltas sind ausreichend und zuverlässiger als Bestätigungs-Erkennung
- Kein zusätzlicher OCR-Overhead

---

### 7.3 ROI-Kalibrierung

**Lösung**: ✅ **Anhand markierter Screenshots kalibrieren**
- Referenz-Screenshots: `sell_item_marked.png`, `buy_item_marked.png`
- Violettes Rechteck = Balance-ROI
- Gelbes Rechteck = Warehouse-ROI
- Item-Name-ROI = Oben links (muss noch markiert werden)
- Kalibrierungs-Tool erstellt visuelle Overlays zur Verifikation

---

## 8. Dokumentation & User-Guide

### 8.1 User-Dokumentation

**Datei**: `docs/DETAIL_WINDOW_FEATURE.md`

Inhalt:
- Feature-Beschreibung
- Setup-Anleitung (ROI-Kalibrierung)
- Bekannte Limitierungen
- Troubleshooting

### 8.2 Developer-Dokumentation

**Datei**: `docs/DETAIL_WINDOW_ARCHITECTURE.md`

Inhalt:
- State-Machine-Diagramm
- Datenfluss-Diagramm
- API-Referenz für neue Methoden
- Code-Beispiele

---

## 9. Rollout-Plan

### 9.1 Alpha-Release (Interne Tests)
- Implementierung abgeschlossen
- Unit-Tests bestanden
- Manual E2E-Tests auf Entwickler-Maschine

### 9.2 Beta-Release (Closed Beta)
- 3-5 Beta-Tester
- Feedback-Sammlung
- Bug-Fixes

### 9.3 Production-Release
- Dokumentation finalisiert
- Feature-Flag in GUI (Ein-/Ausschalten)
- Monitoring & Logging erweitert

---

## 10. Anhang

### 10.1 Referenz-Screenshots

Siehe `dev-screenshots/`:
- `sell_item_marked.png` - Balance (violett) und Warehouse (gelb) markiert
- `buy_item_marked.png` - Balance (violett) und Warehouse (gelb) markiert
- `sell_item_confirm.png` - Bestätigungsfenster
- `buy_item_confirm.png` - Bestätigungsfenster

### 10.2 Relevante Code-Referenzen

**Bestehende Funktionen**:
- `tracker.py::_extract_buy_ui_metrics` - Template für Metriken-Extraktion
- `tracker.py::_infer_quantity_from_price` - Ähnliche Inferenz-Logik
- `utils.py::detect_window_type` - Window-Detection
- `database.py::transaction_exists_by_values_near_time` - Deduplizierung

**Zu modifizierende Dateien**:
- `utils.py` - Neue ROI-Funktionen
- `tracker.py` - Neue Monitoring-Logik
- `database.py` - Erweiterte Deduplizierung (optional)
- `gui.py` - UI-Indicator für Detail-Transaktionen

---

## 11. Fazit

Die Implementierung der Detail-Fenster-Transaktionserkennung ist technisch machbar und fügt sich gut in die bestehende Architektur ein. Die größten Herausforderungen sind:

1. **ROI-Kalibrierung** - Drei ROIs (Item-Name, Balance, Warehouse) müssen anhand der markierten Screenshots kalibriert werden
2. **Deduplication** - Verhindere doppelte Speicherung (Detail + Log)
3. **OCR-Zuverlässigkeit** - Item-Name, Balance und Warehouse müssen korrekt gelesen werden

**Klare Lösungen für offene Fragen**:
- ✅ Item-Name wird aus dedizierter ROI oben links ausgelesen
- ✅ Bestätigungsfenster wird ignoriert (Delta-basierte Erkennung ausreichend)
- ✅ ROI-Positionen werden anhand violetter/gelber Markierungen in Screenshots kalibriert

**Empfehlung**: Inkrementelle Implementierung mit umfangreichen Tests nach jeder Phase. Feature-Flag in GUI erlaubt einfaches Deaktivieren bei Problemen.

**Nächste Schritte**:
1. ROI-Kalibrierung mit `calibrate_detail_roi.py` und markierten Screenshots
2. Implementierung Phase 1 (3 ROIs + Metriken-Extraktion)
3. Unit-Tests für Item-Name, Balance und Warehouse-Extraktion
4. Prototyp-Test mit echtem Detail-Fenster
5. Review & Iteration
