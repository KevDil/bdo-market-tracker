# Detail-Window Metrics Extraction Bug - Analyse & Fix-Plan

**Datum**: 2025-10-20  
**Status**: 🚨 **KRITISCHER BUG - DETAIL-WINDOW-MONITORING KOMPLETT NON-FUNCTIONAL**

---

## Executive Summary

**Problem**: Detail-Window-Monitoring speichert **KEINE** Transaktionen  
**Root Cause**: `_extract_detail_window_metrics()` kann Metriken nicht parsen → gibt `None` zurück  
**Impact**: **100% Fehlschlag-Rate** - Feature ist komplett nicht funktional

---

## Problem-Beweise

### Test-Szenario
- ✅ Auto-Track aktiviert
- ✅ 2x 5000x Powder of Flame im Buy-Item-Fenster gekauft
- ❌ **0 Transaktionen gespeichert**

### Log-Analyse

#### 1. Window Detection funktioniert
```
2025-10-20T19:23:24.840597 [DEBUG] window='buy_item' -> keine Auswertung
2025-10-20T19:23:25.156909 [DEBUG] window='buy_item' -> keine Auswertung
... (20+ mal wiederholt)
```
✅ `detect_window_type()` erkennt korrekt `'buy_item'`

#### 2. Detail-ROIs werden korrekt extrahiert
```
2025-10-20T19:23:25.777405 [DEBUG] [DETAIL] Extracted detail window metrics:
2025.10.20 19.23 Powder of Flame
Balance 204,793,068,735
10,000 Warehouse Quantity

2025-10-20T19:23:26.801958 [DEBUG] [DETAIL] Extracted detail window metrics:
2025.10.20 19.23 Powder of Flame
Balance 204,782,318,735
10,000 Warehouse Quantity
```
✅ ROI-Extraction funktioniert (sogar Balance-Änderung sichtbar: -10,750,000 Silver)

#### 3. State Machine wird NIE aufgerufen
```
# Erwartete Logs (FEHLEN KOMPLETT):
[DETAIL] Entered buy_item window
[DETAIL] Change detected in buy_item (Δ Balance: -, Δ Warehouse: +)
[DETAIL] ✅ Inferred transaction
```
❌ `_monitor_detail_window()` läuft nicht

---

## Root Cause Analysis

### Code-Flow

```python
# tracker.py, Zeile 722
self.process_ocr_text(full_text)  # full_text enthält Detail-ROI-Metriken

# tracker.py, Zeile 2469
self._monitor_detail_window(wtype, full_text)  # Wird aufgerufen

# tracker.py, Zeile 2278
current_metrics = self._extract_detail_window_metrics(ocr_text, window_type)

if not current_metrics:  # ← HIER IST DAS PROBLEM!
    return  # Funktion bricht sofort ab
```

### Warum gibt `_extract_detail_window_metrics()` None zurück?

#### Test mit echtem OCR-Text
```python
text = '''2025.10.20 19.23 Powder of Flame
Balance 204,793,068,735
10,000 Warehouse Quantity'''

metrics = mt._extract_detail_window_metrics(text, 'buy_item')
# Result: None ❌
```

#### Ursache 1: Balance-Pattern FALSCH

**Code** (Zeile 1544-1547):
```python
balance_pattern = re.compile(
    r'Balance\s*[:;]?\s*([0-9,\.]+)\s*Silver',  # ← ERFORDERT "Silver"!
    re.IGNORECASE
)
```

**Erwartetes Format**: `Balance: 204,793,068,735 Silver`  
**Tatsächliches Format**: `Balance 204,793,068,735` (OHNE "Silver"!)

**Ergebnis**: Pattern matched NICHT → `balance` fehlt in `metrics`

---

#### Ursache 2: Warehouse-Pattern FALSCH

**Code** (Zeile 1554-1557):
```python
warehouse_pattern = re.compile(
    r'(?:Warehouse\s*(?:Quantity)?|WH)\s*[:;]?\s*([0-9,\.]+)',  # ← Erwartet "Warehouse Quantity" DAVOR
    re.IGNORECASE
)
```

