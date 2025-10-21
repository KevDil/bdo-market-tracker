# Lion Blood Test - Problem-Analyse (2025-10-20)

## Test-Szenario

1. Click "Relist" auf 3048x Lion Blood Preorder
2. Detail-Fenster öffnet **OHNE** dass Preorder collected ist
3. Kauf #1: 5000x @ 95,500,000 → Preorder automatisch mit collected (3048x @ 58,216,800)
4. Kauf #2: 5000x @ 95,500,000
5. Kauf #3: 5000x @ 95,500,000  
6. Kauf #4: 5000x @ 95,500,000
7. Neue Preorder gesetzt: 5000x @ 95,500,000
8. Detail-Fenster geschlossen

**Erwartung:** 4-5 Transaktionen (kombiniert oder einzeln)
**Realität:** ❌ **0 Transaktionen gespeichert**

## Was tatsächlich passiert ist

### Warehouse-Baseline und Deltas

```
21:43:10: Warehouse = 23,048 (Baseline gesetzt)
          └─ 20,000 alte Items (schon im Warehouse)
          └─  3,048 Preorder (beim Relist automatisch collected)

21:43:11: Warehouse = 23,048 (keine Änderung)
21:43:12: Balance = -95,500,000 (Kauf #1 erkannt!)
21:43:12: Warehouse = 23,048 (KEINE ÄNDERUNG! ❌)
21:43:12: ERROR: cannot import name 'get_last_ocr_text' ❌
21:43:13: Warehouse = 23,048 (immer noch keine Änderung)
```

### Root Cause #1: Warehouse UI-Update Verzögerung

**Das Kernproblem:** BDO's Detail-Window aktualisiert das **Warehouse-Display NICHT sofort** nach einem Kauf!

Warehouse-Wert bleibt bei 23,048 trotz 4×5000 = 20,000 gekaufter Items:
- Nach Kauf #1: 23048 (sollte 28048 sein)
- Nach Kauf #2: 23048 (sollte 33048 sein)  
- Nach Kauf #3: 23048 (sollte 38048 sein)
- Nach Kauf #4: 23048 (sollte 43048 sein)

**Warehouse-Delta = 0** → Transaktion incomplete → **NICHTS gespeichert**

### Root Cause #2: Import-Fehler

```python
from utils import get_last_ocr_text  # ❌ Funktion existiert nicht!
```

Diese Funktion sollte den letzten OCR-Text für "Placed order" Erkennung liefern, existiert aber nicht in `utils.py`.

**Effekt:**
- Exception bei `_infer_transaction_from_deltas()`
- Transaktion wird abgebrochen
- Keine Fehlermeldung (try/except schluckt es)

### Root Cause #3: Balance-Only Transaktionen nicht unterstützt

Die aktuelle Logik erfordert **BEIDE** Deltas:
```python
if self._detail_partial_balance_delta >= 0 or self._detail_partial_warehouse_delta <= 0:
    return None  # Noch nicht beide Deltas vorhanden
```

Bei Buy:
- `balance_delta < 0` ✅ (Geld ausgegeben)
- `warehouse_delta > 0` ❌ (UI nicht aktualisiert)

→ Transaktion bleibt forever "incomplete"

## Warum Detail-Window-Monitoring fundamental kaputt ist

### Problem: BDO UI ist asynchron und inkonsistent

1. **Balance:** Updates sofort nach Kauf
2. **Warehouse:** Updates verzögert oder gar nicht im Detail-Window
3. **Kombination:** Unmöglich beide Deltas synchron zu erfassen

### Beispiele aus realen Tests

**Powder of Flame (vorheriger Test):**
- Warehouse zeigte 9999 beim Window-Open (Preorder bereits collected)
- Nach Kauf: 14999, 19999 (korrekte Updates) ✅

**Lion Blood (aktueller Test):**
- Warehouse zeigt 23048 beim Window-Open (20000 alt + 3048 preorder)
- Nach 4 Käufen: Immer noch 23048 ❌
- UI aktualisiert NICHT während Detail-Window offen

**Fazit:** Warehouse-Display im Detail-Window ist **unzuverlässig**!

## Korrektur-Strategien (Evaluierung)

### Option 1: Balance-Only Transaktionen erlauben ❌

**Idee:** Speichere Transaktion wenn balance_delta vorhanden, auch ohne warehouse_delta

**Problem:**
- Menge unbekannt (warehouse_delta fehlt)
- Multiple Käufe können nicht unterschieden werden
- 4×5000 würde als 1 Kauf mit unbekannter Menge gespeichert

**Verdict:** ❌ Nicht praktikabel

### Option 2: OCR-Text parsen für Menge ⚠️

**Idee:** Suche "Purchased x5,000" im Log-ROI OCR-Text

**Problem:**
- Log-ROI wird im Detail-Window NICHT gescannt (PERF-QUICK skip)
- Müsste Log-ROI auch bei Detail-Window scannen
- Performance-Impact

**Verdict:** ⚠️ Möglich aber komplex

