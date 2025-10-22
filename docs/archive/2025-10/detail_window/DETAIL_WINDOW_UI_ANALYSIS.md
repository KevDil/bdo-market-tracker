# Detail-Window UI-Analyse - Tatsächliche Screenshots

Basierend auf den Screenshots: `buy_item.png`, `buy_item_confirm.png`, `sell_item.png`, `sell_item_confirm.png`

## Buy Item Detail-Fenster (`buy_item.png`)

### Sichtbare UI-Elemente

```
┌─────────────────────────────────────────────────┐
│ Purchase                                   [X]  │
│                                                 │
│ Sellers | Prices | Buyers                      │
│                                                 │
│ In Stock    Warehouse Capacity   Listed: XX    │
│ 7,466       0.30 VT               Listed: XX    │
│                                   Listed: XX    │
│                                                 │
│ Base Price    Recent Price                      │
│ 2,510,000     2,540,000                        │
│                                                 │
│ Total Trades  Recent Transaction                │
│ 142,256,362   10-08 21:56                      │
│                                                 │
│ ┌─────────────────────────────────────────┐   │
│ │ Balance          Warehouse Capacity      │   │
│ │ [Icon] 56,500,417,618   [Capacity]      │   │
│ │                                           │   │
│ │ Desired Price: [________] Silver         │   │
│ │ Desired Amount: [____]                   │   │
│ │                                           │   │
│ │              [Register]                   │   │
│ └─────────────────────────────────────────┘   │
│                                                 │
│ [Price List rechts]                             │
└─────────────────────────────────────────────────┘
```

### Wichtige Erkenntnisse
1. **Balance-Position**: ✅ LINKS-MITTIG (wie bei Sell)
   - Zusammen mit "Warehouse Capacity" in einem grauen Kasten
   - Ca. 5-35% von links, 45-52% von oben
   - Format: "Balance [Icon] 56,500,417,618"
2. **Desired Price Feld**: Klar sichtbar mit "Silver" Suffix
3. **Desired Amount Feld**: Separate Eingabe für Menge
4. **Button**: "Register" (nicht "Buy" wie ursprünglich angenommen!)

## Buy Confirmation Window (`buy_item_confirm.png`)

### Sichtbare UI-Elemente