**Erwartetes Format**: `Warehouse Quantity: 10,000`  
**Tatsächliches Format**: `10,000 Warehouse Quantity` (REIHENFOLGE UMGEKEHRT!)

**Ergebnis**: Pattern matched NICHT → `warehouse_qty` fehlt in `metrics`

---

#### Ursache 3: Return-Logik

**Code** (Zeile 1638):
```python
return metrics if metrics else None
```

Wenn `metrics == {}` (leer), wird `None` zurückgegeben!

**Resultat**:
- Balance matched nicht → `balance` fehlt
- Warehouse matched nicht → `warehouse_qty` fehlt
- `metrics == {}` (leer)
- `return None`
- `_monitor_detail_window()` bricht bei Zeile 2280 ab:
  ```python
  if not current_metrics:
      return
  ```

---

## OCR-Formatanalyse

### Tatsächliche ROI-Outputs (aus Logs)

#### Detail-Item-Name ROI
```
2025.10.20 19.23 Powder of Flame
```
**Format**: `<Timestamp> <ItemName>`

#### Detail-Balance ROI
```
Balance 204,793,068,735
```
**Format**: `Balance <Betrag>` (OHNE "Silver"!)

#### Detail-Warehouse ROI
```
10,000 Warehouse Quantity
```
**Format**: `<Anzahl> Warehouse Quantity` (Zahl ZUERST!)

### Vergleich: Erwartetes vs. Tatsächliches Format

| Metrik | Erwartet (Code) | Tatsächlich (OCR) | Match? |
|--------|----------------|-------------------|--------|
| Balance | `Balance: 123,456 Silver` | `Balance 123,456` | ❌ Nein |
| Warehouse | `Warehouse Quantity: 50` | `50 Warehouse Quantity` | ❌ Nein |
| Item Name | `<ItemName>` | `2025.10.20 19.23 <ItemName>` | ⚠️ Timestamp davor |

---

## Fix-Strategie

### Phase 1: Regex-Patterns korrigieren (KRITISCH)

#### 1.1 Balance-Pattern anpassen

**ALT** (Zeile 1544-1547):
```python
balance_pattern = re.compile(
    r'Balance\s*[:;]?\s*([0-9,\.]+)\s*Silver',
    re.IGNORECASE
)
```

**NEU**:
```python
balance_pattern = re.compile(
    r'Balance\s*[:;]?\s*([0-9,\.]+)(?:\s*Silver)?',  # "Silver" ist optional
    re.IGNORECASE
)
```

**Begründung**: Detail-ROI liefert kein "Silver", Overview-Windows möglicherweise schon → Pattern muss beide unterstützen

---

#### 1.2 Warehouse-Pattern anpassen

**ALT** (Zeile 1554-1557):
```python
warehouse_pattern = re.compile(
    r'(?:Warehouse\s*(?:Quantity)?|WH)\s*[:;]?\s*([0-9,\.]+)',
    re.IGNORECASE
)
```

**NEU**:
```python
warehouse_pattern = re.compile(
    r'(?:([0-9,\.]+)\s*Warehouse\s*(?:Quantity)?)|'  # Zahl DAVOR (Detail-ROI)
    r'(?:(?:Warehouse\s*(?:Quantity)?|WH)\s*[:;]?\s*([0-9,\.]+))',  # Zahl DANACH (Overview)
    re.IGNORECASE
)
```

**Begründung**: Detail-ROI hat Format `"50 Warehouse Quantity"`, Overview könnte `"Warehouse: 50"` haben

**Wichtig**: Match-Gruppen anpassen!
```python
m = warehouse_pattern.search(s)
if m:
    wh_str = m.group(1) or m.group(2)  # Erste oder zweite Gruppe
    wh_val = normalize_numeric_str(wh_str)
    if wh_val is not None:
        metrics['warehouse_qty'] = wh_val
```

---

#### 1.3 Item-Name-Extraction korrigieren

**Problem**: Timestamp steht im Item-Name-ROI  
**Format**: `2025.10.20 19.23 Powder of Flame`

**Lösung**: Timestamp-Pattern explizit entfernen

