# Region-Kalibrierung Anleitung

## Problem
Die Screenshot-Region erfasst nicht das Central Market Fenster.

Der Tracker sieht aktuell das **Processing/Crafting UI** statt des Market-Fensters!

---

## Lösung: Region neu kalibrieren

### Schritt 1: Central Market öffnen
1. Starte Black Desert Online
2. Öffne das Central Market (Taste `F5` oder über NPC)
3. Gehe zum **SELL** oder **BUY** Tab (egal welcher)
4. **WICHTIG:** Das Market-Fenster muss **vollständig sichtbar** sein

### Schritt 2: GUI starten
```bash
python gui.py
```

### Schritt 3: Region festlegen
1. Klicke im GUI auf **"Region festlegen"**
2. Das Fenster wird transparent/schwarz
3. Es erscheint eine Anweisung: "Klick auf linke obere Ecke..."

### Schritt 4: Ecken markieren
**Wichtig: Das GESAMTE Market-Fenster erfassen!**

```
┌─────────────────────────────────┐  ← Klick 1: HIER (linke obere Ecke)
│ Central Market        [X]       │     inkl. "Central Market" Text
│ ┌───────┬───────┐               │
│ │ BUY   │ SELL  │ ← Tabs       │
│ └───────┴───────┘               │
│                                  │
│  Item Name           Quantity   │
│  ......................         │
│                                  │
│  Transaction Log:               │
│  2025.10.13 20:24              │
│  Listed Item x100 for ...       │
│  Transaction of Item x50 ...    │
│                                  │
│                                  │
│                                  │
│  [Register] [Cancel]            │
└─────────────────────────────────┘
                                 ↑
                  Klick 2: HIER (rechte untere Ecke)
```

### Schritt 5: Region testen
1. Die Region wird automatisch gespeichert
2. Klicke auf **"Einmal scannen"**
3. Prüfe die Meldung:
   - ✅ Erfolg: "Einzel-Scan abgeschlossen"
   - ❌ Fehler: Region nochmal kalibrieren

### Schritt 6: Auto-Track starten
1. Klicke auf **"Auto-Tracking starten"**
2. Mache eine Test-Transaktion im Spiel:
   - Verkaufe ein Item ODER
   - Kaufe ein Item
3. Warte 5-10 Sekunden
4. Prüfe ob die Transaktion erfasst wurde

---

## Häufige Fehler

### ❌ Fenster zu klein markiert
**Problem:** Nur den Transaction-Log-Bereich markiert  
**Lösung:** Das GESAMTE Market-Fenster inkl. Header erfassen

### ❌ Falsches Fenster erfasst
**Problem:** Processing UI oder anderes Fenster im Weg  
**Lösung:** 
1. Alle anderen UIs schließen (ESC)
2. NUR das Central Market öffnen
3. Region neu kalibrieren

### ❌ Fenster nicht vollständig sichtbar
**Problem:** Market-Fenster teilweise außerhalb des Bildschirms  
**Lösung:** Market-Fenster in die Bildschirmmitte ziehen

### ❌ Window='unknown' in Logs
**Problem:** Region erfasst falschen Bereich  
**Symptome:** 
```
window='unknown' -> keine Auswertung
OCR Text: "Advanced Cooking..." (falsches UI)
```
**Lösung:** Region-Kalibrierung wiederholen

---

## Debugging

### 1. Prüfe Debug-Screenshots
Nach einem Scan werden erstellt:
- `debug_orig.png` - Original-Screenshot
- `debug_proc.png` - Preprocessed Version

**Was sollte zu sehen sein:**
- ✅ Central Market Header
- ✅ BUY/SELL Tabs
- ✅ Item-Liste oder Transaction-Log
- ❌ NICHT: Processing UI, Inventar, Chat, etc.

### 2. Prüfe OCR-Log
```bash
# Letzte 20 Zeilen anzeigen
Get-Content ocr_log.txt -Tail 20

# Nach "window=" suchen
Get-Content ocr_log.txt -Tail 50 | Select-String "window="
```

**Erwartete Ausgabe:**
```
window='sell_overview' -> detected tab=sell
window='buy_overview' -> detected tab=buy
```

**Fehler-Ausgabe:**
```
window='unknown' -> keine Auswertung
```

### 3. Prüfe OCR-Text
Der OCR-Text (in ocr_log.txt) sollte enthalten:
- ✅ "Central Market"
- ✅ "Buy" oder "Sell"
- ✅ "Warehouse" oder "Balance"
- ✅ Timestamps wie "2025.10.13 20:24"
- ✅ "Listed" / "Transaction" / "Purchased"

**NICHT enthalten sein sollte:**
- ❌ "Processing" / "Cooking" / "Alchemy"
- ❌ "Chat" / "Inventory"
- ❌ "Character" / "Quest"

---

## Alternative: Manuelle Konfiguration

Falls die GUI-Methode nicht funktioniert:

1. Öffne `config.py`
2. Finde Zeile 13: `DEFAULT_REGION = (734, 371, 1823, 1070)`
3. Ändere die Werte:
   ```python
   DEFAULT_REGION = (x1, y1, x2, y2)
   ```
   - `x1, y1` = linke obere Ecke (Pixel-Koordinaten)
   - `x2, y2` = rechte untere Ecke (Pixel-Koordinaten)

**Für 1920x1080 Auflösung (Vollbild):**
```python
DEFAULT_REGION = (734, 371, 1823, 1070)  # Standard
```

**Für 2560x1440 Auflösung:**
```python
DEFAULT_REGION = (979, 495, 2431, 1427)  # Hochrechnung
```

4. Speichern und GUI neu starten

---

## Support-Checklist

Wenn es immer noch nicht funktioniert, sammle diese Infos:

- [ ] `debug_orig.png` anschauen - was ist zu sehen?
- [ ] Bildschirmauflösung? (z.B. 1920x1080, 2560x1440)
- [ ] Spiel im Vollbild oder Windowed Mode?
- [ ] Aktuelle Region-Koordinaten aus config.py
- [ ] Letzte 50 Zeilen von ocr_log.txt
- [ ] Window-Detection-Status: "window='unknown'" oder erkannt?

---

**Erstellt:** 2025-10-13  
**Status:** Aktiv  
**Version:** Market Tracker 0.2.4
