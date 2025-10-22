# BASELINE-CORRECTION FIX - Pig Blood Test Analysis
**Datum**: 2025-10-21 01:00 UTC  
**Branch**: feature/detail-window-capture  
**Status**: ✅ IMPLEMENTIERT

---

## Problem-Analyse: Pig Blood Test

### Test-Szenario
```
Warehouse Start: 0 Pig Blood
1. Click "Relist" auf 5000x Preorder (4131x gefüllt)
2. Detail-Fenster öffnet (Preorder NICHT collected)
3. Kauf #1: 5000x @ 14,560,000 → Preorder mit collected (9131x @ 25,961,560)
4. Kauf #2: 5000x @ 14,803,040
5. Neue Preorder: 5000x @ 13,700,000
6. Fenster geschlossen
```

### Was gespeichert wurde
```
❌ Kauf #1: 9131x @ 25,961,560 (VERLOREN!)
✅ Kauf #2: 5000x @ 14,803,040 (GESPEICHERT)
```

### Root Cause - Timeline-Analyse

**Die ECHTE Timeline**:
```
t=0.0: Click Relist
t=0.1: Detail-Window öffnet → Warehouse sollte 0 sein
t=0.3: Kauf #1 (9131x mit Preorder) → Warehouse = 9131
t=0.5: ERSTER OCR-Scan → Baseline gesetzt:
       Warehouse = 9131 (ZU SPÄT!)
       Balance = 176,296,958,610
       
t=4.5: Kauf #2 (5000x) → Warehouse = 14131, Balance = 176,282,155,570
t=4.6: ZWEITER OCR-Scan → ERSTE "Change detected":
       Balance: 176,296,958,610 → 176,282,155,570 (Δ -14,803,040)
       Warehouse: 9131 → 14131 (Δ +5000)
       
       → Transaction: 5000x @ 14.8M ✅
       → Kauf #1 verloren (war schon in Baseline!)
```

**Log-Evidence**:
```
23:37:05.686904 [DEBUG] [DETAIL] Entered buy_item window
   Balance baseline: 176,296,958,610
   Warehouse baseline: 9,131  ← ZU SPÄT! Sollte 0 sein
   🔧 First-scan correction enabled

23:37:09.295346 [DEBUG] [DETAIL] Change detected in buy_item
   Balance: 176296958610 → 176282155570 (Δ -14,803,040)
   Warehouse: 9131 → 14131 (Δ +5000)
   
   → _detail_first_scan = True
   → BASELINE-CORRECTION sollte triggern
   → ABER: Logik war falsch!
```

---

## Warum die alte Baseline-Correction NICHT funktionierte

### Alte Logik (FALSCH)
```python
if self._detail_first_scan and window_type == 'buy_item':
    if warehouse_delta == 0 and balance_delta < 0:
        # Warte auf warehouse...
        
    elif warehouse_delta > 0 and self._detail_partial_balance_delta < 0:
        # Korrigiere Baseline
        corrected_baseline = 0
```

**Problem**: Bedingung `self._detail_partial_balance_delta < 0` war **FALSCH**!

**Im Pig Blood Test**:
```
ERSTE "Change detected" (23:37:09):
  → warehouse_delta = +5000 ✅
  → balance_delta = -14,803,040 ✅
  → self._detail_partial_balance_delta = 0 ❌ (noch nicht akkumuliert!)
  
  → Bedingung NICHT erfüllt!
  → BASELINE-CORRECTION wurde NICHT triggered!
  → Baseline blieb 9131 (FALSCH!)
```

**Warum `_detail_partial_balance_delta = 0`?**
- Partielle Deltas werden **NACH** Baseline-Correction akkumuliert
- Bei ERSTER Change ist `_detail_partial_balance_delta` immer noch 0
- Bedingung kann niemals erfüllt sein!

---

## Die NEUE Baseline-Correction Logik

