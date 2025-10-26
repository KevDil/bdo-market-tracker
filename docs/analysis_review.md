# Analyse-Review (Stand: 2025-10-23)

## Überblick
Die folgenden Befunde fassen die bisherigen Erkenntnisse aus der Analyse der Kernmodule (`tracker.py`, `preorder_manager.py`, `utils.py`) zusammen. Ziel ist es, mögliche Logikfehler und Inkonsistenzen nachvollziehbar zu dokumentieren und ihre Auswirkungen einzuschätzen.

## Befunde im Detail

### 1. Preorder-Erkennung (`tracker.py::_detect_preorder_placement()`)
- **Preis-Semantik korrigiert**: Die Pipeline trennt jetzt klar zwischen `preorder_unit_price` (ROI/Fallback) und `preorder_total_price`. Persistiert wird ausschließlich der Totalbetrag, der Unitpreis dient nur zur Plausibilitätsprüfung und Dedupe.
- **Fallback bereinigt**: Balance-basierte Berechnung erzeugt fortan ausschließlich `preorder_total_price`; Doppelzählungen mit Auto-Collect-Korrekturen entfallen.
- **Dedup-Guard erweitert**: Schlüssel enthält Item, Menge, Unit- und Totalpreis. Einträge landen nur bei erfolgreichem DB-Speichern im Cache.

### 2. Listing-Erkennung (`tracker.py::_detect_listing_placement()`)
- **Preis-Semantik vereinheitlicht**: ROI/Fallback liefern Stückpreis, der in einen gerundeten Totalbetrag überführt wird; beide Werte werden für Plausibilitätschecks festgehalten.
- **Dedup-Guard ergänzt**: Analog zur Preorder-Logik – Schlüssel umfasst Item, Menge, Unit- und Totalpreis; Cache aktualisiert sich nur bei erfolgreichem `store_listing()`.

### 3. Detailfenster-Baseline (`tracker.py::_monitor_detail_window()`)
- **Baseline-Caching stabilisiert**: Timestamp wird gesetzt, und der Cache liefert `quantity/price/total` konsistent.
- **Itemnamen-Helfer zentralisiert**: `_safe_correct_item_name()` kapselt jetzt sämtliche Korrekturen. Alle Aufrufer erhalten `(name, valid)` und führen Null-Checks konsequent durch.
- **Sell-Baseline-Risiko offen**: `sell_item` behandelt `warehouse=None` weiter als 0. Für exakte Lagerstände wäre ein erneuter Scan oder separater Branch sinnvoll (ToDo bleibt bestehen).

### 4. Preorder-/Listing-Manager (`preorder_manager.py`)
- **Preisannahme erfüllt**: Dank korrigierter Tracker-Logik landen nun ausschließlich Totalbeträge in `price`. Folgefunktionen (`find_matching_preorder()` usw.) arbeiten dadurch konsistent.

- **Itemnamen normalisiert**: Tracker nutzt ausschließlich `_safe_correct_item_name()` und damit direkt die `(name, valid)`-Semantik des Market-Managers. Die Helper in `utils.py` bleiben für Legacy-Aufrufe bestehen, kollidieren aber nicht mehr.

## Auswirkungen & Risiken
- **Preisfehler behoben**: Preorder- und Listing-Einträge speichern wieder korrekte Totalwerte; Matching und Auto-Collect greifen.
- **Itemnamen konsistent**: Keine Misch-Rückgabewerte oder `[0]`-Indexierungen mehr; Relist-/Fallback-Pfade stabil.
- **Baseline-Rest-Thema**: Sell-Fenster ohne Warehouse-Wert bleibt Risiko (siehe oben).

## Empfohlene Maßnahmen
- **Sell-Baseline prüfen**: Optional zusätzliche Messung einbauen, wenn `warehouse` im ersten Scan fehlt (nur Sell-Fenster).
- **UI-Delta-Validierung beobachten**: Neue Preis-/Unit-Checks bei UI-inferierten Käufen/Verkäufen erzeugen ggf. neue Edge-Cases – Regressionstests ergänzen.

## Offene Punkte
- Auswirkungen auf weitere Module (`gui.py`, `parsing.py`, `database.py`) wurden erneut geprüft – keine zusätzlichen Anpassungen erforderlich, solange Totalpreis-Semantik beibehalten wird.
- `sell_item`-Baseline-Verbesserung (siehe Punkt 3) bleibt als potenzielles Enhancement offen.

---
*Erstellt von Cascade (agentische Analyseunterstützung).*  
*Aktualisiert: 2025-10-23 nach Umsetzung der Preorder/Listings-Fixes.*