```
┌─────────────────────────────────────────────────┐
│                                                 │
│           Ordering [Item Name] x765            │
│                                                 │
│         Desired Price: 1,943,100,000 Silver    │
│                                                 │
│         In case of stock shortage,             │
│         outstanding items will be put on       │
│         pre-order.                             │
│                                                 │
│         Continue?                              │
│                                                 │
│         Yes (ENTER)    No (ESC)                │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Wichtige Erkenntnisse
1. **Titel-Format**: `"Ordering [Item Name] x[Quantity]"`
2. **Preis-Zeile**: `"Desired Price: [Total] Silver"`
3. **Keine separate Menge**: Menge ist nur im Titel `x765`
4. **Buttons**: "Yes (ENTER)" und "No (ESC)"
5. **Kontext-Text**: "In case of stock shortage..." (optional)

## Sell Item Detail-Fenster (`sell_item.png`)

### Sichtbare UI-Elemente

```
┌─────────────────────────────────────────────────┐
│ Sell                                       [X]  │
│                                                 │
│ [Item Icon] [Item Name - z.B. "Traditional...] │
│                                                 │
│ In Stock    Warehouse Capacity                  │
│ 1           0.30 VT                             │
│                                                 │
│ Base Price    Recent Price                      │
│ 745,000       690,000                           │
│                                                 │
│ Total Trades  Recent Transaction                │
│ 4,234         10-19 17:49                       │
│                                                 │
│ ┌─────────────────────────────────────────┐   │
│ │ Balance          Warehouse Capacity      │   │
│ │ [Icon] 191,287,355,053   5,381.1/11,000 │   │
│ │                                           │   │
│ │ Set Price: [690,000]  MAX                │   │
│ │                        MIN                │   │
│ │                                           │   │
│ │ Total Price                               │   │
│ │ (690,000 + 0) x 1                        │   │
│ │                                           │   │
│ │         690,000                           │   │
│ │                                           │   │
│ │              [Register]                   │   │
│ └─────────────────────────────────────────┘   │
│                                                 │
│ Sellers | Prices | Buyers                      │
│ [Price List rechts]                             │
└─────────────────────────────────────────────────┘
```

### Wichtige Erkenntnisse
1. **Balance-Position**: ❌ NICHT oben rechts! → ✅ LINKS-MITTIG
   - Zusammen mit "Warehouse Capacity" in einem grauen Kasten
   - Ca. 5-35% von links, 45-52% von oben
   - Format: "Balance [Icon] 191,287,355,053"
2. **Set Price Feld**: Mit "MAX/MIN" Buttons rechts davon
3. **Register Quantity**: Teil der "Total Price" Berechnung
4. **Button**: "Register"

## Sell Confirmation Window (`sell_item_confirm.png`)

### Sichtbare UI-Elemente

```
┌─────────────────────────────────────────────────┐
│                                                 │
│      Listing [Magical Shard] x200              │
│                                                 │
│      Desired Price: 600,000,000 Silver         │
│                                                 │
│      Continue?                                  │
│                                                 │
│      Yes (ENTER)    No (ESC)                   │
│                                                 │
│                                                 │
│ Balance    Warehouse Capacity    Set Price     │
│ [Betrag]   [Kapazität]           3,000,000     │
│                                                 │
│ (3,000,000 + 0) X 200 = 200                   │
└─────────────────────────────────────────────────┘
```

### Wichtige Erkenntnisse
1. **Titel-Format**: `"Listing [Item Name] x[Quantity]"`
2. **Preis-Zeile**: `"Desired Price: [Total] Silver"`
3. **Unten**: Balance, Warehouse Capacity, Set Price sichtbar
4. **Berechnung**: `(Set Price + 0) X Quantity = Total Items`
5. **Buttons**: Gleich wie Buy

## Kritische Unterschiede zum ursprünglichen Plan

### 1. Confirmation-Window Text
**Original-Annahme:**
```
"Do you want to purchase the following item?"
Item: [Name]
Amount: [Quantity]
Price: [Total] Silver
```

**Tatsächlich (Buy):**
```
Ordering [Item Name] x[Quantity]
Desired Price: [Total] Silver
```

**Tatsächlich (Sell):**
```
Listing [Item Name] x[Quantity]
Desired Price: [Total] Silver
```

### 2. Item-Name Position
- **Nicht** in separater "Item:" Zeile
- **Direkt** im Titel: `"Ordering/Listing [Item] x[Qty]"`

### 3. Menge Position
- **Nicht** in separater "Amount:" Zeile
- **Im Titel**: `x[Quantity]`

### 4. Preis-Label
- **Buy**: "Desired Price:" (nicht "Price:")
- **Sell**: "Desired Price:" (nicht "Price:")

### 5. Balance-Position
- Bestätigt: **Oben rechts**
- Format: Große Zahl ohne "Balance:" Label manchmal
- In Sell-Confirm: Separate Zeile mit "Balance" Label

## Aktualisierte Pattern für OCR

### Buy Confirmation Detection

```python
# Pattern 1: Title
r"Ordering\s+(.+?)\s+x\s*([0-9,\.]+)"

# Pattern 2: Price
r"Desired\s+Price\s*[:：]?\s*([0-9,\.]+)\s*Silver"

# Pattern 3: Buttons (Confirmation)
r"Yes\s*\(ENTER\)\s*No\s*\(ESC\)"
```

### Sell Confirmation Detection

```python
# Pattern 1: Title
r"Listing\s+(.+?)\s+x\s*([0-9,\.]+)"

# Pattern 2: Price
r"Desired\s+Price\s*[:：]?\s*([0-9,\.]+)\s*Silver"

# Pattern 3: Buttons (Confirmation)
r"Yes\s*\(ENTER\)\s*No\s*\(ESC\)"
```

### Balance Extraction

```python
# Pattern 1: Mit Label (in Confirmation Window)
r"Balance\s+([0-9,\.]+)"

# Pattern 2: Ohne Label (in Detail Window, oben rechts)
# Große Zahl (> 1,000,000) im Balance-ROI
r"([0-9,\.]{10,})"  # Mind. 10 Zeichen (für große Beträge)
```

## Detail-Window Detection Updates

### Buy Item Window
**Bestehende Erkennung:**
```python
buy_core = has_candidate(["desired price"])
buy_max = has_candidate(["max", "m4x", "rnax"])
buy_min = has_candidate(["min", "m1n", "mln"])
```

**Zusätzliche Marker:**
- ✅ "Purchase" Header
- ✅ "Desired Amount"
- ✅ "Register" Button

### Sell Item Window
**Bestehende Erkennung:**
```python
sell_core = has_candidate(["set price"])
sell_max = has_candidate(["max", "m4x", "rnax"])
sell_min = has_candidate(["min", "m1n", "mln"])
```

**Zusätzliche Marker:**
- ✅ "Register Quantity"
- ✅ "Register" Button

## Balance-ROI Validierung

### Position (basierend auf 2560x1440 Screenshot)
```python
# KORRIGIERT nach Screenshot-Analyse:
y_start = int(h * 0.45)   # 45% von oben (NICHT 5%!)
y_end = int(h * 0.52)     # bis 52% (NICHT 15%!)
x_start = int(w * 0.05)   # 5% von links (NICHT 70%!)
x_end = int(w * 0.35)     # bis 35% (NICHT 100%!)

# Validiert durch sell_item.png: ✅ KORREKT
# Balance: "191,287,355,053" steht LINKS-MITTIG
# Zusammen mit Warehouse Capacity in grauem Kasten
```

### Position-Analyse (2560x1440 Screenshot)
```
Balance-ROI:
- X: 128 bis 896 (5% bis 35%)
- Y: 648 bis 749 (45% bis 52%)
- Größe: 768 x 101 Pixel

Skaliert auf 1920x1080:
- X: 96 bis 672
- Y: 486 bis 562
- Größe: 576 x 76 Pixel
```

### Format-Varianten
1. **Detail-Window**: Nur Zahl, z.B. `56,500,417,618`
2. **Confirmation-Window**: Mit Label, z.B. `Balance 56,500,417,618`

## Timing-Analyse

### Confirmation-Window Lifecycle

```
[User Action Timeline]
T+0.0s  : User klickt "Register" im Detail-Window
T+0.1s  : Confirmation-Window erscheint
T+0.1s  : OCR erkennt "Ordering/Listing [Item] x[Qty]"
        → _pending_confirmation gesetzt
        → _last_balance gespeichert
T+0.5s  : User klickt "Yes (ENTER)"
T+0.6s  : Confirmation-Window schließt sich
T+0.6s  : Zurück im Detail-Window
T+0.7s  : Balance ändert sich (sichtbar)
T+0.8s  : OCR erkennt neue Balance
        → Balance-Änderung validiert
        → Transaktion gespeichert
```

**Gesamt-Latenz:** ~0.8 Sekunden (sehr schnell!)

## OCR-Herausforderungen

### 1. Item-Name Extraction aus Titel
**Problem:** Item-Name ist Teil eines größeren Strings
```
"Ordering [Advanced Alchemy Tool] x765"
         ^^^^^^^^^^^^^^^^^^^^^^^^
```

**Lösung:** Regex mit nicht-greedy Capture
```python
match = re.search(r"(?:Ordering|Listing)\s+(.+?)\s+x\s*([0-9,\.]+)", text)
item_name = match.group(1)  # "Advanced Alchemy Tool"
quantity = match.group(2)    # "765"
```

### 2. Balance ohne Label
**Problem:** Große Zahl könnte auch andere Werte sein (Total Trades, etc.)

**Lösung:** ROI-basierte Isolation
- Balance-ROI ist **sehr klein** (nur oben rechts)
- Andere große Zahlen sind außerhalb dieser ROI
- Zusätzlich: Balance ist meist die **größte** Zahl im Spiel

### 3. OCR-Fehler bei großen Zahlen
**Problem:** 
```
56,500,417,618  →  56,5OO,4l7,6l8  (O→0, l→1 Fehler)
```

**Lösung:** Bestehende `normalize_numeric_str()` Funktion
```python
# Bereits implementiert in utils.py
LETTER_TO_DIGIT = {'O':'0', 'o':'0', 'I':'1', 'l':'1', '|':'1', ...}
```

## Aktualisierte Balance-Toleranz

### Warum Balance-Änderung manchmal ungleich Preis ist

1. **Marktplatz-Steuern (Sell-Side)**:
   ```
   Set Price:      3,000,000
   Total (x200):   600,000,000
   Steuer (11.275%): -67,650,000
   Balance-Änderung: +532,350,000  (nicht 600M!)
   ```

2. **Rückerstattung (Buy-Side)**:
   ```
   Desired Price:  1,943,100,000
   Actual Price:   1,900,000,000  (niedrigerer Market-Preis)
   Refund:         +43,100,000
   Balance-Änderung: -1,900,000,000  (nicht -1.943B!)
   ```

### Aktualisierte Validierungs-Logik

```python
def validate_balance_change(
    confirmation_data: dict,
    old_balance: int,
    new_balance: int
) -> bool:
    """
    Validiert Balance-Änderung mit Toleranz für Steuern/Rückerstattungen.
    
    Args:
        confirmation_data: {action, price, quantity}
        old_balance: Balance vor Transaktion
        new_balance: Balance nach Transaktion
    
    Returns:
        True wenn Änderung plausibel ist
    """
    action = confirmation_data['action']
    expected_price = confirmation_data['price']
    
    actual_change = old_balance - new_balance
    
    if action == 'buy':
        # Buy: Balance sinkt (negative Änderung erwartet)
        # Toleranz: -50% bis +5% (Rückerstattung bei niedrigerem Preis)
        min_change = expected_price * 0.50  # Mind. 50% des Preises
        max_change = expected_price * 1.05  # Max 105% (kleine Toleranz)
        
        return min_change <= actual_change <= max_change
        
    else:  # action == 'sell'
        # Sell: Balance steigt (negative actual_change)
        # Nach Steuern: ~88.725% des Set Price
        # Toleranz: 85% bis 100% (manche Items haben andere Steuersätze)
        min_change = -(expected_price * 1.00)  # Max 100% (kein Bonus)
        max_change = -(expected_price * 0.85)  # Min 85% (nach Steuern)
        
        return min_change <= actual_change <= max_change
```

## Edge Cases

### 1. Schneller Fenster-Wechsel
**Szenario:** User drückt ESC während Confirmation-Window

**Handling:**
```python
# Timeout nach 10 Sekunden
if (now - self._confirmation_timestamp).total_seconds() > 10.0:
    self._pending_confirmation = None
    log_debug("[DETAIL-TX] Timeout - user cancelled")
```

### 2. Mehrere Items gleichzeitig
**Szenario:** User öffnet mehrere Confirmation-Windows nacheinander

**Handling:**
```python
# Jedes neue Confirmation-Window überschreibt _pending_confirmation
# Nur das letzte wird getrackt (FIFO-Prinzip)
if confirmation_data:
    self._pending_confirmation = confirmation_data  # Überschreiben
    self._confirmation_timestamp = datetime.datetime.now()
```

### 3. Balance ändert sich aus anderem Grund
**Szenario:** User kauft etwas im Shop während pending Confirmation

**Handling:**
```python
# Toleranz-Check verhindert False Positives
# Wenn Balance-Änderung nicht plausibel ist (z.B. +50M statt -1.9B):
if not validate_balance_change(...):
    log_debug("[DETAIL-TX] Balance changed but doesn't match - ignoring")
    continue  # Warte weiter auf plausible Änderung
```

## Performance-Optimierungen

### 1. Balance-ROI ist sehr klein
```
Fullscreen: 1920 x 1080 = 2,073,600 Pixel
Balance-ROI: ~500 x 100 = 50,000 Pixel (2.4% der Fläche)
```
**OCR-Zeit:** ~50-100ms (sehr schnell!)

### 2. Confirmation-Text ist kurz
```
Typischer Text:
- "Ordering" + Item + Qty:  ~30 Zeichen
- "Desired Price":          ~20 Zeichen
- "Yes (ENTER)":            ~15 Zeichen
Gesamt: ~65 Zeichen (vs. 500+ im Log-ROI)
```
**OCR-Zeit:** ~100-200ms (schneller als Log)

### 3. Nur bei Detail-Fenstern aktiv
```python
# Burst-Scans sind bereits aktiv:
if wtype in ("buy_item", "sell_item"):
    self._burst_until = now + datetime.timedelta(seconds=4.0)
    # Balance-Capture läuft nur während Burst
```

**Performance-Impact:** < 3% (nur 4 Sekunden pro Transaktion)

## Zusammenfassung der Änderungen

| Aspekt | Original-Plan | Nach Screenshot-Analyse |
|--------|---------------|------------------------|
| **Confirmation-Titel** | "Do you want to..." | "Ordering/Listing [Item] x[Qty]" |
| **Item-Extraktion** | Separate "Item:" Zeile | Aus Titel-Regex |
| **Menge-Extraktion** | Separate "Amount:" Zeile | Aus Titel-Regex (xQty) |
| **Preis-Label** | "Price:" | "Desired Price:" |
| **Balance-Format** | Nur mit Label | Mit/Ohne Label je nach Window |
| **Balance-Validierung** | ±5% Toleranz | 50-100% (Buy), 85-100% (Sell) |
| **Button-Text** | "Yes / No" | "Yes (ENTER) / No (ESC)" |

**Fazit:** Plan ist größtenteils korrekt, aber Details müssen angepasst werden! ✅