### Korrigierte Implementierung
```python
if self._detail_first_scan and window_type == 'buy_item':
    # ERSTER Change nach Window-Open
    
    if self._detail_baseline_warehouse > 0 and warehouse_delta > 0:
        # Baseline war bereits > 0 beim Öffnen UND Warehouse steigt weiter
        # → Baseline wurde zu spät gesetzt (User kaufte bereits vor erstem Scan)
        # → Korrigiere Baseline auf 0
        
        corrected_baseline = 0
        corrected_warehouse_delta = current_warehouse - corrected_baseline
        
        log_debug(f"[DETAIL] 🔧 BASELINE-CORRECTION triggered!")
        log_debug(f"[DETAIL] 🔧 Original baseline: warehouse={self._detail_baseline_warehouse:,}")
        log_debug(f"[DETAIL] 🔧 Reason: Baseline > 0 at window open (scan too late)")
        log_debug(f"[DETAIL] 🔧 Corrected baseline: warehouse=0")
        log_debug(f"[DETAIL] 🔧 Corrected warehouse_delta: +{corrected_warehouse_delta}")
        
        # Update Baseline UND warehouse_delta
        self._detail_baseline_warehouse = corrected_baseline
        warehouse_delta = corrected_warehouse_delta
    
    # Flag deaktivieren nach erstem Change-Scan
    self._detail_first_scan = False
```

### Warum das funktioniert

**Bedingung**: `baseline > 0 AND warehouse_delta > 0`

1. **`baseline > 0`**: 
   - Erster Scan kam zu spät
   - Käufe bereits im Warehouse
   - Sollte 0 sein für Relist

2. **`warehouse_delta > 0`**:
   - ERSTE Change zeigt Warehouse-Increase
   - Bedeutet: Weitere Käufe passieren JETZT
   - Baseline muss korrigiert werden

**KEINE Bedingung für `balance_delta` oder `_detail_partial_balance_delta`!**
- Diese sind bei ERSTER Change noch nicht zuverlässig
- Warehouse-Baseline ist allein ausreichend

---

## Pig Blood Test - Erwartetes Verhalten (NACH Fix)

### Korrigierte Timeline
```
t=0.5: ERSTER OCR-Scan → Baseline:
       Warehouse = 9131
       Balance = 176,296,958,610
       _detail_first_scan = True ✅

t=4.6: ERSTE "Change detected":
       warehouse_delta = +5000 (9131 → 14131)
       balance_delta = -14,803,040
       _detail_first_scan = True ✅
       
       → BASELINE-CORRECTION CHECK:
          ✅ _detail_first_scan = True
          ✅ baseline (9131) > 0
          ✅ warehouse_delta (+5000) > 0
          
       → 🔧 BASELINE-CORRECTION TRIGGERED!
       → Corrected baseline: 0
       → Corrected warehouse_delta: 14131 - 0 = +14131
       
       → Transaction: 14131x @ (accumulated balance_delta)
       → _detail_first_scan = False
```

**Erwartetes Resultat**:
```
✅ Transaction #1: 14131x Pig Blood @ 25,961,560 + 14,803,040 = 40,764,600
   (Kauf #1 + #2 kombiniert)
```

