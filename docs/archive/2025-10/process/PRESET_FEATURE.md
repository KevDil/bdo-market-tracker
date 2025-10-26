# Item Presets Feature - Dokumentation

## Übersicht
Das Item-Presets-System ermöglicht es Benutzern, vordefinierte oder eigene Item-Kombinationen zu erstellen und beim Datenfilter zu verwenden.

## Features

### 1. Vordefinierte Presets
**"Harmony Draught"**: Enthält alle Items zur Herstellung und zum Verkauf von Harmony Draught Elixieren
- Alle Harmony Draught Varianten (Human, Demihuman, Kamasylvia, etc.)
- Alle Elixiere (Brutal Assassin, Death, Carnage, etc.)
- Crafting-Materialien (88 Items total):
  - Mushrooms (Arrow, Cloud, Dwarf, Emperor, Ghost, Sky, Tiger, Truffle, etc.)
  - Saps (Ash, Birch, Cedar, Fir, Maple, Pine, Snowfield Cedar, Thuja)
  - Powders (Darkness, Flame, Time, Black Stone Powder)
  - Blood (Clown's, Fox, Lion, Rhino, Sinner's, Tyrant's, Wise Man's)
  - Reagents & Oils (Pure Powder Reagent, Clear Liquid Reagent, Oils of Corruption/Fortitude/etc.)
  - Misc. Materials (Monk's Branch, Old Tree Bark, Wild Grass, Spirit's Leaf, etc.)

### 2. Filter-Modi
Beim Datenabfragen kann der Benutzer zwischen drei Modi wählen:

- **Alles anzeigen**: Zeigt alle Transaktionen im gewählten Zeitraum
- **Manuelle Eingabe**: Erlaubt Filterung nach Item-Name (LIKE) und Typ (buy/sell)
- **Preset wählen**: Wählt ein vordefiniertes oder benutzerdefiniertes Preset

### 3. Preset-Verwaltung
Über den Button "Presets verwalten" können Benutzer:

- **Neue Presets erstellen**: Name + Items (ein Item pro Zeile)
- **Presets bearbeiten**: Items hinzufügen/entfernen
- **Presets löschen**: Mit Bestätigungsdialog
- **Presets anzeigen**: Liste aller Presets mit Item-Anzahl

## Technische Details

### Datenbank-Schema
```sql
CREATE TABLE item_presets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    items TEXT NOT NULL,  -- JSON-Array
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
```

### Backend-Funktionen (database.py)
```python
get_all_presets() -> list[dict]
get_preset_by_name(name: str) -> dict | None
save_preset(name: str, items: list[str]) -> bool
delete_preset(name: str) -> bool
get_transactions_by_preset(preset_name: str, start_date: str, end_date: str) -> list
```

### GUI-Integration
- Filter-Dropdown in "Daten & Analyse" Section
- Dynamisches Preset-Dropdown (lädt aus DB)
- Preset-Manager Dialog (TreeView + CRUD-Operationen)
- Angepasste `view_data()` Funktion mit SQL IN-Clause für Presets

## Verwendung

### Preset verwenden
1. Im Hauptfenster unter "Daten & Analyse"
2. Filter-Modus: "Preset wählen" auswählen
3. Gewünschtes Preset aus Dropdown wählen
4. Zeitraum (Von/Bis) einstellen
5. "Daten anzeigen" klicken

### Neues Preset erstellen
1. Button "Presets verwalten" klicken
2. Button "Neu" klicken
3. Namen eingeben (z.B. "Meine Elixiere")
4. Items eingeben (ein Item pro Zeile)
5. "Speichern" klicken

### Preset bearbeiten
1. "Presets verwalten" öffnen
2. Preset in Liste auswählen
3. "Bearbeiten" klicken
4. Items anpassen
5. "Speichern" klicken

## Vorteile

- **Effizienz**: Schnelle Filterung häufig analysierter Item-Kombinationen
- **Übersichtlichkeit**: Gruppierung zusammengehöriger Items
- **Flexibilität**: Benutzerdefinierte Presets für individuelle Workflows
- **Persistenz**: Presets überleben Neustarts
- **Performance**: SQL IN-Clause ist effizient auch bei vielen Items

## Beispiel-Workflows

### Elixier-Crafter
Preset "Harmony Draught" verwenden, um:
- Materialkosten zu analysieren (Buy-Transaktionen)
- Verkaufserlöse zu tracken (Sell-Transaktionen)
- Profitabilität zu berechnen (Nettoumsatz)

### Händler
Eigenes Preset mit häufig gehandelten Items erstellen:
- Magical Shards
- Concentrated Magical Black Stone
- Crystal of Void Destruction
- etc.

### Material-Farmer
Preset für Farm-Routen erstellen:
- Alle Mushroom-Typen
- Alle Blood-Typen
- Spezifische Drops

## Erweiterungsmöglichkeiten

- Import/Export von Presets (JSON)
- Preset-Templates (z.B. "Elixier-Herstellung", "Crystal-Trading")
- Preset-Kategorien
- Automatische Preset-Vorschläge basierend auf häufig gefilterten Items
- Preset-Sharing zwischen Benutzern
