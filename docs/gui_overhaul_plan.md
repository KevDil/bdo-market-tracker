## GUI-Überarbeitung – Implementierungsplan

Dieser Plan basiert auf dem aktuellen Stand von `gui.py` (Stand: 25.10.2025) sowie den Analyse-Notizen in `docs/gui_analyse.txt`. Der Code nutzt nach wie vor überwiegend `pack()`-Layouts, verzichtet auf Tabs, Theme-Anpassungen, Tooltips und Validierungen – sämtliche Punkte aus der Analyse sind also weiterhin relevant. Nachfolgend der Umsetzungsplan mit klaren Arbeitspaketen, betroffenen Dateien und Akzeptanzkriterien.

---

### 1. Layout & Struktur modernisieren

**Ziel:** Reduzieren der visuellen Überlastung und bessere Skalierung.

1.1 `main_container` in `gui.py` auf `grid` oder `pack(fill="both", expand=True")` belassen, aber Hauptsektionen in ein `ttk.Notebook` verschieben.  
&nbsp;&nbsp;• Neue Tabs: `Scan-Steuerung`, `Einstellungen & Status`, `Daten & Analyse`.  
&nbsp;&nbsp;• Frames `region_frame`, `settings_frame`, `status_frame`, `data_frame`, `orders_manager` entsprechend umhängen.  
&nbsp;&nbsp;• `root.grid_rowconfigure/columnconfigure` setzen, damit Fenstergrößenänderungen übernommen werden.

1.2 Innerhalb der Tabs auf `grid()` umstellen (z. B. Buttons nebeneinander, Eingaben mit Labels), inklusive konsistenter `padx/pady` (mind. 8–12 px).  
&nbsp;&nbsp;• Bestehende `tk.Frame`-Container durch `ttk.Frame` ersetzen, um Style-Vererbung zu vereinheitlichen.  
&nbsp;&nbsp;• Regionen-Auswahl: Label + Entry + Buttons in einer `grid`-Zeile mit `weight=1` für Entry.

**Akzeptanzkriterien:**  
- Tabs trennen die bisherigen Sektionen, Fenster lässt sich verkleinern ohne Überlagerungen.  
- Keine Harte-`pack()`-Verkettungen mehr in den Hauptabschnitten.

---

### 2. Styling & Theming ausbauen

**Ziel:** Modernes, konsistentes Erscheinungsbild und Statusfarben.

2.1 Theme erweitern (`start_gui`):  
&nbsp;&nbsp;• definierte Farbpalette (z. B. Primär: `#1E2852`, Akzent: `#4DA3FF`, Warnung: `#FF8C42`).  
&nbsp;&nbsp;• `style.configure` für `TFrame`, `TLabel`, `Accent.TButton`, `Danger.TButton`, `Header.TLabel`, Status-Labels (`Status.Green.TLabel` etc.).  
&nbsp;&nbsp;• Hover-Zustände via `style.map`.

2.2 Health/Status-Anzeige (`update_health_status`) auf Styles statt `fg`-Farben umstellen, Emojis beibehalten.  
2.3 Optionale Dark-Mode-Checkbox, die Hintergrundfarben von `root` und Frames umschaltet (einfacher boolean state, Styles neu konfigurieren).

**Akzeptanzkriterien:**  
- Buttons und Labels nutzen definierte Styles (keine Inline-Farben).  
- Health-Anzeige reagiert mit Style-Wechsel statt direkter `fg`-Manipulation.  
- (Optional) Dark-Mode-Schalter ändert Farbschema live.

---

### 3. UX / Input-Verbesserungen

**Ziel:** Fehlerreduktion, Transparenz.

3.1 Region-Validierung: `_parse_region` Ergebnis in Echtzeit im Entry färben (weiß bei valid, hellrot bei invalid).  
3.2 Tooltips für kritische Controls (Region-Eingabe, Auto-Tracking, GPU-Checkbox, Export) mittels kleiner Tooltip-Hilfsklasse (`tk.Toplevel`, `wm_overrideredirect`).  
3.3 Fortschritts-/Aktionsfeedback:  
&nbsp;&nbsp;• kurzen `ttk.Progressbar` oder Statuslabel einblenden, sobald `tracker.auto_track` gestartet wurde.  
&nbsp;&nbsp;• `messagebox`-Orbit reduzieren, statt dessen `status_var` plus ggf. Toast/Toplevel.

3.4 Hotkeys: `root.bind("<Control-r>", run_single)`, `root.bind("<Control-a>", toggle_auto)`.  
3.5 Fehlerbehandlung im Orders-Manager vereinheitlichen (Statusmeldungen in Statusbar statt nur Messagebox).