**NEU** (vor Item-Name-Loop, nach Zeile 1610):
```python
# Entferne Timestamp-Präfix wenn vorhanden
# Pattern: "2025.10.20 19.23 ItemName" → "ItemName"
s_cleaned = re.sub(
    r'^\d{4}\.\d{2}\.\d{2}\s+\d{2}\.\d{2}\s+',  # Timestamp-Präfix
    '',
    s
)
lines = s_cleaned.split('\n')
```

---

### Phase 2: Validation & Debugging

#### 2.1 Debug-Logging hinzufügen

**In `_extract_detail_window_metrics()` nach Zeile 1638**:
```python
if self.debug:
    log_debug(f"[DETAIL-EXTRACT] Extracted metrics for {window_type}:")
    log_debug(f"   Balance: {metrics.get('balance')}")
    log_debug(f"   Warehouse: {metrics.get('warehouse_qty')}")
    log_debug(f"   Item: {metrics.get('item_name')}")
    log_debug(f"   OCR Preview: {s[:200]}")

return metrics if metrics else None
```

**Nutzen**: Sofort sehen ob Patterns matchen

---

#### 2.2 Early-Return bei leeren Metriken vermeiden

**Problem**: `return metrics if metrics else None` gibt `None` zurück wenn dict leer ist

**Alternative**: Partielle Metriken akzeptieren
```python
# Option 1: Partielle Metriken erlauben (Balance ODER Warehouse reicht)
if 'balance' in metrics or 'warehouse_qty' in metrics:
    return metrics
return None

# Option 2: Nur Balance erforderlich (Warehouse optional)
if 'balance' in metrics:
    return metrics
return None
```

**Empfehlung**: Option 2 (Balance ist Pflicht, Warehouse optional)

**Begründung**: Balance-Änderung ist der Haupt-Indikator für Transaktionen

---

### Phase 3: Integration Tests

#### 3.1 Unit-Test mit echtem OCR-Text

```python
def test_extract_balance_without_silver():
    """Test: Balance wird auch ohne 'Silver' erkannt"""
    text = "Balance 204,793,068,735"
    metrics = tracker._extract_detail_window_metrics(text, 'buy_item')
    assert metrics is not None
    assert metrics['balance'] == 204793068735

def test_extract_warehouse_number_first():
    """Test: Warehouse wird erkannt wenn Zahl zuerst kommt"""
    text = "10,000 Warehouse Quantity"
    metrics = tracker._extract_detail_window_metrics(text, 'buy_item')
    assert metrics is not None
    assert metrics['warehouse_qty'] == 10000

def test_extract_item_name_with_timestamp():
    """Test: Item-Name wird auch mit Timestamp-Präfix erkannt"""
    text = "2025.10.20 19.23 Powder of Flame"
    metrics = tracker._extract_detail_window_metrics(text, 'buy_item')
    assert metrics is not None
    assert 'Powder of Flame' in metrics.get('item_name', '')

def test_extract_combined_real_ocr():
    """Test: Vollständiger OCR-Text von echtem Detail-Fenster"""
    text = """2025.10.20 19.23 Powder of Flame
Balance 204,793,068,735
10,000 Warehouse Quantity"""
    
    metrics = tracker._extract_detail_window_metrics(text, 'buy_item')
    assert metrics is not None
    assert metrics['balance'] == 204793068735
    assert metrics['warehouse_qty'] == 10000
    assert 'Powder of Flame' in metrics.get('item_name', '')
```

---

#### 3.2 Manual E2E Test

1. ✅ Fix implementieren
2. ✅ GUI starten mit Auto-Track
3. ✅ Buy-Item-Fenster öffnen (z.B. Powder of Flame)
4. ✅ **WARTEN** (5 Sekunden) → Baseline sollte gesetzt werden
5. ✅ Kauf durchführen
6. ✅ Prüfe Logs:
   ```
   [DETAIL-EXTRACT] Extracted metrics for buy_item:
      Balance: 204793068735
      Warehouse: 10000
      Item: Powder of Flame
   
   [DETAIL] Entered buy_item window
      Item: Powder of Flame
      Balance baseline: 204793068735
      Warehouse baseline: 10000
   
   [DETAIL] Change detected in buy_item (Δ Balance: -10750000, Δ Warehouse: +5000)
   [DETAIL] ✅ Inferred transaction: buy | Powder of Flame x5000 @ 2,150
   [DETAIL] ✅ Transaction saved successfully to database
   ```
