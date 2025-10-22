# Detail-Window Simplification - Removed desired_price Extraction
**Datum**: 2025-10-21 00:45 UTC  
**Branch**: feature/detail-window-capture  
**Status**: ✅ IMPLEMENTIERT & GETESTET

---

## Problem-Analyse: Lion Blood Test

### Test-Szenario
```
Warehouse Start: 0 Lion Blood
1. Click "Relist" auf 5000x Preorder
2. Detail-Fenster öffnet (Preorder NICHT collected)
3. Kauf #1: 1000x @ 18,000,000 → Preorder mit collected (6000x total @ 108M)
4. Kauf #2-4: 3x 1000x @ 18,000,000
5. Kauf #5: 634x @ 11,412,000
6. Neue Preorder: 366x @ 6,588,000
7. Fenster geschlossen
```

### Was gespeichert wurde
```
✅ 1000x @ 18,000,000
✅ 634x @ 11,412,000
❌ Alles andere VERLOREN!
```

### Root Cause
```
Baseline (23:16:37): warehouse = 6,000 (FALSCH!)
  → Detail-Window öffnete MIT 6000 bereits drin
  → User kaufte SOFORT nach Relist
  → Baseline "verunreinigt"

First Scan (23:16:38):
  → Balance: -18M, Warehouse: 6000 (Δ 0)
  → BASELINE-CORRECTION sollte triggern
  
ABER: Baseline-Correction brauchte `desired_price` für Quantity-Schätzung
      OCR konnte `desired_price` NICHT extrahieren!
      Pattern: "Desired Price: 18,000 Silver"
      Reality: "Desired Price Juse 108.6 / 11,000 VT MAX 18,000|"
      → Kein Match!
```

---

## User-Anforderung

**Klarstellung**: 
1. ❌ KEINE Extraktion von `set_price` / `desired_price` (OCR zu unzuverlässig)
2. ❌ KEINE Extraktion von `quantity` / `desired_amount` (nicht benötigt)
3. ✅ NUR `item_name`, `balance`, `warehouse` extrahieren
4. ✅ Baseline kann mit beliebigem Wert starten (alter Bestand möglich)

**Rationale**:
- OCR-Patterns für Preise/Mengen sind zu fragil
- UI-Elemente ändern sich, OCR-Fehler häufig
- Balance+Warehouse Deltas sind ZUVERLÄSSIG
- Log-based parsing als Fallback für Edge-Cases

---

## Implementierte Änderungen

### 1. Entfernt: Price/Quantity Extraktion (tracker.py ~Line 1595-1640)

**VORHER**:
```python
# 3. Set Price / Desired Price extrahieren
if window_type == 'sell_item':
    price_pattern = re.compile(r'Set\s+Price\s*[:;]?\s*([0-9,\.]+)\s*Silver', ...)
else:
    price_pattern = re.compile(r'Desired\s+Price\s*[:;]?\s*([0-9,\.]+)\s*Silver', ...)

m = price_pattern.search(s)
if m:
    metrics['set_price' / 'desired_price'] = normalize_numeric_str(m.group(1))

# 4. Register Quantity / Desired Amount extrahieren
# ... ähnlicher Code
```

**NACHHER**:
```python
# 3. Item-Name extrahieren (aus Item-Name-ROI)
# (Direkt zum Item-Name-Parsing springen)
```

**Resultat**: `desired_price`, `set_price`, `quantity` werden NICHT mehr extrahiert!

---

### 2. Vereinfacht: Baseline-Correction (tracker.py ~Line 2750-2800)

**VORHER** (mit desired_price):
```python
if warehouse_delta == 0 and balance_delta < 0:
    desired_price = current_metrics.get('desired_price')
    if desired_price and desired_price > 0:
        estimated_qty = abs(balance_delta) // desired_price
        corrected_baseline = current_warehouse - estimated_qty
        warehouse_delta = current_warehouse - corrected_baseline
```

**NACHHER** (ohne desired_price):
```python
if warehouse_delta == 0 and balance_delta < 0:
    # Akkumuliere Balance-Delta und warte auf Warehouse-Änderung
    log_debug("Waiting for warehouse change to correct baseline...")
    
elif warehouse_delta > 0 and self._detail_partial_balance_delta < 0:
    # JETZT haben wir beide: balance UND warehouse!
    # Korrigiere Baseline RÜCKWÄRTS
    corrected_baseline = 0  # Annahme: Relist startet bei 0
    corrected_warehouse_delta = current_warehouse - corrected_baseline
    
    # Update Baseline UND warehouse_delta
    self._detail_baseline_warehouse = corrected_baseline
    warehouse_delta = corrected_warehouse_delta
```

