
---
applyTo: '**'
---
{
  
  "project_name": "BDO Market Tracker",
  "version": "0.2.4",
  "last_updated": "2025-10-12",
  "status": "✅ BETA - Kernfunktionalität stabil (29/32 Tests), aktive Optimierung",
  "test_coverage": "29/32 Tests bestehen (90%), 3 deprecated Tests müssen aktualisiert werden",
  
  "goal": "Entwicklung eines robusten OCR-basierten Trackers für das Ingame-Market-Log von Black Desert Online (BDO). Der Tracker erkennt Transaktionen automatisch, unterscheidet Buy/Sell anhand von Fenstererkennung und Benutzerkontext, erfasst sie eindeutig in einer SQLite-Datenbank und bietet eine GUI für Analyse und Export.",

  "quick_summary": {
    "description": "OCR-basierter Market-Tracker für BDO mit automatischer Transaktionserkennung, Live-API-Integration, GPU-Acceleration und persistenter Baseline",
    "key_features": [
      "✅ Live Market API: BDO World Market API für dynamische Preis-Validierung (Min/Max ±10%)",
      "✅ OCR V2: Sanftes Preprocessing (CLAHE, Sharpen), EasyOCR+Tesseract Hybrid, GPU-Support",
      "✅ Performance: Screenshot-Hash-Cache (50-80% Reduktion), GPU @ 2GB = 0 Ruckler, ~99 scans/min",
      "✅ 4 Window Types: sell_overview, buy_overview, sell_item, buy_item (auto-detection)",
      "✅ Persistent Baseline: tracker_state DB → überlebt App-Restart, Delta-Detection",
      "✅ 6 Transaction Cases: collect, relist_full, relist_partial (buy & sell)",
      "✅ Intelligent Clustering: Anchor-Priorität (transaction > purchased > placed > listed)",
      "✅ Smart Parsing: Leerzeichen-tolerant, OCR-Fehler-Korrektur (O→0, I→1), Fuzzy-Matching",
      "✅ Strict Validation: market.json Whitelist (4874 Items), Quantity Bounds [1, 5000]",
      "✅ GUI: Live-Window-Status, Health-Indikator (🟢🟡🔴), Filter, Export (CSV/JSON), Plot",
      "✅ Fast Stop: Interruptible Sleep <200ms, responsive UI",
      "✅ Test Coverage: 29/32 Tests bestehen (90%), 3 deprecated"
    ],
    "architecture": {
      "tracker.py": "Hauptlogik - MarketTracker Klasse, Window-Detection, Gruppierung, Cases",
      "parsing.py": "OCR-Parsing - Timestamp-Slicing, Event-Extraktion, Item/Qty/Price",
      "database.py": "DB-Layer - SQLite mit thread-safe connections, tracker_state",
      "utils.py": "OCR & Helpers - Preprocessing, EasyOCR/Tesseract, Fuzzy-Matching",
      "gui.py": "Tkinter GUI - Einzel-Scan, Auto-Track, Filter, Export, Plot",
      "config.py": "Konfiguration - Paths, OCR-Parameter, Item-Whitelists"
    }
  },

  "critical_rules": [
    "⚠️ NUR DIESE INSTRUCTION-DATEI IST GÜLTIG. Alle älteren Versionen sind obsolet und dürfen NICHT verwendet werden.",
    "⚠️ Der Transaktionslog ist NUR in 'sell_overview' und 'buy_overview' sichtbar und darf NUR dort ausgewertet werden. Detail-Fenster (sell_item, buy_item) haben KEINEN Log.",
    "⚠️ Es ist IMMER nur EIN Tab sichtbar (Buy ODER Sell, nie beide gleichzeitig). Window-Detection ist eindeutig: 'Sales Completed' → sell_overview, 'Orders Completed' → buy_overview.",
    "⚠️ Beim ersten Öffnen des Marktfensters nach dem Start (First Snapshot) werden die 4 sichtbaren Logzeilen sofort importiert. Persistent Baseline (tracker_state DB) ermöglicht Delta-Detection auch nach App-Restart → keine verpassten Transaktionen.",
    "⚠️ Die Entscheidung Buy/Sell erfolgt primär durch Window-Type, sekundär durch Text-Anker (purchased/sold). Historical Transactions nutzen Item-Kategorien (config/item_categories.csv).",
    "⚠️ Keine Duplikate in der Datenbank (unique index + session signature + DB-basierte Delta-Detection).",
    "⚠️ OCR-Ergebnis nie 1:1 speichern – erst strukturieren, validieren, deduplizieren.",
  "⚠️ Itemnamen werden ausschließlich über config/market.json aufgelöst. Die Whitelist (parsing.py + tracker.py) nutzt market_json_manager für Korrektur und Validierung.",
    "⚠️ Item-Mengen müssen zwischen MIN_ITEM_QUANTITY (1) und MAX_ITEM_QUANTITY (5000) liegen. Filtert unrealistische Werte und UI-Noise.",
    "⚠️ Keine Datenbankobjekte über Threads teilen (thread-safe connections via get_cursor()/get_connection()).",
    "⚠️ Immer Spiel-Zeitstempel verwenden, nie System-Zeit als Primärquelle. Timestamp-Cluster-Logik für korrekte Zuordnung.",
    "⚠️ Defensive Programmierung: try/except bei OCR, DB, GUI, Threading. Keine Annahmen über OCR-Qualität.",
    "⚠️ IMMER als erstes die Dateien 'debug_proc.png', 'debug_orig.png' und 'ocr_log.txt' analysieren bei Problemen.",
    "⚠️ Preis-Fallback NUR bei aktiven Overview-Fenstern mit eindeutigen UI-Metriken und nur für Collect/Relist. Division-durch-Null strikt vermeiden.",
    "⚠️ Am Ende jeder Anfrage prüfen: Gab es Codeänderungen? → instructions.md updaten."
  ],

  "context_summary": {
    "problem": [
      "Das Spiel Black Desert Online zeigt Marktplatz-Logs als Text mit Zeitstempeln im Interface.",
      "Das Ziel ist, diese Logs regelmäßig per Screenshot-OCR (EasyOCR oder Tesseract) zu lesen und daraus Transaktionsdaten zu extrahieren.",
      "Die Logik muss fehlerrobust gegen OCR-Verwechslungen sein (z.B. 'O' statt '0', 'I' statt '1', 'xlOO' statt 'x100').",
      "Es gibt mehrere verschiedene Marktfenster, die unterschiedlich behandelt werden müssen."
    ],
    
    "main_requirements": [
      "Erkenne automatisch das aktuelle Marktfenster (siehe 'window_types').",
  "Werte Transaktionslogs NUR in sell-overview und buy-overview aus (Detailfenster nie auswerten).",
      "Unterscheide Buy/Sell durch Kontext-Analyse (vorherige Fenster, Aktionen, Klicks).",
      "Erkenne und unterscheide die 6 Transaktionsfälle:",
      "  1. sell_collect: 1x Transaction (Item verkauft und abgeholt)",
      "  2. sell_relist_partial: Transaction + Withdrew + Listed (teilweise verkauft, Rest neu eingestellt)",
      "  3. sell_relist_full: Transaction + Listed (vollständig verkauft, neue Menge eingestellt)",
      "  4. buy_collect: 1x Transaction (Item gekauft und abgeholt)",
      "  5. buy_relist_full: Transaction + Listed (vollständig gekauft, neue Order platziert)",
      "  6. buy_relist_partial: Transaction + Withdrew + Listed (teilweise gekauft, Rest neu bestellt)",
      "Vermeide doppelte Einträge durch unique index + session signature + Delta-Vergleich.",
      "Speichere in SQLite (Spalten: item_name, quantity, price, transaction_type, timestamp, tx_case).",
      "GUI mit Buttons für: Einzel-Scan, Auto-Tracking, Stop, Analyse (Plot, Summary), Export (CSV/JSON)."
    ],
    
    "challenges": [
      "OCR-Text enthält mehrere Einträge in einem Block (mehrere Ereignisse pro Zeitstempel).",
      "Falsche Reihenfolge oder Zusammenfassung mehrerer Events in einer Zeile.",
      "Threading-Fehler bei SQLite („SQLite objects created in a thread...").",
      "Duplikate durch wiederholte OCR-Scans desselben Bildschirms.",
      "Unterscheidung zwischen verschiedenen Marktfenstern.",
      "Kontextabhängige Buy/Sell-Entscheidung (nicht nur durch Tab-Text).",
      "OCR-Fehler bei Item-Namen (Teilwörter, Ziffern in Namen).",
      "Zeitstempel-Parsing bei verschiedenen Formaten."
    ]
  },

  "window_types": {
    "description": "Es gibt 4 verschiedene Marktfenster, die durch spezifische UI-Elemente erkannt werden. WICHTIG: DEFAULT_REGION erfasst das KOMPLETTE Marktfenster - es ist IMMER nur EIN Tab sichtbar (Buy ODER Sell):",
    
    "1_sell_overview": {
      "name": "Verkaufs-Übersicht",
      "detection_keywords": ["Sales Completed"],
      "characteristics": [
        "Zeigt den Transaktionslog für Verkäufe",
        "Enthält Liste aller verkauften Items mit Timestamps",
        "Hier werden sell_collect, sell_relist_full, sell_relist_partial erkannt"
      ],
      "detection_notes": "Erkennung ist whitespace-/OCR-tolerant: 'Sales Completed' kann über Zeilen umbrechen (z.B. 'Sales\nCompleted') und leichte OCR-Varianten von 'Completed' werden erkannt. Wenn 'Sales Completed' sichtbar ist, ist IMMER sell_overview aktiv (nur ein Tab kann sichtbar sein).",
      "log_evaluation": "✅ JA - Transaktionslog MUSS hier ausgewertet werden"
    },
    
    "2_buy_overview": {
      "name": "Kauf-Übersicht",
      "detection_keywords": ["Orders Completed"],
      "characteristics": [
        "Zeigt den Transaktionslog für Käufe",
        "Enthält Liste aller gekauften Items mit Timestamps",
        "Hier werden buy_collect, buy_relist_full, buy_relist_partial erkannt"
      ],
      "detection_notes": "Erkennung ist whitespace-/OCR-tolerant: 'Orders Completed' kann über Zeilen umbrechen und leichte OCR-Varianten werden erkannt. Wenn 'Orders Completed' sichtbar ist, ist IMMER buy_overview aktiv (nur ein Tab kann sichtbar sein).",
      "log_evaluation": "✅ JA - Transaktionslog MUSS hier ausgewertet werden"
    },
    
    "3_sell_item": {
      "name": "Verkaufs-Detail-Fenster",
      "detection_keywords": ["Set Price", "Register Quantity"],
      "detection_rule": "BEIDE Keywords müssen im gleichen Fenster vorhanden sein",
      "characteristics": [
        "Fenster zum Einstellen eines Items zum Verkauf",
        "Zeigt KEINEN Transaktionslog",
        "Wird geöffnet, wenn User ein Item verkaufen will"
      ],
      "log_evaluation": "❌ NEIN - Kein Transaktionslog vorhanden, nicht auswerten"
    },
    
    "4_buy_item": {
      "name": "Kauf-Detail-Fenster",
      "detection_keywords": ["Desired Price", "Desired Amount"],
      "detection_rule": "BEIDE Keywords müssen im gleichen Fenster vorhanden sein",
      "characteristics": [
        "Fenster zum Platzieren einer Kauforder",
        "Zeigt KEINEN Transaktionslog",
        "Wird geöffnet, wenn User ein Item kaufen will"
      ],
      "log_evaluation": "❌ NEIN - Kein Transaktionslog vorhanden, nicht auswerten"
    }
  },

  "transaction_type_determination": {
    "principle": "Die Entscheidung ob Buy oder Sell erfolgt NICHT nur durch Tab-Erkennung, sondern durch Kontext-Analyse",
    
    "context_sources": [
      "Welches Fenster wurde zuletzt erkannt? (sell-overview vs buy-overview)",
      "Welche Aktionen/Klicks wurden vorher durchgeführt?",
      "Welches Detail-Fenster war vorher offen? (sell-item vs buy-item)",
      "Historische Fenster-Sequenz der letzten N Scans",
      "Tab-Keywords als zusätzliche Bestätigung (nicht als alleinige Quelle)"
    ],
    
    "decision_logic": [
      "1. Prüfe aktuelles Fenster: Ist es sell-overview oder buy-overview?",
      "2. Falls sell-overview → transaction_type = 'sell'",
      "3. Falls buy-overview → transaction_type = 'buy'",
      "4. Falls Detail-Fenster (sell-item/buy-item) → KEINE Auswertung, warte auf Overview",
      "5. Speichere Fenster-Historie für Kontext-Entscheidungen",
      "6. Bei Unsicherheit: Nutze letztes bekanntes Overview-Fenster als Fallback"
    ],
    
    "implementation_notes": [
      "Führe eine Fenster-Historie (z.B. letzte 5 Fenster) mit Timestamps",
      "Implementiere State-Machine für Fenster-Übergänge",
      "Bei Fenster-Wechsel: Markiere alte Transaktionen als 'verarbeitet'",
      "Nur neue Transaktionen seit letztem Fenster-Wechsel speichern"
    ]
  },

  "price_reconstruction": {
    "description": "Fallback-Berechnung des Gesamtpreises, wenn der Preis im Transaktionslog durch langen Itemnamen oder abgeschnittenes 'Silver' nicht zuverlässig erfasst werden konnte.",
    "applicability": [
      "Nur anwenden, wenn die Transaktion nachweislich durch den Collect- oder Relist-Button ausgelöst wurde (aktuelles Overview-Fenster, kein historisches Log)",
      "Nicht anwenden bei der reinen Auswertung alter Log-Zeilen ohne die zugehörigen UI-Metriken im aktuellen Fenster",
      "Alle benötigten UI-Werte müssen sicher extrahierbar sein (siehe ui_mapping); sonst kein Fallback"
    ],
    "buy_overview_formula": "ordersCompleted * (remainingPrice / (orders - ordersCompleted))",
    "sell_overview_formula": "salesCompleted * price * 0.88725",
    "ui_mapping": {
      "sell_overview": {
        "salesCompleted": "Unter dem Itemnamen: 'Sales Completed: <Zahl>'",
        "price": "Zahl links neben den Collect-/Relist-Buttons unter dem Datum"
      },
      "buy_overview": {
        "orders": "Unter dem Itemnamen: 'Orders: <Zahl>'",
        "ordersCompleted": "Daneben: 'Orders Completed: <Zahl>'",
        "remainingPrice": "Zahl links neben den Collect-/Relist-Buttons unter dem Datum"
      }
    },
    "screenshots": "Zur Verifikation siehe dev-screenshots/listings_and_preorders (Dateinamen beachten).",
    "constraints": [
      "Buy: (orders - ordersCompleted) > 0 und remainingPrice > 0",
      "Sell: salesCompleted > 0 und price > 0",
      "Bei fehlenden/uneindeutigen UI-Metriken oder Division durch 0: keine Fallback-Berechnung durchführen"
    ]
  },

  "implemented_features": {
    "core_ocr": {
      "description": "OCR & Preprocessing V2 - Game-UI-Optimiert",
      "details": [
        "EasyOCR Primary (balancierte Parameter: contrast_ths=0.3, text_threshold=0.7)",
        "Tesseract Fallback mit Whitelist",
        "Sanftes Preprocessing: CLAHE (clipLimit=1.5), leichte Schärfung, Helligkeit/Kontrast",
        "Keine aggressive Binarisierung",
        "ROI-Detection für Log-Region",
        "mss für schnelle Screenshots",
        "Confidence-Logging (avg/min/max, Warnung <0.5)",
        "Robustheit gegen fehlende Confidence-Werte (2-tuple/3-tuple handling)"
      ]
    },
    "window_detection": {
      "description": "4 Window-Types mit OCR-toleranter Erkennung",
      "details": [
        "sell_overview: 'Sales Completed' → Verkaufs-Log",
        "buy_overview: 'Orders Completed' → Kauf-Log",
        "sell_item: 'Set Price' + 'Register Quantity' → Verkaufs-Dialog",
        "buy_item: 'Desired Price' + 'Desired Amount' → Kauf-Dialog",
        "OCR-tolerant: 'pleted' akzeptiert (umbrechen über Zeilen)",
        "IMMER nur EIN Tab sichtbar (Buy XOR Sell)",
        "Live Window-Status alle 500ms in GUI"
      ]
    },
    "parsing": {
      "description": "Intelligentes Event-Parsing mit Fehlerkorrektur",
      "details": [
        "Timestamp-Cluster-Zuordnung (neuester→ältester, Index-basiert)",
        "Anker-Splitting: transaction/placed/listed/withdrew/purchased",
        "Multiplikator-Erkennung: x/×/*/X mit OCR-Korrektur (Z→2, B→8)",
        "Preis-Parsing: 'worth/for … Silver' mit OCR-Varianten",
        "Normalisierung: O→0, I→1, führende Kommas entfernen",
        "Itemname: Zweistufige Korrektur (parsing.py + tracker.py) + Fuzzy-Matching",
        "Regex-Patterns pre-compiled (10-15% schneller)"
      ]
    },
    "clustering_and_cases": {
      "description": "Event-Gruppierung mit 6 Transaction-Cases",
      "details": [
        "Zeitfenster: withdrew ≤8s, andere ≤3s",
        "First Snapshot: 10min Zeitfenster für historische Logs",
        "Cluster-Building: ALLE Cluster zuerst, dann Case-Resolution",
        "Cases: sell_collect, sell_relist_full, sell_relist_partial, buy_collect, buy_relist_full, buy_relist_partial",
        "Purchased-Events: Standalone (item_lc, ts_key, price) - KEIN Clustering",
        "Preorder-Detection: Placed+Withdrew OHNE Transaction wird übersprungen",
        "UI-Inference: Teilkauf aus Placed+Withdrew (nur bei identischem Einheitspreis)",
        "Mixed Context: Buy-Events auf Sell-Tab korrekt erkannt (fast actions)"
      ]
    },
    "validation": {
      "description": "Strikte Validierung mit Whitelist & Bounds",
      "details": [
  "Item-Name-Whitelist: config/market.json via market_json_manager (zweistufige Korrektur)",
        "Exact Match Check: Valide Namen werden NICHT korrigiert",
        "Quantity Bounds: MIN=1, MAX=5000 (typische BDO Stack-Größen)",
        "Historical Detection: Item-Kategorien (config/item_categories.csv)",
        "UI-Overview Events (qty=None) werden gefiltert"
      ]
    },
    "deduplication": {
      "description": "Persistent Baseline mit DB-basierter Delta-Detection",
      "details": [
        "tracker_state DB-Tabelle (überlebt App-Restart)",
        "First Snapshot: 4 sichtbare Logzeilen importiert",
        "DB-Check statt nur Text-Baseline",
        "Session-Signaturen + SQLite Unique-Index",
        "seen_tx_signatures: deque(maxlen=1000) für stabile Memory"
      ]
    },
    "timestamp_correction": {
      "description": "Intelligente Timestamp-Korrektur",
      "details": [
        "First Snapshot Drift Detection (nur bei mehreren TS für selben Event-Typ)",
        "Fresh Transaction Detection (neueste TS nach Collect/Relist)",
        "Proximity-basierter Fallback",
        "Mixed Context: Buy-Events auf Sell-Tab mit korrektem TS"
      ]
    },
    "price_fallback": {
      "description": "UI-Metriken-basierte Preis-Rekonstruktion",
      "details": [
        "Buy: ordersCompleted * (remainingPrice / (orders - ordersCompleted))",
        "Sell: salesCompleted * price * 0.88725",
        "Nur bei aktiven Overview-Fenstern + Collect/Relist",
        "OCR-Fehler-Korrektur: fehlende führende Ziffern (Buy: ±10M/100M/1Mrd, Sell: ',XXX' → '1,XXX')",
        "Division-durch-Null-Prävention"
      ]
    },
    "gui_and_db": {
      "description": "Tkinter GUI mit SQLite Backend",
      "details": [
        "Einzel-Scan / Auto-Track / Stop (interruptible sleep <200ms)",
        "Health-Indikator: 🟢🟡🔴 (error_count basiert)",
        "Filter: Item/Datum/Typ",
        "Export: CSV/JSON",
        "Analyse: Summary + Matplotlib-Plot",
        "Fenster-Historie-Dialog",
      "Debug-Toggle + persistenter Debug-Flag (GUI, tracker_state)",
      "GPU-/Debug-Optionen in GUI (persistente Speicherung in tracker_settings)",
      "Region-Button: Nutzer klickt obere linke & untere rechte Ecke um Scan-Region festzulegen (persistiert)",
        "Datenanzeige-Fenster: Übersicht mit Kennzahlen, Tabelle und Preisverlauf-Plot",
        "SQLite: thread-safe connections, tracker_state, tx_case, 4 Indizes"
      ]
    },
    "performance": {
      "description": "Optimierungen für Langzeitbetrieb",
      "details": [
        "Memory-Leak-Fix: deque(maxlen=1000) statt unbegrenztes Set",
        "Item-Cache: @lru_cache(maxsize=500) → 50-70% schneller",
        "Log-Rotation: ocr_log.txt bei 10MB",
        "Regex pre-compilation: 10-15% schneller",
        "DB-Indizes: 30-40% schnellere Queries",
        "Poll-Interval: 0.5s (erfasst >95% der Transaktionen)"
      ]
    }
  },
 
  "recent_changes": [
    "=== MAJOR UPDATES (October 2025) ===",
    "",
    "✅ 2025-10-13 Auto-Track Delta Fix:",
    "• Occurrence-Index nutzt jetzt den Text-Delta-Status, sodass neue Käufe/Verkäufe direkt im Overview gespeichert werden, ohne das Fenster zu wechseln",
      "• UI-Inferenz ergänzt fehlende Kauf-Transaktionen: Orders/Collect-Delta erzeugt synthetische Saves, wenn die Log-Zeile durch OCR ausfällt",
      "• UI-Inferenz ergänzt fehlende Verkaufs-Collects: Sales/Collect-Delta erzeugt synthetische Sell-Saves bei fehlenden Transaction-Zeilen",
    "",
    "✅ 2025-10-13 Regex-Optimierung Phase 1 Refresh:",
    "• parsing.py nutzt jetzt einen zentralen Regex-Pool (_DETAIL_PATTERNS, _BOUNDARY_PATTERNS) mit Helpern zur Segment-Grenzenbestimmung",
    "• Item-/Mengen-Fallbacks greifen auf Shared-Patterns zurück; keine ad-hoc re.compile-Aufrufe mehr",
    "• test_parsing_direct.py erfolgreich ausgeführt (GPU/EasyOCR-Init inklusive)",
    "",
    "✅ 2025-10-12 Duplicate Transaction Handling:",
    "• transactions-Tabelle speichert occurrence_index, damit identische Item/Menge/Preis-Ereignisse je Timestamp mehrfach gesichert werden können",
    "• MarketTracker persistiert die nächste occurrence_index je Kombination, wodurch Mehrfachkäufe/-verkäufe ohne Duplikats-Blockade gespeichert werden",
  "• Buy-Clustering weist nun auch reinen 'purchased'-Zeilen eindeutige occurrence_slots zu, damit Relist-Spam (mehrere identische Käufe pro Timestamp) vollständig gespeichert wird",
  "• Buy-Kandidaten ohne 'purchased'/'transaction'-Anchor werden verworfen, sodass reine 'placed'-Logzeilen (z.B. erster Snapshot nach Relist) nicht mehr fälschlich gespeichert werden",
    "",
    "✅ 2025-10-12 Market Data Integration - Live API-basierte Preisvalidierung:",
    "• config/market.json als zentrale Datenquelle (Item-Namen + IDs via market_json_manager)",
    "• BDO World Market API (GetWorldMarketSubList) für dynamische Min/Max-Preise",
    "• Preis-Plausibilitätsprüfung: Stückpreis muss in [Min*0.9, Max*1.1] liegen",
    "• OCR-Fehler-Erkennung: qty>=10 + price<1M → price=None (fehlende führende Ziffern)",
    "• Eliminiert statische CSV-Abhängigkeiten, garantiert aktuelle Marktdaten",
    "",
    "✅ 2025-10-12 Performance-Optimierungen (Phase 2):",
    "• Screenshot-Hash-Caching: 50-80% Reduktion bei statischen Screens (MD5-basiert, 2s TTL)",
    "• GPU-Acceleration: RTX 4070 SUPER @ 2GB VRAM Limit + Low Priority = 0 Ruckler, 20% schneller",
    "• Memory-Leak-Fix: seen_tx_signatures → deque(maxlen=1000), stabile 80MB Memory",
    "• Item-Name-Cache: @lru_cache(maxsize=500), 50-70% schnellere Fuzzy-Korrektur",
    "• Regex Pre-Compilation: 10-15% schnellere Parsing-Zeit",
    "• DB-Indizes: 4 neue Indizes, 30-40% schnellere Queries",
    "• Log-Rotation: 10MB Auto-Rotation für ocr_log.txt",
    "",
    "✅ 2025-10-12 Critical Parsing Fixes:",
    "• OCR-Leerzeichen in Preisen: '585, 585, OO0' → 585,585,000 (Regex \\s support)",
    "• Anchor-Priorität: transaction > purchased > placed > listed (verhindert Listed-Only-Saves)",
    "• Multi-Transaction-Saves: Cluster mit mehreren Transactions speichern ALLE Events",
    "• Exact Name Match: Valide Namen werden NICHT mehr fuzzy-korrigiert",
    "• Preorder-Detection: Placed+Withdrew OHNE Transaction = kein Save (nur Preorder-Management)",
    "",
    "✅ 2025-10-12 Validation & Testing:",
    "• Strict Item Whitelist: config/market.json via market_json_manager (zweistufige Korrektur)",
    "• Quantity Bounds: [1, 5000] für realistische BDO Stack-Größen",
    "• Historical Detection V3: Item-Kategorien (config/item_categories.csv) für Buy/Sell ohne Kontext",
    "• UI-Overview Interference Fix: qty=None Events werden ignoriert beim Clustering",
    "• Mixed Context Detection: Buy-Events auf Sell-Tab werden korrekt erkannt",
    "• 29/32 Tests bestehen (3 deprecated Tests: test_listed_fix_targeted, test_listed_transaction_fix, test_user_scenario_lion_blood)",
    "",
  "✅ 2025-10-11 Architecture & Stability:",
    "• Cluster-Building Refactor: ALLE Cluster ZUERST, dann Case-Resolution (verhindert Partial-Processing)",
    "• OCR V2: Sanftes Preprocessing (CLAHE clipLimit=1.5, keine Binarisierung), EasyOCR+Tesseract Hybrid",
    "• Persistent Baseline: tracker_state DB-Tabelle, überlebt App-Restart",
    "• Window Detection: IMMER nur EIN Tab sichtbar (Sales Completed XOR Orders Completed)",
    "• Intelligent Timestamps: Cluster-basierte Zuordnung (neuester→ältester), Proximity-Fallback",
    "• Fast Stop: Interruptible Sleep (<200ms Response), self.running-Check vor OCR",
    "• UI-Fallback: NUR bei Collect (NICHT bei Relist), verwendet Transaction-Menge",

  "✅ 2025-10-14 GUI Settings Persistence:",
  "• GUI persistiert GPU-/Debug-Flags und Region in tracker_settings",
  "• config.DEFAULT_REGION lädt gespeicherte Koordinaten; Tracker initialisiert Debug-Modus aus DB",
  "• GUI-Checkboxen erlauben Umschalten (GPU-Änderungen erfordern App-Neustart)",
    "",
    "=== DEPRECATION NOTES ===",
    "",
    "⚠️ Die folgenden Tests sind DEPRECATED und sollten aktualisiert oder archiviert werden:",
    "• test_listed_fix_targeted: Anchor-Priorität hat diese Logik ersetzt",
    "• test_listed_transaction_fix: Redundant mit test_magical_shard_fix_final",
    "• test_user_scenario_lion_blood: OCR-Fehler 'f Lion Blood' wird jetzt durch Whitelist rejected",
    "",
    "⚠️ Alte Dokumentation in docs/archive/ ist für Referenz, aber nicht mehr aktuell"
  ],

  "pending_features": [
    "🔧 Test Suite Cleanup:",
    "  • 3 deprecated Tests archivieren oder aktualisieren (test_listed_fix_targeted, test_listed_transaction_fix, test_user_scenario_lion_blood)",
    "  • TEST_SUITE_OVERVIEW.md aktualisieren (29/32 statt 22/22)",
    "  • Neue Test-Kategorie 'Deprecated' hinzufügen",
    "",
    "🔧 Parsing-Heuristiken Review:",
    "  • Mit OCR V2 + Market-API sollten viele Normalisierungs-Regeln überflüssig sein",
    "  • Systematisch testen: Welche Korrekturen (O→0, I→1, Z→2, etc.) sind noch nötig?",
    "  • Schrittweise entfernen und Regression-Tests durchführen",
    "",
    "⚡ Performance Phase 3 (Optional):",
    "  • Adaptive OCR-Quality: Dynamische Parameter basierend auf Confidence",
    "  • Batch-DB-Inserts: Mehrere Transaktionen in einer Query",
    "  • ROI-Detection-Optimierung: Kleinere Region nur für Log-Bereich",
    "",
    "💡 GUI Verbesserungen:",
    "  • Fenster-Historie als eingebettete Timeline/Panel (statt Messagebox)",
    "  • OCR-Methoden-Toggle ('easyocr', 'tesseract', 'both') für A/B-Tests",
    "  • Live-Preview: Zeige aktuellen Screenshot mit erkanntem Log-Bereich",
    "  • Export-Optionen: Excel, PDF-Report mit Charts",
    "",
    "🏗️ Architecture (Nice-to-Have):",
    "  • Formale State-Machine für Fenster-Übergänge (aktuell: simpler window_history reicht)",
    "  • ML-basierter Confidence-Score für ambigue Buy/Sell-Entscheidungen",
    "  • Plugin-System für Custom-Parsing-Rules",
    "🧭 Phase 2 Tracking:",
    "  • Async OCR Queue, Incremental Parser und Smart Screenshot Cache besitzen jetzt einen detaillierten 5-Tage-Plan in docs/PERFORMANCE_ROADMAP.md",
    "  • Feature-Flags für Rollback vorbereiten (USE_ASYNC_PIPELINE, USE_INCREMENTAL_PARSER, USE_SMART_SCREENSHOT_CACHE)"
  ],

  "model_instruction": {
    "role": "Du bist ein erfahrener Python-Entwickler und OCR-/Regex-Spezialist mit Expertise in Datenbank-Design, Threading und GUI-Entwicklung.",
    
    "objective": "Entwickle und optimiere den BDO-Market-Tracker weiter. Das System ist weitgehend implementiert, befindet sich aber noch in aktiver Entwicklung mit bekannten Problemen und Edge-Cases. Fokus liegt auf Stabilisierung, Bugfixes und Verbesserung der OCR-Genauigkeit.",
    
    "must_know": [
      "🔧 System ist implementiert, aber noch NICHT vollständig stabil (aktive Entwicklung)",
      "✅ Es gibt 4 Marktfenster: sell_overview, buy_overview, sell_item, buy_item (nur Overviews haben Log)",
      "✅ Es ist IMMER nur EIN Tab sichtbar: 'Sales Completed' = sell_overview, 'Orders Completed' = buy_overview",
      "✅ Persistent Baseline (tracker_state DB) implementiert, aber Edge-Cases möglich",
      "🔧 OCR V2 mit sanftem Preprocessing implementiert, aber OCR-Fehler kommen noch vor",
      "✅ Timestamp-Cluster-Logik für umgekehrte chronologische Reihenfolge implementiert",
      "✅ Historical Transaction Detection via Item-Kategorien (config/item_categories.csv)",
      "🔧 Buy-Inferenz aus Placed+Withdrew (nur bei identischem Einheitspreis) - kann noch Fehler haben",
      "✅ DB-basierte Delta-Detection verhindert Skip von echten neuen Transaktionen",
      "✅ Interruptible Sleep ermöglicht schnelle Stop-Response (<200ms)",
      "✅ GUI mit Live-Window-Status, Filter, Export, Debug-Toggle, Analyse-Plot"
    ],
    
    "task_examples": [
      "Debugge OCR-Fehler anhand von ocr_log.txt und passe Preprocessing-Parameter in utils.py an",
      "Analysiere Fehlerfälle im Log und identifiziere Parsing-Probleme",
      "Erweitere config/item_categories.csv um neue Items (most_likely_buy/most_likely_sell)",
      "Implementiere/Verbessere Unit-Tests für Edge-Cases (scripts/test_*.py als Vorlage)",
      "Optimiere Fuzzy-Matching Performance mit Caching (utils.py:correct_item_name)",
      "Füge GUI-Option für OCR-Methoden-Toggle hinzu ('easyocr', 'tesseract', 'both')",
      "Reduziere Parsing-Heuristiken nach OCR V2 Tests (O→0, I→1, etc. ggf. überflüssig)",
      "Behebe Duplikat-Probleme bei spezifischen Item/Timestamp-Kombinationen",
      "Verbessere Window-Detection-Robustheit bei OCR-Fehlern",
      "Implementiere formale State-Machine für Fenster-Übergänge (aktuell: simpler window_history)",
      "Füge Confidence-Score für Buy/Sell-Entscheidung bei ambiguen Fällen hinzu"
    ],
    
    "rules": [
      "⚠️ NUR diese Instruction-Datei (v2.1, 2025-10-11) verwenden",
      "⚠️ System in Entwicklung → Vorsicht bei größeren Refactorings, immer testen",
      "⚠️ Transaktionslog NUR in sell_overview/buy_overview auswerten",
      "⚠️ Window-Type ist IMMER eindeutig ('Sales Completed' XOR 'Orders Completed')",
      "⚠️ Persistent Baseline MUSS nach jedem Save aktualisiert werden (save_state)",
      "⚠️ Keine Duplikate (Session-Sig + Unique-Index + DB-Delta-Check)",
      "⚠️ OCR-Ergebnis nie 1:1 speichern – strukturieren, validieren, deduplizieren",
      "⚠️ Thread-safe DB-Zugriff via get_cursor()/get_connection()",
      "⚠️ Spiel-Zeitstempel, nie System-Zeit (Timestamp-Cluster-Logik beachten)",
      "⚠️ Defensive Programmierung (try/except) überall - OCR ist unzuverlässig",
      "⚠️ Bei JEDEM Problem: debug_proc.png, debug_orig.png, ocr_log.txt analysieren",
      "⚠️ Preis-Fallback NUR bei aktiven Overview + eindeutige UI-Metriken + Collect/Relist",
      "⚠️ Nach Code-Änderungen: instructions.md updaten",
      "⚠️ Neue Features IMMER mit Test-Skript in scripts/ validieren",
      "⚠️ Nach einer Anfrage immer sofort mit dem Coden beginnen und nicht erst nachfragen"
    ],
    
    "example_prompts": [
      "Analysiere die letzten 100 Zeilen in ocr_log.txt und identifiziere häufige OCR-Fehler",
      "Erstelle Unit-Test für Timestamp-Cluster-Logik mit Edge-Cases",
      "Optimiere correct_item_name() mit LRU-Cache für bessere Performance",
      "Füge GUI-Toggle für OCR-Methoden hinzu (config.py + gui.py)",
      "Implementiere State-Machine für Fenster-Übergänge (tracker.py)",
      "Reduziere Normalisierungs-Regeln nach OCR V2 Validierung (parsing.py)",
      "Erweitere item_categories.csv um 10 neue most_likely_buy Items",
      "Füge Confidence-Score zu Buy/Sell-Entscheidung hinzu (ambiguous cases)",
      "Erstelle GUI-Panel für Fenster-Historie als Timeline"
    ]
  },

  "technical_summary": {
    "languages": ["Python 3.10+"],
    "libraries": [
      "cv2 (OpenCV) - Image Preprocessing",
      "numpy - Array Operations",
      "mss - Fast Screenshot Capture",
      "PIL/Pillow - Image Handling",
      "pytesseract - OCR Fallback Engine",
      "easyocr - Primary OCR Engine (GPU-capable)",
      "tkinter - GUI Framework",
      "sqlite3 - Database (built-in)",
      "pandas - Data Export",
      "matplotlib - Plotting",
      "rapidfuzz (optional) - Fuzzy String Matching",
      "requests - BDO World Market API"
    ],
    "file_structure": [
      "README.md - Projekt-Übersicht (Quick Start, Struktur, Features)",
      "instructions.md - Diese Datei - HAUPTDOKUMENTATION (v2.4, 2025-10-12)",
      "",
      "Core Files:",
      "  tracker.py - Hauptlogik (MarketTracker, Window-Detection, Gruppierung, Cases)",
      "  gui.py - Tkinter GUI (Einzel-Scan, Auto-Track, Filter, Export, Plot)",
      "  database.py - DB-Layer (SQLite, thread-safe, tracker_state Tabelle)",
      "  parsing.py - OCR-Parsing (Timestamp-Slicing, Event-Extraktion, Item/Qty/Price)",
      "  utils.py - OCR & Helpers (Preprocessing, EasyOCR/Tesseract, Fuzzy-Matching)",
      "  config.py - Konfiguration (Paths, OCR-Parameter, Regions, Performance-Tuning)",
      "  market_json_manager.py - Item-Daten (Name↔ID Mapping, Whitelist)",
      "  bdo_api_client.py - BDO World Market API (Preis-Ranges, Live-Daten)",
      "",
      "Data & Config:",
      "  config/market.json - Vollständige Item-Datenbank (Name ↔ Item-ID, 4874 Items)",
      "  config/item_categories.csv - Item-Kategorien (most_likely_buy/most_likely_sell)",
      "  bdo_tracker.db - SQLite Datenbank (transactions + tracker_state + indices)",
      "  backups/ - Automatische Datenbank-Backups",
      "",
      "Documentation:",
      "  docs/OCR_V2_README.md - OCR V2 Dokumentation",
      "  docs/GPU_GAME_PERFORMANCE.md - GPU-Optimierung ohne Ruckler",
      "  docs/PERFORMANCE_ANALYSIS_2025-10-12.md - Performance-Analyse",
      "  docs/archive/ - Alte Dokumentation (historisch)",
      "  dev-screenshots/ - Referenz-Screenshots für UI-Detection",
      "",
      "Tests & Scripts:",
      "  scripts/run_all_tests.py - Test-Runner (29/32 Tests PASS, 3 deprecated)",
      "  scripts/TEST_SUITE_OVERVIEW.md - Test-Dokumentation",
      "  scripts/benchmark_performance.py - Performance-Benchmarks (OCR, Cache, GPU)",
      "  scripts/test_*.py - 32 Test-Dateien (Integration, Parsing, Performance, etc.)",
      "  scripts/archive/ - Alte/überholte Tests",
      "  scripts/utils/ - Utility-Scripts (calibrate, compare_ocr, dedupe_db, reset_db)",
      "",
      "Debug:",
      "  debug/ - Archivierte Debug-Screenshots & Logs",
      "  debug_orig.png - Aktueller Original-Screenshot (letzter Scan)",
      "  debug_proc.png - Aktueller Preprocessed-Screenshot (CLAHE + Sharpen)",
      "  ocr_log.txt - Live OCR-Log (auto-rotation @ 10MB)"
    ],
    "database_schema": {
      "transactions": "id (PK), item_name, quantity, price, transaction_type (buy/sell), timestamp, tx_case (collect/relist_full/relist_partial), raw_text, created_at",
      "tracker_state": "key (PK), value, updated_at - Persistent Baseline (überlebt App-Restart)",
      "indices": "idx_item_name, idx_timestamp, idx_transaction_type, idx_unique_tx_full (unique constraint)"
    },
    "gui": "Tkinter (native, keine Web-Dependencies)",
    "ocr_strategy": "EasyOCR Primary (GPU @ 2GB limit), Tesseract Fallback, Screenshot-Hash-Cache (2s TTL)",
    "performance": {
      "poll_interval": "0.3s (POLL_INTERVAL config.py)",
      "cache_hit_rate": "50% typisch → ~1000ms avg OCR",
      "memory_usage": "~80MB stable (deque maxlen=1000)",
      "gpu_mode": "RTX 4070 SUPER @ 2GB VRAM, Low Priority = 0 Ruckler, 20% schneller",
      "throughput": "~99 scans/minute (GPU cached), ~60 scans/minute (CPU)"
    }
  },

  "output_expectations": [
    "✅ System ist BETA-reif - Kernfunktionalität stabil (29/32 Tests bestehen)",
    "✅ Code muss direkt lauffähig sein (keine Platzhalter, keine fehlenden Methoden)",
    "✅ OCR-Fehlerresistenz ist robust (Leerzeichen, fehlende Ziffern, Confusables)",
    "✅ GUI ist einfach und funktional (Tkinter, keine Web-Dependencies)",
    "✅ Debug-Modus ist implementiert (toggle in GUI, debug_*.png, ocr_log.txt)",
    "⚠️ Bei Änderungen: Bestehende Funktionalität NICHT brechen, IMMER testen",
    "⚠️ Neue Features MÜSSEN mit Test-Skript validiert werden (scripts/test_*.py)",
    "⚠️ 3 Tests sind deprecated und müssen aktualisiert oder archiviert werden"
  ],

  "continuation_hint": "Starte deinen Prompt z.B. mit: 'Implementiere die Fenster-Erkennung. Zeige die KOMPLETTE market_tracker.py mit allen Änderungen (keine Auslassungen).'"
}