**ABER WAIT**: Balance-Delta ist nur -14,803,040 (Kauf #2)!
- Balance von Kauf #1 (25,961,560) fehlt!
- Diese war VOR erstem Scan, daher nicht in Delta!

---

## Verbleibendes Problem: Balance von Kauf #1

### Das Problem
```
Kauf #1 (t=0.3): 9131x @ 25,961,560
  → Balance: ??? → 176,296,958,610 (nach Kauf)
  → Baseline wurde NACH diesem Kauf gesetzt!
  
Kauf #2 (t=4.5): 5000x @ 14,803,040
  → Balance: 176,296,958,610 → 176,282,155,570
  → Delta: -14,803,040 ✅
```

**Balance-Delta enthält NUR Kauf #2!**
- Kauf #1 Balance ist in Baseline "versteckt"
- Warehouse-Delta korrigiert auf 14131 ✅
- Aber Balance-Delta ist nur 14.8M, nicht 40.7M ❌

### Lösung: Balance muss auch korrigiert werden!

**Wenn Baseline-Correction triggert**:
```python
if self._detail_baseline_warehouse > 0 and warehouse_delta > 0:
    # Korrigiere Warehouse-Baseline
    corrected_baseline_warehouse = 0
    corrected_warehouse_delta = current_warehouse - corrected_baseline_warehouse
    
    # AUCH: Korrigiere Balance-Baseline!
    # Wenn Warehouse zu spät gesetzt wurde, dann Balance auch!
    # Aber wir kennen die "wahre" Balance vor Käufen NICHT...
    
    # PROBLEM: Wir können Balance NICHT korrigieren!
    # → Fallback: Nutze accumulated balance_delta
```

**Konsequenz**: 
- Warehouse-Delta ist korrekt (14131)
- Balance-Delta ist nur partial (14.8M statt 40.7M)
- **Price-per-item wird FALSCH sein!**

---

## Finale Strategie: Log-based Fallback MANDATORY

### Die harte Realität
```
Detail-Window Monitoring KANN NICHT alles erfassen wenn:
1. User kauft SOFORT nach Relist
2. Erster OCR-Scan kommt zu spät
3. Baseline enthält bereits Käufe
4. Balance-Delta kann nicht korrigiert werden
```

### Die Lösung
```
PRIMARY: Detail-Window mit Baseline-Correction
  → Erfasst Warehouse-Delta korrekt
  → Balance-Delta nur partial
  → Transaction hat falsche Price-per-item
  
FALLBACK: Log-based Parsing
  → Liest Transaction-Log aus
  → Extrahiert ALLE Käufe mit korrekten Preisen
  → Dedupe gegen Detail-Window Transactions
  → Rescued verpasste/falsche Transaktionen
```

**Detail-Window ist NICHT ausreichend für Sofort-Käufe!**
- Log-based parsing ist MANDATORY
- Nicht optional, sondern essentiell

---

## Test-Plan (Pig Blood Wiederholung)

### Test #1: Baseline-Correction Verification
```
1. Reset DB
2. Warehouse Start: 0 Pig Blood
3. Click Relist (5000x Preorder)
4. SOFORT: Kauf 5000x (mit Preorder)
5. WARTE 5 Sekunden
6. Kauf 5000x
7. Close Window

Erwartung:
- BASELINE-CORRECTION triggered Logs
- Transaction: ~14000x (beide Käufe kombiniert)
- Price-per-item: WAHRSCHEINLICH FALSCH
```

### Test #2: Mit Pause (Ideal-Fall)
```
1. Reset DB
2. Click Relist (5000x Preorder)
3. WARTE 2 Sekunden (Baseline stabilisiert)
4. Kauf 5000x (mit Preorder)
5. Kauf 5000x
6. Close Window

Erwartung:
- KEINE Baseline-Correction nötig
- 2 separate Transactions
- Beide mit korrekten Preisen
```

### Test #3: Log-based Rescue
```
1. Wie Test #1
2. Check: Detail-Window Transaction falsch?
3. Check: Log-based parsing rescued?
4. Verify: Finale DB hat korrekte Preise?
```

---

## Zusammenfassung

### Implementierte Änderung
```diff
- if warehouse_delta == 0 and balance_delta < 0:
-     # Warte auf warehouse...
- elif warehouse_delta > 0 and self._detail_partial_balance_delta < 0:
-     # Korrigiere Baseline (FALSCHE BEDINGUNG!)

+ if self._detail_baseline_warehouse > 0 and warehouse_delta > 0:
+     # Baseline > 0 at window open AND warehouse increasing
+     # → Scan was too late, correct baseline to 0
+     corrected_baseline = 0
+     warehouse_delta = current_warehouse - corrected_baseline
```

### Was die Änderung behebt
✅ Erkennt "zu späte" Baseline (warehouse > 0 bei window open)
✅ Korrigiert Warehouse-Baseline auf 0
✅ Berechnet warehouse_delta neu (erfasst ALLE Käufe)
✅ Keine falsche Bedingung mehr (`_detail_partial_balance_delta`)

### Was NICHT behoben wird
❌ Balance-Delta bleibt partial (nur Käufe nach erstem Scan)
❌ Price-per-item wird falsch sein (balance / quantity)
❌ Log-based parsing als Fallback NOTWENDIG

### Status
- ✅ Code implementiert
- ✅ Syntax korrekt
- ⏳ Testing ausstehend
- ⚠️ Log-based fallback ist MANDATORY

---

**Ende der Analyse**