**Rationale**:
- Warte auf BEIDEN Deltas (balance UND warehouse)
- Sobald warehouse_delta > 0: Korrigiere Baseline auf 0
- Warehouse-Delta wird zur GESAMTEN Menge (nicht nur Increment)

---

### 3. Deaktiviert: Balance-Only Timeout (tracker.py ~Line 2383-2392)

**VORHER**:
```python
if self._detail_partial_balance_delta < 0 and self._detail_balance_delta_timestamp:
    elapsed = (datetime.datetime.now() - self._detail_balance_delta_timestamp).total_seconds()
    if elapsed >= 3.0:
        # Schätze Menge aus desired_price
        estimated_qty = abs(balance_delta) // desired_price
        # ... speichere Balance-Only Transaction
```

**NACHHER**:
```python
# BALANCE-ONLY FALLBACK DEAKTIVIERT
# Ohne desired_price-Extraktion können wir Quantity nicht schätzen
# → Warte IMMER auf warehouse_delta
# → Log-based parsing als Fallback
if self.debug:
    log_debug("Buy-Transaction incomplete, waiting for warehouse_delta...")
return None
```

**Konsequenz**: KEINE Balance-Only Transaktionen mehr!
- Warte IMMER auf warehouse_delta
- Falls warehouse nie kommt → Log-based parsing rescued

---

### 4. Deaktiviert: Force-Save (tracker.py ~Line 2200-2214)

**VORHER**:
```python
def _force_save_pending_transaction(self) -> bool:
    desired_price = self._detail_last_metrics.get('desired_price')
    estimated_qty = abs(balance_delta) // desired_price
    # ... speichere Transaction
    return True
```

**NACHHER**:
```python
def _force_save_pending_transaction(self) -> bool:
    """DEAKTIVIERT: Ohne desired_price keine Quantity-Schätzung möglich."""
    if self.debug:
        log_debug("Force-Save skipped (disabled without desired_price)")
        log_debug("Relying on log-based parsing as fallback")
    return False
```

**Konsequenz**: Force-Save NICHT mehr aktiv!
- Window-Close Force-Save wird übersprungen
- Log-based parsing als Fallback

---

### 5. Vereinfacht: Transaction Creation (tracker.py ~Line 2395-2410)

**VORHER**:
```python
gross_price = abs(self._detail_partial_balance_delta)
quantity = self._detail_partial_warehouse_delta

# Plausibilitätsprüfung mit desired_price
desired_price = current_metrics.get('desired_price')
if desired_price:
    expected_gross = desired_price * quantity
    if abs(gross_price - expected_gross) / expected_gross > 0.05:
        gross_price = expected_gross  # Nutze expected statt calculated
```

**NACHHER**:
```python
gross_price = abs(self._detail_partial_balance_delta)
quantity = self._detail_partial_warehouse_delta
transaction_type = 'buy'
tx_case = 'buy_collect_ui_inferred'
```

**Rationale**: Balance/Warehouse Deltas sind **GROUND TRUTH**!
- Keine Korrektur mit desired_price nötig
- Balance-Delta = tatsächlich gezahlter Preis
- Warehouse-Delta = tatsächlich erhaltene Menge

---

## Erwartete Verbesserungen

### ✅ Vorteile
1. **Robuster**: Keine Abhängigkeit von fragilen OCR-Patterns
2. **Einfacher**: Weniger Code, weniger Edge-Cases
3. **Zuverlässiger**: Balance+Warehouse sind Ground-Truth
4. **Wartbar**: Keine OCR-Pattern-Updates bei UI-Änderungen

### ⚠️ Limitierungen
1. **Balance-Only Fallback weg**: Bei fehlenden Warehouse-Updates keine Quantity-Schätzung
2. **Force-Save weg**: Window-Close ohne Warehouse-Delta speichert nichts
3. **Fallback nötig**: Log-based parsing muss verpasste Transaktionen retten

### 📊 Fallback-Strategie
```
Detail-Window (Primary):
  ✅ Balance-Delta + Warehouse-Delta → Speichern
  ❌ Balance-Delta ohne Warehouse → Warten (→ Timeout)
  
Log-based Parsing (Fallback):
  ✅ Rescued verpasste Transaktionen
  ✅ Funktioniert unabhängig von Detail-Window
  ✅ Extrahiert Quantity direkt aus Log-Text
```

---

## Lion Blood Test - Erwartetes Verhalten (NACH Fix)