**Akzeptanzkriterien:**  
- Ungültige Region-Eingaben ändern Entry-Hintergrund, Buttons bleiben disablebar.  
- Mindestens drei Hauptaktionen besitzen Tooltips.  
- Hotkeys funktionieren und blockieren GUI nicht.

---

### 4. Daten- und Analysebereiche aufwerten

**Ziel:** Schnellere Dateninspektion, visuelle Unterstützung.

4.1 Filterleiste (`filters_row`) komplett auf `grid` + Icons (Unicode oder kleine PNGs) umstellen; Preset-Auswahl nur sichtbar, wenn Modus „Preset wählen“.  
4.2 `view_data()` bzw. Tabellenanzeige:  
&nbsp;&nbsp;• `ttk.Treeview` mit Spaltensortierung (Header-Click).  
&nbsp;&nbsp;• „Export“-Buttons mit Icons (📤 CSV, 📄 JSON).  
4.3 Plots (Preisverlauf) direkt im Hauptfenster anzeigen:  
&nbsp;&nbsp;• `matplotlib`-Canvas in Tab „Analyse“ einbetten, Dropdown für Item-Auswahl.  
&nbsp;&nbsp;• Zoom/Toolbar aktivieren (`NavigationToolbar2Tk`).  
4.4 Orders-Manager (`open_orders_manager`):  
&nbsp;&nbsp;• Spaltenbreiten, Sortierung, Suchfeld.  
&nbsp;&nbsp;• Buttons farblich differenzieren (z. B. `Danger.TButton` für Cancel).

**Akzeptanzkriterien:**  
- Treeview unterstützt Sortierung; Filter-Presets arbeiten ohne Neustart.  
- Ein Plot ist standardmäßig sichtbar, lässt sich aktualisieren.  
- Orders-Manager zeigt aktive/collected/cancelled farbig an, inkl. Suchfeld.

---

### 5. Code-Organisation & Tests

5.1 Hilfsfunktionen (Tooltips, Validierungen, Theme-Switch) in eigenen Abschnitten/Modul (`gui_helpers.py` o. ä.) auslagern, damit `start_gui()` lesbar bleibt.  
5.2 GUI-spezifische Settings (z. B. Default-Farben) in `config.py` oder neuer `gui_config.py` zentralisieren.  
5.3 Manuelle Tests dokumentieren:  
&nbsp;&nbsp;• „Start → Auto-Tracking → Stop“ Workflow.  
&nbsp;&nbsp;• Region-Validierung (valid/invalid).  
&nbsp;&nbsp;• UI-Metrics/Tab-Wechsel bei verschiedenen Fenstergrößen.  
5.4 `docs/gui_analyse.txt` aktualisieren oder durch neues Dokument ersetzen (z. B. `docs/gui_overhaul_plan.md` – dieses Dokument).

**Akzeptanzkriterien:**  
- Keine überlangen Funktionen (>150 Zeilen) in `gui.py`.  
- Dokumentation verweist auf neue Struktur und erklärt Dark-Mode/Shortcuts.  
- Testprotokoll beschreibt mindestens die o. g. Fälle.

---

### Roadmap / Reihenfolge

1. Layout (Tab-Struktur + Grid).  
2. Styling/Theming + Dark Mode.  
3. UX-Verbesserungen (Validierung, Tooltips, Statusmeldungen).  
4. Daten-/Orders-Bereich aufwerten.  
5. Refactoring & Docs/Tests.

Jedes Paket kann separat gemergt werden, solange bestehende Funktionen (Auto-Tracking, Datenexport, Orders-Manager) nach jedem Schritt manuell geprüft werden.

---

### Offene Fragen / Entscheidungen

1. **Dark Mode Pflicht?** – Falls nicht gewünscht, Checkbox entfallen lassen.  
2. **Externe Icon-Fonts?** – Aktuell nur Unicode vorgesehen; könnten später durch PNG/SVG ersetzt werden.  
3. **Notebook/Tab-Reihenfolge** – Ggf. Benutzer-Feedback einholen, ob Analyse-Tab überhaupt nötig ist oder ob eigene Fenster bevorzugt werden.  
4. **Migration zu `customtkinter`?** – Dieses Plan-Dokument bleibt bei Standard-Tkinter; Migration wäre eigenes Projekt.

Bitte Rückmeldung geben, bevor mit Schritt 1 begonnen wird, damit offene Fragen geklärt werden können.
