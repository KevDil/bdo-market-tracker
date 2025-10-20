# Detail-Fenster ROI-Referenz

## Übersicht

Dieses Dokument beschreibt die ROI-Positionen für die Detail-Fenster-Transaktionserkennung basierend auf den markierten Screenshots.

**Referenz-Screenshots**:
- `dev-screenshots/sell_item_marked.png` - Sell-Item-Fenster mit Markierungen
- `dev-screenshots/buy_item_marked.png` - Buy-Item-Fenster mit Markierungen

---

## ROI-Definitionen

### 1. Item-Name-ROI (Grün)

**Position**: Oben links im Detail-Fenster

**Koordinaten** (prozentual vom Frame):
- X: 5-40% der Breite
- Y: 5-20% der Höhe

**Extrahierte Daten**:
- Item-Name (z.B. "Powder of Darkness", "Brutal Death Elixir")
- Optional: Grade-Bracket (z.B. "[Party]")

**Beispiel-Text**:
```
Powder of Darkness
```
oder
```
[Party] Harmony Draught - Human
```

**Implementation**:
```python
def detect_detail_item_name_roi(img):
    h, w = _shape_hw(img)
    x_start = int(w * 0.05)
    x_end = int(w * 0.40)
    y_start = int(h * 0.05)
    y_end = int(h * 0.20)
    return (x_start, y_start, x_end - x_start, y_end - y_start)
```

**Kalibrierungs-Hinweise**:
- Item-Name ist immer zentriert oben links
- Kann mehrzeilig sein bei langen Namen
- Grade-Bracket ist optional (nur bei Special Items)

---

### 2. Balance-ROI (Violett)

**Position**: Mittig links im Detail-Fenster

**Koordinaten** (prozentual vom Frame):
- X: 10-35% der Breite
- Y: 35-50% der Höhe

**Extrahierte Daten**:
- Balance (Kontostand in Silver)

**Beispiel-Text**:
```
Balance: 1,234,567,890 Silver
```

**Implementation**:
```python
def detect_detail_balance_roi(img):
    h, w = _shape_hw(img)
    x_start = int(w * 0.10)
    x_end = int(w * 0.35)
    y_start = int(h * 0.35)
    y_end = int(h * 0.50)
    return (x_start, y_start, x_end - x_start, y_end - y_start)
```

**Kalibrierungs-Hinweise**:
- Balance ist immer im gleichen Format: "Balance: <amount> Silver"
- Kommas als Tausender-Trenner
- Immer auf gleicher Position (Sell und Buy identisch)

---

### 3. Warehouse-ROI (Gelb)

**Position**: Abhängig von Fenstertyp

#### 3.1 Sell-Item-Fenster

**Position**: Relativ weit oben links

**Koordinaten** (prozentual vom Frame):
- X: 5-30% der Breite
- Y: 15-35% der Höhe

**Beispiel-Text**:
```
Warehouse Quantity: 50
```
oder
```
Warehouse: 50
```

#### 3.2 Buy-Item-Fenster

**Position**: Relativ weit unten links

**Koordinaten** (prozentual vom Frame):
- X: 5-30% der Breite
- Y: 65-85% der Höhe

**Beispiel-Text**:
```
Warehouse Quantity: 10
```
oder
```
Warehouse: 10
```

**Implementation**:
```python
def detect_detail_warehouse_roi(img, window_type: str):
    h, w = _shape_hw(img)
    
    if window_type == 'sell_item':
        # Sell-Item: Warehouse oben links
        x_start = int(w * 0.05)
        x_end = int(w * 0.30)
        y_start = int(h * 0.15)
        y_end = int(h * 0.35)
    elif window_type == 'buy_item':
        # Buy-Item: Warehouse unten links
        x_start = int(w * 0.05)
        x_end = int(w * 0.30)
        y_start = int(h * 0.65)
        y_end = int(h * 0.85)
    else:
        return None
    
    return (x_start, y_start, x_end - x_start, y_end - y_start)
```

**Kalibrierungs-Hinweise**:
- Position unterscheidet sich stark zwischen Sell und Buy!
- Format kann variieren: "Warehouse Quantity:" oder nur "Warehouse:"
- Nur Zahl ist relevant, Label kann ignoriert werden

---

## Kalibrierungs-Workflow

### Schritt 1: ROI-Visualisierung

Erstelle visuelle Overlays zur Verifikation der ROI-Positionen:

```powershell
# Sell-Item-Fenster
python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/sell_item_marked.png --type sell_item

# Buy-Item-Fenster
python scripts/utils/calibrate_detail_roi.py --image dev-screenshots/buy_item_marked.png --type buy_item
```

**Output**: `debug/calibrate_sell_item_roi.png`, `debug/calibrate_buy_item_roi.png`

### Schritt 2: Visuelle Verifikation

Prüfe die generierten Overlays:
- ✅ Grünes Rechteck (Item-Name) umschließt den Item-Namen komplett
- ✅ Violettes Rechteck (Balance) umschließt "Balance: ... Silver" komplett
- ✅ Gelbes Rechteck (Warehouse) umschließt "Warehouse Quantity: ..." komplett

### Schritt 3: Feinabstimmung

Falls ROIs nicht korrekt positioniert sind:
1. Öffne `utils.py`
2. Passe prozentuale Koordinaten in `detect_detail_*_roi()` an
3. Wiederhole Schritt 1-2 bis perfekt

### Schritt 4: OCR-Test

Teste OCR-Extraktion mit echtem Detail-Fenster:

```powershell
python analyze_ocr.py --image debug/debug_orig.png --roi item_name
python analyze_ocr.py --image debug/debug_orig.png --roi balance
python analyze_ocr.py --image debug/debug_orig.png --roi warehouse
```

---

## Typische OCR-Fehler & Korrekturen

### Item-Name

**OCR-Fehler**:
- "Powder of Darkness" → "Powder 0f Darkness" (0 statt o)
- "[Party]" → "lPartyl" (l statt [)

**Korrektur**:
- `clean_item_name()` - Entfernt Sonderzeichen
- `correct_item_name()` - Fuzzy-Matching gegen Whitelist

### Balance

**OCR-Fehler**:
- "1,234,567" → "1,234,S67" (S statt 5)
- "Balance:" → "Ba1ance:" (1 statt l)

**Korrektur**:
- `normalize_numeric_str()` - Ersetzt OCR-Confusables (O→0, l→1, S→5)
- Pattern: `Balance\s*[:;]?\s*([0-9,\.]+)\s*Silver`

### Warehouse

**OCR-Fehler**:
- "Warehouse Quantity: 50" → "Warehouse Quantity: SO" (O statt 0)
- "Warehouse:" → "Warehouse :" (extra Space)

**Korrektur**:
- `normalize_numeric_str()` - Ersetzt O→0
- Pattern: `(?:Warehouse\s*(?:Quantity)?|WH)\s*[:;]?\s*([0-9,\.]+)`

---

## ROI-Größen-Referenz

Für einen typischen 1920x1080 Screenshot mit Capture-Region `(734, 371, 1823, 1070)`:

**Frame-Größe**: 1089px Breite × 699px Höhe

### Item-Name-ROI
- X: 54px - 435px (381px breit)
- Y: 35px - 140px (105px hoch)

### Balance-ROI (Sell & Buy identisch)
- X: 109px - 381px (272px breit)
- Y: 245px - 350px (105px hoch)

### Warehouse-ROI (Sell-Item)
- X: 54px - 327px (273px breit)
- Y: 105px - 245px (140px hoch)

### Warehouse-ROI (Buy-Item)
- X: 54px - 327px (273px breit)
- Y: 454px - 594px (140px hoch)

**Hinweis**: Diese Werte sind Beispiele und müssen anhand der tatsächlichen Screenshots kalibriert werden!

---

## Testing-Checkliste

### Unit-Tests
- [ ] `test_detect_detail_item_name_roi()` - ROI-Koordinaten korrekt
- [ ] `test_detect_detail_balance_roi()` - ROI-Koordinaten korrekt
- [ ] `test_detect_detail_warehouse_roi()` - ROI-Koordinaten korrekt (Sell & Buy)
- [ ] `test_extract_item_name()` - Item-Name korrekt extrahiert
- [ ] `test_extract_balance()` - Balance korrekt extrahiert
- [ ] `test_extract_warehouse()` - Warehouse korrekt extrahiert

### Integration-Tests
- [ ] Sell-Item-Fenster: Alle 3 ROIs korrekt erkannt
- [ ] Buy-Item-Fenster: Alle 3 ROIs korrekt erkannt
- [ ] OCR-Fehler werden durch `normalize_numeric_str()` korrigiert
- [ ] Multi-Item-Test: Verschiedene Items funktionieren

### End-to-End-Tests
- [ ] Sell-Transaktion: Item-Name, Balance-Delta, Warehouse-Delta korrekt
- [ ] Buy-Transaktion: Item-Name, Balance-Delta, Warehouse-Delta korrekt
- [ ] Abbruch: Keine Transaktion bei Timeout
- [ ] Duplikat-Prävention: Keine doppelte Speicherung

---

## Troubleshooting

### Problem: Item-Name nicht erkannt

**Symptom**: `metrics['item_name']` ist None oder falsch

**Diagnose**:
```powershell
python analyze_ocr.py --image debug/debug_orig.png --roi item_name
```

**Lösung**:
1. Prüfe ROI-Position mit `calibrate_detail_roi.py`
2. Erweitere Y-Koordinaten falls Name abgeschnitten
3. Prüfe `clean_item_name()` Logik

### Problem: Balance-Wert falsch

**Symptom**: Balance ist 0 oder völlig falsch

**Diagnose**:
```powershell
python analyze_ocr.py --image debug/debug_orig.png --roi balance
```

**Lösung**:
1. Prüfe ob "Silver" im OCR-Text vorkommt
2. Erweitere ROI falls Text abgeschnitten
3. Füge OCR-Confusables zu `normalize_numeric_str()` hinzu

### Problem: Warehouse bei Buy falsch positioniert

**Symptom**: Warehouse-ROI zeigt auf falschen Bereich

**Diagnose**:
Visuelle Prüfung von `debug/calibrate_buy_item_roi.png`

**Lösung**:
1. Prüfe ob `window_type == 'buy_item'` korrekt erkannt wird
2. Passe Y-Koordinaten in `detect_detail_warehouse_roi()` an
3. Buy-Warehouse ist UNTEN links, nicht oben!

---

## Nächste Schritte

Nach erfolgreicher ROI-Kalibrierung:

1. ✅ ROI-Positionen finalisiert
2. ➡️ Implementiere `_extract_detail_window_metrics()`
3. ➡️ Unit-Tests für Metriken-Extraktion
4. ➡️ Integration in `_monitor_detail_window()`
5. ➡️ End-to-End-Tests mit echtem Gameplay