7. ✅ Prüfe DB: `python check_db.py`

---

### Phase 4: Dokumentation

#### 4.1 AGENTS.md Update

**Sektion**: "Parsing, Classification & Inference"

**Hinzufügen**:
```markdown
- Detail-Window-Metriken werden aus drei spezialisierten ROIs extrahiert:
  - Item-Name-ROI liefert Timestamp + Item-Name (z.B. "2025.10.20 19.23 Powder of Flame")
  - Balance-ROI liefert "Balance <Betrag>" (OHNE "Silver"-Suffix)
  - Warehouse-ROI liefert "<Anzahl> Warehouse Quantity" (Zahl ZUERST!)
  
  Die Regex-Patterns in `_extract_detail_window_metrics()` wurden angepasst um diese
  Formate zu unterstützen, auch wenn sie von den Overview-Formaten abweichen.
```

---

#### 4.2 Test-Dokumentation

**Datei**: `tests/manual/test_detail_window_e2e.md`

**Hinzufügen**: Abschnitt "Known OCR Format Variations"

```markdown
## Known OCR Format Variations

### Detail-Window ROI Formats

Die Detail-Window-ROIs liefern abweichende Formate von Overview-Fenstern:

| Metrik | Detail-ROI Format | Overview Format |
|--------|------------------|-----------------|
| Balance | `Balance 123,456` | `Balance: 123,456 Silver` |
| Warehouse | `50 Warehouse Quantity` | `Warehouse: 50` |
| Item Name | `2025.10.20 19.23 ItemName` | `ItemName` (meist) |

Die Extraction-Patterns müssen **BEIDE** Formate unterstützen!

### Regression Test

Wenn `_extract_detail_window_metrics()` geändert wird, IMMER testen mit:

1. ✅ Detail-ROI-Format (ohne "Silver", Zahl zuerst bei Warehouse)
2. ✅ Overview-Format (mit "Silver", Zahl nach bei Warehouse)
3. ✅ Timestamp-Präfix bei Item-Name
```

---

## Implementierungs-Plan

### Phase 1: Code-Fix (30 Minuten)

1. ✅ **Balance-Pattern anpassen** (Zeile 1544)
   - `Silver` optional machen
   
2. ✅ **Warehouse-Pattern anpassen** (Zeile 1554)
   - Beide Reihenfolgen unterstützen (Zahl davor/danach)
   - Match-Gruppen-Handling anpassen
   
3. ✅ **Item-Name-Extraction korrigieren** (Zeile 1610)
   - Timestamp-Präfix entfernen
   
4. ✅ **Debug-Logging hinzufügen** (Zeile 1638)
   - Extrahierte Metriken loggen
   
5. ✅ **Return-Logik anpassen** (Zeile 1638)
   - Balance required, Warehouse optional

---

### Phase 2: Testing (20 Minuten)

1. ✅ **Unit-Tests erstellen**
   - `test_extract_balance_without_silver()`
   - `test_extract_warehouse_number_first()`
   - `test_extract_item_name_with_timestamp()`
   - `test_extract_combined_real_ocr()`
   
2. ✅ **Unit-Tests ausführen**
   ```bash
   python -m pytest tests/unit/test_detail_window_metrics_extraction.py -v
   ```

3. ✅ **Bestehende Tests prüfen**
   ```bash
   python -m pytest tests/unit/test_detail_window_transactions.py -v
   ```

---

### Phase 3: Manual E2E Test (10 Minuten)

1. ✅ GUI starten
2. ✅ Auto-Track aktivieren
3. ✅ 2x Käufe im Detail-Fenster
4. ✅ Logs prüfen → `[DETAIL] Entered buy_item window` sollte erscheinen
5. ✅ DB prüfen → 2 Transaktionen sollten da sein

---

### Phase 4: Dokumentation (10 Minuten)

1. ✅ AGENTS.md aktualisieren
2. ✅ test_detail_window_e2e.md erweitern
3. ✅ Diesen Fix-Plan als historisches Dokument archivieren

---

## Timeline