### Option 3: Detail-Window-Monitoring aufgeben ✅

**Idee:** Verlasse Detail-Window-Monitoring vollständig, nutze nur Log-basiertes Tracking

**Vorteile:**
- Log-basiertes Tracking funktioniert zuverlässig
- Keine UI-Timing-Probleme
- Einfacher und robuster

**Nachteile:**
- Kein Real-Time-Feedback während Käufen
- Muss warten bis Overview-Window geöffnet wird

**Verdict:** ✅ **Beste Lösung für Zuverlässigkeit**

### Option 4: Hybrid-Ansatz ✅✅ (EMPFOHLEN)

**Idee:** 
- Detail-Window-Monitoring für **simple Fälle** (1-2 Käufe, klare Deltas)
- Log-basiertes Tracking als **Fallback und Validierung**
- Beide Quellen deduplizieren intelligent

**Implementation:**
1. Detail-Window versucht Transaktionen zu erfassen
2. Bei fehlenden Deltas/Problemen: Markiere als "pending"
3. Beim Verlassen des Detail-Windows: Parse Log-ROI
4. Dedupliziere Detail-Window vs Log-based Transaktionen

**Vorteile:**
- Best of both worlds
- Fallback bei UI-Problemen
- Real-Time + Zuverlässigkeit

**Verdict:** ✅✅ **Optimal**

## Empfohlener Fix-Plan

### Schritt 1: Fix Import-Fehler (CRITICAL)

**Problem:** `get_last_ocr_text()` existiert nicht

**Lösung:** Entferne den Import, nutze alternativen Ansatz:
```python
# Statt:
from utils import get_last_ocr_text
recent_ocr = get_last_ocr_text() or ""

# Nutze:
recent_ocr = ocr_text  # Bereits als Parameter vorhanden!
```

**Oder:** Parse Log-ROI beim Detail-Window-Exit für "Placed order"

### Schritt 2: Balance-Only Fallback (MEDIUM)

**Problem:** Warehouse-Delta bleibt 0 trotz Käufen

**Lösung:** Erlaube Balance-Only Transaktionen mit geschätzter Menge:

```python
# Wenn nach 5 Sekunden immer noch warehouse_delta = 0:
if self._detail_partial_balance_delta < 0 and self._detail_partial_warehouse_delta == 0:
    # Schätze Menge aus desired_price
    desired_price = current_metrics.get('desired_price')
    if desired_price:
        estimated_qty = abs(self._detail_partial_balance_delta) // desired_price
        if 1 <= estimated_qty <= 5000:
            log_debug(f"[DETAIL] Using balance-only transaction: {estimated_qty}x estimated")
            quantity = estimated_qty
```

### Schritt 3: Log-ROI Backup-Scan (HIGH PRIORITY)

**Problem:** Detail-Window überspringt Log-ROI komplett

**Lösung:** Bei Detail-Window-Exit (window_type wechselt zu overview):
1. Scanne Log-ROI ein letztes Mal
2. Parse alle "Purchased" Einträge seit Detail-Window-Entry
3. Vergleiche mit gespeicherten Detail-Window-Transaktionen
4. Speichere fehlende Transaktionen

**Code-Location:** `_monitor_detail_window()` beim Fenster-Wechsel

### Schritt 4: Timeout-basierte Balance-Only-Saves (FALLBACK)

**Problem:** Käufe verschwinden wenn Detail-Window sofort geschlossen wird

**Lösung:** Nach 3 Sekunden ohne warehouse_delta:
- Speichere Balance-Only-Transaktion mit geschätzter Menge
- Markiere als `tx_case='buy_collect_balance_only'`
- Später deduplizieren mit Log-based-Entries

## Test-Requirements nach Fix

1. **Lion Blood Repeat:** 3048x Preorder + 4×5000x Käufe
   - Erwartung: 4 Transaktionen @ 95,500,000 (oder 1×23048 kombiniert)

2. **Powder of Flame Repeat:** 4999x Preorder + 3×5000x Käufe
   - Erwartung: 3 Transaktionen (mit Placed order detection)

3. **Single Purchase:** 1×5000x ohne Preorder
   - Erwartung: 1 Transaktion, einfacher Fall

4. **Detail-Window sofort schließen:** Kauf + sofort ESC
   - Erwartung: Transaktion trotzdem gespeichert (via Log-Backup)

## Nächste Schritte

1. ✅ **CRITICAL:** Fix `get_last_ocr_text` Import-Fehler
2. ✅ **HIGH:** Implementiere Log-ROI Backup-Scan bei Detail-Window-Exit
3. ⚠️ **MEDIUM:** Implementiere Balance-Only Fallback mit Timeout
4. 📝 **LOW:** Dokumentiere Warehouse-UI-Limitierungen

---

**Status:** Problem analysiert, Fix-Plan erstellt  
**Priorität:** CRITICAL (Detail-Window-Monitoring komplett kaputt)  
**Nächster Test:** Nach Fixes Lion Blood wiederholen