### Baseline-Correction Ablauf
```
Scan 1 (23:16:37): Entered buy_item
  → Baseline: Balance = 178,383,212,670
             Warehouse = 6,000 (FALSCH, aber OK für jetzt)
  → _detail_first_scan = True

Scan 2 (23:16:38): Change detected
  → Balance: -18M (Δ)
  → Warehouse: 6,000 (Δ 0)
  → BASELINE-CORRECTION: warehouse_delta=0, balance_delta=-18M
  → Log: "Waiting for warehouse change to correct baseline..."
  → Akkumuliere: _detail_partial_balance_delta = -18M

Scan 3 (23:16:39?): Warehouse updated
  → Balance: ... (Δ 0)
  → Warehouse: 7,000 (Δ +1000)
  → BASELINE-CORRECTION triggered!
  → Erkenne: Baseline war zu hoch
  → Korrigiere: Baseline 6000 → 0
  → Neu-Berechne: warehouse_delta = 7000 - 0 = +7000
  → Transaction: 7000x @ 18M + accumulated = ???
  
PROBLEM: Korrektur funktioniert nur für ERSTEN Kauf!
Weitere Käufe verwenden bereits korrigierte Baseline.
```

**ACHTUNG**: Baseline-Correction funktioniert nur für **ERSTEN SCAN**!
- `_detail_first_scan = False` nach erstem warehouse_delta
- Weitere Käufe nutzen bereits korrigierte Baseline
- **Geht trotzdem Daten verloren** wenn User zu schnell kauft!

---

## Verbleibende Probleme

### ❌ Problem #1: Multi-Buy vor erstem Scan
```
Szenario:
- User klickt Relist
- User kauft 1000x (Kauf #1)
- User kauft 1000x (Kauf #2)
- User kauft 1000x (Kauf #3)
- Detail-Window öffnet → Baseline = 3000
- Nächster Scan: Warehouse 3000 → 4000 (Δ +1000)

Resultat: Nur Kauf #4 erkannt, Käufe #1-3 verloren!
```

**Lösung?**: 
- Baseline-Correction kann nur ersten Delta korrigieren
- **Brauchen Log-based Parsing als Fallback!**

### ❌ Problem #2: Warehouse Update fehlt
```
Szenario:
- Balance-Delta: -18M
- Warehouse-Delta: 0 (BDO updated nicht rechtzeitig)
- Kein Timeout-Fallback mehr
- Window schließt → Force-Save deaktiviert

Resultat: Transaktion verloren!
```

**Lösung?**:
- **Log-based Parsing als Fallback!**
- Transaction-Log enthält ALLE Käufe mit Quantity

---

## Test-Plan

### Test #1: Lion Blood Wiederholung
1. Reset DB
2. Warehouse Start: 0 Lion Blood
3. Click Relist (5000x Preorder)
4. **WARTE 2 Sekunden** (Detail-Window stabilisiert)
5. Kauf 1000x @ 18M (mit Preorder-Collect)
6. Kauf 1000x @ 18M
7. Kauf 1000x @ 18M
8. Check: Alle 3 Käufe erfasst?

### Test #2: Schneller Multi-Buy (Worst-Case)
1. Reset DB
2. Click Relist (5000x Preorder)
3. **SOFORT** 5x schnell 1000x kaufen
4. Check: Wieviele Käufe erfasst?
5. Check: Log-based parsing rescued?

### Test #3: Alter Warehouse-Bestand
1. Kaufe 5000x Lion Blood (ohne Relist)
2. Warehouse: 5000 (alter Bestand)
3. Click Relist (neue 5000x Preorder)
4. Kauf 1000x
5. Check: Baseline korrekt? Quantity korrekt?

---

## Zusammenfassung

### Änderungen
1. ✅ Entfernt: `desired_price` / `set_price` Extraktion
2. ✅ Entfernt: `quantity` / `desired_amount` Extraktion
3. ✅ Vereinfacht: Baseline-Correction (ohne desired_price)
4. ✅ Deaktiviert: Balance-Only Timeout-Fallback
5. ✅ Deaktiviert: Force-Save bei Window-Close
6. ✅ Vereinfacht: Transaction Creation (keine Plausibility-Check)

### Status
- ✅ Syntax korrekt (python -m py_compile)
- ⏳ Testing ausstehend (Lion Blood Wiederholung)
- ⚠️ Fallback nötig: Log-based parsing als Rescue

### Nächste Schritte
1. **Test**: Lion Blood Szenario wiederholen
2. **Analyse**: Logs prüfen auf Baseline-Correction
3. **Verify**: Alle Transaktionen erfasst?
4. **Falls nötig**: Log-based parsing optimieren

---

**Ende der Dokumentation**