| Phase | Aufgabe | Dauer | Status |
|-------|---------|-------|--------|
| 1.1 | Balance-Pattern Fix | 5 Min | ⏳ Pending |
| 1.2 | Warehouse-Pattern Fix | 10 Min | ⏳ Pending |
| 1.3 | Item-Name Fix | 5 Min | ⏳ Pending |
| 1.4 | Debug-Logging | 5 Min | ⏳ Pending |
| 1.5 | Return-Logik | 5 Min | ⏳ Pending |
| 2.1 | Unit-Tests erstellen | 10 Min | ⏳ Pending |
| 2.2 | Tests ausführen | 5 Min | ⏳ Pending |
| 2.3 | Bestehende Tests | 5 Min | ⏳ Pending |
| 3 | Manual E2E | 10 Min | ⏳ Pending |
| 4 | Dokumentation | 10 Min | ⏳ Pending |
| **TOTAL** | | **70 Min** | |

---

## Risiko-Analyse

### Kritische Risiken

| Risiko | Wahrscheinlichkeit | Impact | Mitigation |
|--------|-------------------|--------|------------|
| Patterns matchen Overview-Text nicht mehr | Niedrig | Hoch | Beide Formate testen |
| Warehouse-Gruppen-Index falsch | Mittel | Hoch | Explizite Gruppen-Tests |
| Item-Name-Filter zu aggressiv | Niedrig | Mittel | Whitelist-Validation bleibt aktiv |

### Worst-Case-Szenario

**Szenario**: Patterns matchen Overview-Fenster nicht mehr

**Konsequenz**:
- Overview-basierte Transaktions-Erkennung funktioniert weiter (anderer Code-Pfad)
- Nur Detail-Window-Monitoring betroffen
- Kann schnell rollback-ed werden

**Mitigation**:
- Ausführliche Tests mit Overview-OCR-Text
- Beide Formate in Unit-Tests

---

## Success Criteria

### Must-Have (Blocker für Merge)

- ✅ Balance-Pattern matched `"Balance 123,456"` (ohne Silver)
- ✅ Warehouse-Pattern matched `"50 Warehouse Quantity"` (Zahl zuerst)
- ✅ Item-Name wird auch mit Timestamp extrahiert
- ✅ `_extract_detail_window_metrics()` gibt dict zurück (nicht None)
- ✅ Alle bestehenden Unit-Tests (19) bestehen
- ✅ 4 neue Unit-Tests für Format-Varianten bestehen
- ✅ Manual E2E: 2 Käufe → 2 DB-Einträge

### Should-Have (Nice-to-Have)

- ✅ Debug-Logging zeigt extrahierte Metriken
- ✅ AGENTS.md dokumentiert Format-Unterschiede
- ✅ E2E-Test-Guide erweitert um Format-Varianten

---

## Zusammenfassung

### Problem
- ✅ **Identifiziert**: Regex-Patterns in `_extract_detail_window_metrics()` matchen nicht die tatsächlichen ROI-Formate
- ✅ **Root Cause**: Balance erfordert "Silver"-Suffix (nicht vorhanden), Warehouse erwartet falsche Reihenfolge
- ✅ **Impact**: 100% Fehlschlag-Rate – Detail-Window-Monitoring komplett nicht funktional

### Lösung
- 🎯 **Balance-Pattern**: `Silver` optional machen
- 🎯 **Warehouse-Pattern**: Beide Reihenfolgen unterstützen (Zahl davor/danach)
- 🎯 **Item-Name**: Timestamp-Präfix entfernen
- 🎯 **Validation**: Balance required, Warehouse optional
- 🎯 **Testing**: 4 neue Unit-Tests + Manual E2E

### Nächste Schritte
1. ✅ Implementiere Regex-Pattern-Fixes
2. ✅ Erstelle Unit-Tests
3. ✅ Manual E2E Test (2 Käufe im Detail-Fenster)
4. ✅ Update Dokumentation

---

**Status**: ✅ **FIX-PLAN READY TO IMPLEMENT**  
**Geschätzte Fix-Zeit**: **~70 Minuten**  
**Confidence**: **90%**  
**Priorität**: **P0 - KRITISCH** (Feature komplett nicht funktional)
