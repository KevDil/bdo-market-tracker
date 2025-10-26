from __future__ import annotations

import tkinter as tk
import threading
import time
from tkinter import messagebox, ttk
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import datetime
from utils import log_debug 
import torch

from gui_config import (
    PALETTE_LIGHT,
    PALETTE_DARK,
    DEFAULT_THEME,
    LAYOUT,
    PLOT_SETTINGS,
)
from gui_helpers import (
    Palette,
    ThemeManager,
    Tooltip,
    parse_region_text,
    make_treeview_sortable,
    bind_hotkey,
)

from tracker import MarketTracker
from config import (
    DEFAULT_REGION,
    USE_GPU,
    get_capture_region,
    get_dark_mode,
    get_debug_mode,
    get_use_gpu,
    set_capture_region,
    set_dark_mode,
    set_debug_mode,
    set_use_gpu,
)
from database import conn, get_connection
from database import (
    get_all_presets,
    get_preset_by_name,
    save_preset,
    delete_preset,
    get_cursor,
)


# -----------------------
# GUI
# -----------------------
class MarketTrackerGUI:
    HEALTH_POLL_MS = 500
    ORDERS_REFRESH_MS = 4000

    def __init__(self, tracker: MarketTracker) -> None:
        self.tracker = tracker
        self.root = tk.Tk()
        self.root.title("BDO Market Tracker")
        self.root.geometry("960x760")
        self.root.minsize(720, 640)
        try:
            self.root.iconbitmap("config/icon.ico")
        except tk.TclError:
            pass

        saved_dark = get_dark_mode(DEFAULT_THEME == "dark")
        self.dark_mode_var = tk.BooleanVar(value=saved_dark)
        self._setup_theme(initial_dark=saved_dark)

        current_region = get_capture_region(DEFAULT_REGION)
        self.tracker.region = current_region

        self.use_gpu_var = tk.BooleanVar(value=get_use_gpu(USE_GPU))
        self.debug_var = tk.BooleanVar(value=tracker.debug)
        self.status_var = tk.StringVar(value="Status: Idle")
        self.health_status_var = tk.StringVar(value="🟢 Healthy")
        self.window_status_var = tk.StringVar(value="Fenster: -")
        self.mode_var = tk.StringVar(value=f"Modus: {'GPU' if torch.cuda.is_available() else 'CPU'}")
        self.status_bar_var = tk.StringVar(value="Bereit.")
        self.region_var = tk.StringVar(value=",".join(map(str, current_region)))

        self._latest_df: pd.DataFrame | None = None
        self._orders_refresh_job: str | None = None
        self._order_filter_job: str | None = None
        self._region_valid = True

        self._build_layout()
        self._bind_shortcuts()
        self._load_presets()
        self.load_transactions()
        self._refresh_orders()
        self.update_health_status()
        self._schedule_orders_refresh()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def start(self) -> None:
        self.root.mainloop()

    # ------------------------------------------------------------------
    # Setup & Layout
    # ------------------------------------------------------------------
    def _setup_theme(self, initial_dark: bool = False) -> None:
        self.style = ttk.Style()
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.palettes = {
            "light": Palette.from_dict(PALETTE_LIGHT),
            "dark": Palette.from_dict(PALETTE_DARK),
        }

        self.theme_manager = ThemeManager(
            self.root,
            self.style,
            {name: palette for name, palette in self.palettes.items()},
            default=DEFAULT_THEME,
        )
        initial_theme = "dark" if initial_dark else DEFAULT_THEME
        self.theme_manager.apply(initial_theme)
        self.dark_mode_var.set(initial_theme == "dark")

    def _build_layout(self) -> None:
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        padding = LAYOUT["padding"]
        self.main_container = ttk.Frame(self.root, padding=padding, style="Root.TFrame")
        self.main_container.grid(row=0, column=0, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(1, weight=1)

        header = ttk.Frame(self.main_container, style="Root.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        ttk.Label(header, text="BDO Market Tracker", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="Live-OCR Tracker mit GPU-Optionen und Datenanalyse",
            style="SubHeader.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.notebook = ttk.Notebook(self.main_container)
        self.notebook.grid(row=1, column=0, sticky="nsew", pady=(LAYOUT["tab_padding"][0], 0))

        self.control_tab = ttk.Frame(self.notebook, padding=LAYOUT["tab_padding"])
        self.settings_tab = ttk.Frame(self.notebook, padding=LAYOUT["tab_padding"])
        self.analysis_tab = ttk.Frame(self.notebook, padding=LAYOUT["tab_padding"])
        self.orders_tab = ttk.Frame(self.notebook, padding=LAYOUT["tab_padding"])

        self.notebook.add(self.control_tab, text="Scan-Steuerung")
        self.notebook.add(self.settings_tab, text="Einstellungen & Status")
        self.notebook.add(self.analysis_tab, text="Daten & Analyse")
        self.notebook.add(self.orders_tab, text="Orders")

        self._build_control_tab()
        self._build_settings_tab()
        self._build_analysis_tab()
        self._build_orders_tab()

        status_bar = ttk.Frame(self.main_container, padding=(0, 6))
        status_bar.grid(row=2, column=0, sticky="ew")
        status_bar.grid_columnconfigure(0, weight=1)
        self.status_bar_label = ttk.Label(status_bar, textvariable=self.status_bar_var, anchor="w")
        self.status_bar_label.grid(row=0, column=0, sticky="ew")

    def _build_control_tab(self) -> None:
        self.control_tab.columnconfigure(0, weight=1)

        region_frame = ttk.LabelFrame(self.control_tab, text="Region & Steuerung", style="Section.TLabelframe")
        region_frame.grid(row=0, column=0, sticky="ew")
        region_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(region_frame, text="Region (x1,y1,x2,y2):").grid(row=0, column=0, sticky="w")
        self.region_entry = ttk.Entry(region_frame, textvariable=self.region_var, width=32, style="Valid.TEntry")
        self.region_entry.grid(row=0, column=1, sticky="ew", padx=(LAYOUT["column_pad"], 0))

        self.region_apply_btn = ttk.Button(region_frame, text="Übernehmen", style="Accent.TButton", command=self._apply_region)
        self.region_apply_btn.grid(row=0, column=2, padx=(LAYOUT["column_pad"], 0))

        select_btn = ttk.Button(region_frame, text="Auswahl", command=self.start_region_selection)
        select_btn.grid(row=0, column=3, padx=(LAYOUT["column_pad"], 0))

        action_frame = ttk.Frame(region_frame)
        action_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(LAYOUT["row_pad"], 0))
        action_frame.grid_columnconfigure(2, weight=1)

        self.single_button = ttk.Button(action_frame, text="Einmal scannen", style="Accent.TButton", command=self.run_single)
        self.single_button.grid(row=0, column=0, padx=(0, LAYOUT["column_pad"]))

        self.auto_button = ttk.Button(action_frame, text="Auto-Tracking starten", style="Accent.TButton", command=self.toggle_auto)
        self.auto_button.grid(row=0, column=1)

        self.status_label = ttk.Label(action_frame, textvariable=self.status_var)
        self.status_label.grid(row=0, column=2, sticky="w", padx=(LAYOUT["column_pad"], 0))

        Tooltip(self.region_entry, "Aktive Capture-Region des Trackers. Ungültige Eingaben werden hervorgehoben.")
        Tooltip(self.auto_button, "Startet/stoppt den Auto-Tracking-Loop (Strg+A).")
        Tooltip(self.single_button, "Führt einen einzelnen Scan aus (Strg+R).")

        self.region_var.trace_add("write", self._on_region_change)
        self._on_region_change()

    def _build_settings_tab(self) -> None:
        self.settings_tab.columnconfigure(0, weight=1)

        settings_frame = ttk.LabelFrame(self.settings_tab, text="Laufzeit-Einstellungen", style="Section.TLabelframe")
        settings_frame.grid(row=0, column=0, sticky="ew")

        row = 0
        if torch.cuda.is_available():
            gpu_check = ttk.Checkbutton(settings_frame, text="GPU-Modus verwenden", variable=self.use_gpu_var, style="Settings.TCheckbutton")
            gpu_check.grid(row=row, column=0, sticky="w")
            Tooltip(gpu_check, "Wechselt zwischen GPU- und CPU-Modus. Neustart erforderlich.")
            row += 1

        debug_check = ttk.Checkbutton(settings_frame, text="Debug-Modus", variable=self.debug_var, style="Settings.TCheckbutton")
        debug_check.grid(row=row, column=0, sticky="w")
        Tooltip(debug_check, "Aktiviert zusätzliche Debug-Ausgaben.")
        row += 1

        dark_check = ttk.Checkbutton(settings_frame, text="Dark Mode", variable=self.dark_mode_var, command=self._toggle_theme, style="Settings.TCheckbutton")
        dark_check.grid(row=row, column=0, sticky="w")
        Tooltip(dark_check, "Schaltet zwischen hellem und dunklem Farbschema um.")
        row += 1

        save_btn = ttk.Button(settings_frame, text="Einstellungen speichern", style="Accent.TButton", command=self._apply_settings)
        save_btn.grid(row=row, column=0, sticky="e", pady=(LAYOUT["row_pad"], 0))
        Tooltip(save_btn, "Persistiert GPU- und Debug-Optionen.")

        hint = ttk.Label(settings_frame, text="GPU-Änderungen werden nach einem Neustart aktiv.", style="SubHeader.TLabel")
        hint.grid(row=row + 1, column=0, sticky="w", pady=(LAYOUT["row_pad"], 0))

        status_frame = ttk.LabelFrame(self.settings_tab, text="Status", style="Section.TLabelframe")
        status_frame.grid(row=1, column=0, sticky="ew", pady=(LAYOUT["row_pad"], 0))
        status_frame.grid_columnconfigure(0, weight=1)

        self.health_label = ttk.Label(status_frame, textvariable=self.health_status_var, style="Status.Green.TLabel")
        self.health_label.grid(row=0, column=0, sticky="w")

        self.window_label = ttk.Label(status_frame, textvariable=self.window_status_var)
        self.window_label.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.mode_label = ttk.Label(status_frame, textvariable=self.mode_var)
        self.mode_label.grid(row=2, column=0, sticky="w", pady=(2, 0))

        self.auto_progress = ttk.Progressbar(status_frame, mode="indeterminate", length=120)
        self.auto_progress.grid(row=3, column=0, sticky="w", pady=(LAYOUT["row_pad"], 0))
        self.auto_progress.grid_remove()

        history_btn = ttk.Button(status_frame, text="Fenster-Historie", command=self._show_window_history)
        history_btn.grid(row=4, column=0, sticky="w", pady=(LAYOUT["row_pad"], 0))
        Tooltip(history_btn, "Zeigt die letzten erkannten Fensterwechsel an.")

    def _build_analysis_tab(self) -> None:
        self.analysis_tab.columnconfigure(0, weight=1)
        self.analysis_tab.rowconfigure(4, weight=1)

        filter_frame = ttk.Frame(self.analysis_tab)
        filter_frame.grid(row=0, column=0, sticky="ew", pady=(0, LAYOUT["row_pad"] // 2))
        for col in range(4):
            filter_frame.grid_columnconfigure(col, weight=1 if col % 2 == 1 else 0)

        ttk.Label(filter_frame, text="Filter-Modus:").grid(row=0, column=0, sticky="w")
        self.filter_mode_var = tk.StringVar(value="Alles anzeigen")
        self.filter_mode_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_mode_var,
            values=["Alles anzeigen", "Manuelle Eingabe", "Preset wählen"],
            state="readonly",
            width=18,
        )
        self.filter_mode_combo.grid(row=0, column=1, padx=(LAYOUT["column_pad"], 0), sticky="ew")
        self.filter_mode_combo.current(0)

        self.preset_var = tk.StringVar()
        self.preset_label = ttk.Label(filter_frame, text="Preset:")
        self.preset_combo = ttk.Combobox(filter_frame, textvariable=self.preset_var, state="readonly", width=22)

        ttk.Label(filter_frame, text="Von:").grid(row=1, column=0, sticky="e", pady=(LAYOUT["row_pad"] // 2, 0))
        self.start_entry = ttk.Entry(filter_frame, width=12)
        self.start_entry.grid(row=1, column=1, sticky="ew", padx=(LAYOUT["column_pad"], 0), pady=(LAYOUT["row_pad"] // 2, 0))

        ttk.Label(filter_frame, text="Bis:").grid(row=1, column=2, sticky="e", padx=(LAYOUT["column_pad"], 0), pady=(LAYOUT["row_pad"] // 2, 0))
        self.end_entry = ttk.Entry(filter_frame, width=12)
        self.end_entry.grid(row=1, column=3, sticky="ew", pady=(LAYOUT["row_pad"] // 2, 0))

        manual_row = ttk.Frame(self.analysis_tab)
        manual_row.grid(row=1, column=0, sticky="ew", pady=(LAYOUT["row_pad"], 0))
        manual_row.grid_columnconfigure(1, weight=1)
        manual_row.grid_columnconfigure(3, weight=1)

        ttk.Label(manual_row, text="Item:").grid(row=0, column=0, sticky="w")
        self.item_entry = ttk.Entry(manual_row)
        self.item_entry.grid(row=0, column=1, sticky="ew", padx=(LAYOUT["column_pad"], 0))

        ttk.Label(manual_row, text="Typ:").grid(row=0, column=2, sticky="e", padx=(LAYOUT["column_pad"], 0))
        self.type_entry = ttk.Entry(manual_row, width=12)
        self.type_entry.grid(row=0, column=3, sticky="w", padx=(LAYOUT["column_pad"], 0))

        actions_frame = ttk.Frame(self.analysis_tab)
        actions_frame.grid(row=2, column=0, sticky="ew", pady=(LAYOUT["row_pad"], 0))
        actions_frame.grid_columnconfigure(1, weight=1)

        self.view_button = ttk.Button(actions_frame, text="Daten aktualisieren", style="Accent.TButton", command=self.load_transactions)
        self.view_button.grid(row=0, column=0, padx=(0, LAYOUT["column_pad"]), sticky="w")

        export_frame = ttk.Frame(actions_frame)
        export_frame.grid(row=0, column=1, sticky="w")
        self.export_csv_button = ttk.Button(export_frame, text="📤 CSV", command=self.export_csv)
        self.export_csv_button.grid(row=0, column=0, padx=(0, LAYOUT["column_pad"]))
        self.export_json_button = ttk.Button(export_frame, text="📄 JSON", command=self.export_json)
        self.export_json_button.grid(row=0, column=1)

        Tooltip(self.view_button, "Lädt Transaktionen gemäß Filterkriterien (Strg+E).")
        Tooltip(self.export_csv_button, "Exportiert aktuelle Daten als CSV.")
        Tooltip(self.export_json_button, "Exportiert aktuelle Daten als JSON.")

        summary_frame = ttk.LabelFrame(self.analysis_tab, text="Zusammenfassung", style="Section.TLabelframe")
        summary_frame.grid(row=3, column=0, sticky="ew", pady=(LAYOUT["row_pad"], 0))
        summary_frame.grid_columnconfigure(0, weight=1)

        keys = ["trans", "sales", "buys", "profit", "avg_prices", "top_items"]
        self.summary_vars: dict[str, tk.StringVar] = {}
        for idx, key in enumerate(keys):
            var = tk.StringVar(value="-")
            self.summary_vars[key] = var
            ttk.Label(summary_frame, textvariable=var, anchor="w").grid(row=idx, column=0, sticky="w", pady=2)

        tree_frame = ttk.Frame(self.analysis_tab)
        tree_frame.grid(row=4, column=0, sticky="nsew", pady=(LAYOUT["row_pad"], 0))
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        columns = ("timestamp", "item", "qty", "price", "unit_price", "type", "case")
        self.data_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=14)
        headings = {
            "timestamp": ("Zeitstempel", "w", 150),
            "item": ("Item", "w", 220),
            "qty": ("Menge", "e", 90),
            "price": ("Preis", "e", 120),
            "unit_price": ("Preis/Einheit", "e", 130),
            "type": ("Typ", "center", 90),
            "case": ("Fall", "w", 160),
        }
        for key, (label, anchor, width) in headings.items():
            self.data_tree.heading(key, text=label)
            self.data_tree.column(key, anchor=anchor, width=width)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.data_tree.yview)
        self.data_tree.configure(yscrollcommand=vsb.set)
        self.data_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        make_treeview_sortable(self.data_tree, numeric_columns={"qty", "price", "unit_price"})

        plot_frame = ttk.LabelFrame(self.analysis_tab, text="Preisverlauf", style="Section.TLabelframe")
        plot_frame.grid(row=5, column=0, sticky="nsew", pady=(LAYOUT["row_pad"], 0))
        plot_frame.grid_rowconfigure(0, weight=1)
        plot_frame.grid_columnconfigure(0, weight=1)

        self.figure = Figure(figsize=(PLOT_SETTINGS["default_width"], 3.2), dpi=100)
        self.price_axes = self.figure.add_subplot(111)
        self.price_axes.set_xlabel("Zeit")
        self.price_axes.set_ylabel("Preis (Silver)")

        self.canvas = FigureCanvasTkAgg(self.figure, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky="nsew")

        self.toolbar = NavigationToolbar2Tk(self.canvas, plot_frame, pack_toolbar=False)
        self.toolbar.grid(row=1, column=0, sticky="ew")

        self.filter_mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._update_filter_mode())
        self._update_filter_mode()

    def _build_orders_tab(self) -> None:
        self.orders_tab.columnconfigure(0, weight=1)
        self.orders_tab.rowconfigure(1, weight=1)

        filter_frame = ttk.Frame(self.orders_tab)
        filter_frame.grid(row=0, column=0, sticky="ew")
        filter_frame.grid_columnconfigure(4, weight=1)

        ttk.Label(filter_frame, text="Suche:").grid(row=0, column=0, sticky="w")
        self.order_search_var = tk.StringVar()
        self.order_search_entry = ttk.Entry(filter_frame, textvariable=self.order_search_var, width=24)
        self.order_search_entry.grid(row=0, column=1, sticky="w", padx=(LAYOUT["column_pad"], 0))

        ttk.Label(filter_frame, text="Status:").grid(row=0, column=2, sticky="e", padx=(LAYOUT["column_pad"], 0))
        self.orders_status_var = tk.StringVar(value="active")
        self.orders_status_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.orders_status_var,
            values=["Alle", "active", "collected", "cancelled"],
            state="readonly",
            width=12,
        )
        self.orders_status_combo.grid(row=0, column=3, sticky="w", padx=(LAYOUT["column_pad"], 0))

        ttk.Label(filter_frame, text="Typ:").grid(row=0, column=4, sticky="e", padx=(LAYOUT["column_pad"], 0))
        self.orders_type_var = tk.StringVar(value="Alle")
        self.orders_type_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.orders_type_var,
            values=["Alle", "Preorder", "Listing"],
            state="readonly",
            width=12,
        )
        self.orders_type_combo.grid(row=0, column=5, sticky="w", padx=(LAYOUT["column_pad"], 0))

        orders_frame = ttk.Frame(self.orders_tab)
        orders_frame.grid(row=1, column=0, sticky="nsew", pady=(LAYOUT["row_pad"], 0))
        orders_frame.grid_columnconfigure(0, weight=1)
        orders_frame.grid_rowconfigure(0, weight=1)

        columns = ("id", "type", "item", "qty", "filled", "price", "status", "timestamp")
        self.orders_tree = ttk.Treeview(orders_frame, columns=columns, show="headings", height=18)
        orders_headings = {
            "id": ("ID", "center", 60),
            "type": ("Typ", "center", 90),
            "item": ("Item", "w", 240),
            "qty": ("Menge", "e", 90),
            "filled": ("Gefüllt/Verkauft", "e", 130),
            "price": ("Preis", "e", 130),
            "status": ("Status", "center", 90),
            "timestamp": ("Zeitstempel", "center", 160),
        }
        for key, (label, anchor, width) in orders_headings.items():
            self.orders_tree.heading(key, text=label)
            self.orders_tree.column(key, anchor=anchor, width=width)

        vsb = ttk.Scrollbar(orders_frame, orient="vertical", command=self.orders_tree.yview)
        hsb = ttk.Scrollbar(orders_frame, orient="horizontal", command=self.orders_tree.xview)
        self.orders_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.orders_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        make_treeview_sortable(self.orders_tree, numeric_columns={"qty", "filled", "price"})

        button_frame = ttk.Frame(self.orders_tab)
        button_frame.grid(row=2, column=0, sticky="ew", pady=(LAYOUT["row_pad"], 0))

        self.add_order_button = ttk.Button(button_frame, text="➕ Hinzufügen", style="Accent.TButton", command=self._open_add_order_dialog)
        self.add_order_button.pack(side="left")

        self.refresh_orders_button = ttk.Button(button_frame, text="🔄 Aktualisieren", command=self._refresh_orders)
        self.refresh_orders_button.pack(side="left", padx=(LAYOUT["column_pad"], 0))

        self.mark_collected_button = ttk.Button(button_frame, text="✅ Collected", command=self._mark_order_collected)
        self.mark_collected_button.pack(side="left", padx=(LAYOUT["column_pad"], 0))

        self.cancel_order_button = ttk.Button(button_frame, text="❌ Cancel", style="Danger.TButton", command=self._cancel_order)
        self.cancel_order_button.pack(side="left", padx=(LAYOUT["column_pad"], 0))

        self.delete_order_button = ttk.Button(button_frame, text="🗑️ Löschen", style="Danger.TButton", command=self._delete_order)
        self.delete_order_button.pack(side="left", padx=(LAYOUT["column_pad"], 0))

        Tooltip(self.add_order_button, "Erstellt eine Order manuell (z. B. für Nachträge).")
        Tooltip(self.refresh_orders_button, "Lädt die Orderliste gemäß Filtern neu.")

        self.order_search_var.trace_add("write", self._on_order_filter_change)
        self.orders_status_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_orders())
        self.orders_type_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_orders())

    # ------------------------------------------------------------------
    # Helpers & Events
    # ------------------------------------------------------------------
    def _bind_shortcuts(self) -> None:
        bind_hotkey(self.root, "<Control-r>", lambda _e: self.run_single())
        bind_hotkey(self.root, "<Control-a>", lambda _e: self.toggle_auto())
        bind_hotkey(self.root, "<Control-e>", lambda _e: self.load_transactions())

    def _toggle_theme(self) -> None:
        theme = "dark" if self.dark_mode_var.get() else "light"
        self.theme_manager.apply(theme)
        self._on_region_change()
        set_dark_mode(theme == "dark")

    def _on_region_change(self, *_args) -> None:
        region = parse_region_text(self.region_var.get())
        if region:
            self.region_entry.configure(style="Valid.TEntry")
            self.region_apply_btn.state(("!disabled",))
            self._region_valid = True
        else:
            self.region_entry.configure(style="Invalid.TEntry")
            self.region_apply_btn.state(("disabled",))
            self._region_valid = False

    def _apply_region(self) -> None:
        if not self._region_valid:
            self._set_status_bar("Region ungültig.", "warn")
            return
        region = parse_region_text(self.region_var.get())
        if region:
            self.tracker.region = region
            set_capture_region(region)
            self._set_status_bar(f"Region aktualisiert: {region}")
        else:
            self._set_status_bar("Region konnte nicht gesetzt werden.", "error")

    def _apply_settings(self) -> None:
        set_use_gpu(self.use_gpu_var.get())
        set_debug_mode(self.debug_var.get())
        self.tracker.debug = self.debug_var.get()
        self._set_status_bar("Einstellungen gespeichert. GPU-Wechsel nach Neustart aktiv.")

    def _palette(self) -> Palette:
        return self.palettes[self.theme_manager.current_theme]

    def _set_status_bar(self, message: str, level: str = "info") -> None:
        palette = self._palette()
        colors = {
            "info": palette.text_secondary,
            "warn": palette.warning,
            "error": palette.error,
        }
        self.status_bar_var.set(message)
        self.status_bar_label.configure(foreground=colors.get(level, palette.text_secondary))

    def run_single(self) -> None:
        if not self._region_valid:
            self._set_status_bar("Einzel-Scan abgebrochen: Region ungültig.", "warn")
            return
        try:
            self.status_var.set("Status: Scan läuft…")
            self._set_status_bar("Einzel-Scan gestartet…")
            self.tracker.single_scan()
            self.status_var.set("Status: Idle")
            self._set_status_bar("Einzel-Scan abgeschlossen.")
        except Exception as exc:  # noqa: BLE001
            self.status_var.set("Status: Fehler")
            messagebox.showerror("Einzel-Scan", str(exc))
            self._set_status_bar("Einzel-Scan fehlgeschlagen.", "error")

    def toggle_auto(self) -> None:
        if not self.tracker.running:
            if not self._region_valid:
                self._set_status_bar("Auto-Tracking nicht gestartet: Region ungültig.", "warn")
                return
            self.status_var.set("Status: Running")
            self._apply_region()
            log_debug("[AUTO-TRACK] ▶️ STARTED - Auto-Track mode enabled")
            self._set_status_bar("Auto-Tracking gestartet.")
            threading.Thread(target=self.tracker.auto_track, daemon=True).start()
            self.auto_button.configure(text="Auto-Tracking stoppen")
            self.auto_progress.grid()
            self.auto_progress.start(12)
        else:
            log_debug("[AUTO-TRACK] ⏸️ STOPPED - Auto-Track mode disabled")
            self.tracker.stop()
            self.status_var.set("Status: Idle")
            self._set_status_bar("Auto-Tracking gestoppt.")
            self.auto_button.configure(text="Auto-Tracking starten")
            self.auto_progress.stop()
            self.auto_progress.grid_remove()

    def start_region_selection(self) -> None:
        selection_state: list[tuple[int, int]] = []

        overlay = tk.Toplevel(self.root)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.35)
        overlay.configure(background="black")
        overlay.attributes("-topmost", True)
        overlay.grab_set()

        instruction_var = tk.StringVar(value="Klick auf linke obere Ecke des Marktfensters")
        instruction_label = tk.Label(overlay, textvariable=instruction_var, fg="white", bg="black", font=("Segoe UI", 16, "bold"))
        instruction_label.pack(expand=True)

        def finish() -> None:
            overlay.grab_release()
            overlay.destroy()

        def cancel(_event=None) -> None:
            finish()

        def on_click(event) -> None:
            selection_state.append((event.x_root, event.y_root))
            if len(selection_state) == 1:
                instruction_var.set("Klick auf rechte untere Ecke des Marktfensters")
            elif len(selection_state) == 2:
                (x1, y1), (x2, y2) = selection_state
                left, right = sorted([x1, x2])
                top, bottom = sorted([y1, y2])
                region = (int(left), int(top), int(right), int(bottom))
                self.region_var.set(",".join(map(str, region)))
                self.tracker.region = region
                set_capture_region(region)
                self._set_status_bar(f"Region gesetzt: {region}")
                finish()

        overlay.bind("<Button-1>", on_click)
        overlay.bind("<Escape>", cancel)

    def update_health_status(self) -> None:
        try:
            error_count = getattr(self.tracker, "error_count", 0)
            style = "Status.Green.TLabel"
            text = "🟢 Healthy"
            if error_count >= 3:
                style = "Status.Red.TLabel"
                text = "🔴 Fehler"
            elif error_count > 0:
                style = "Status.Yellow.TLabel"
                text = "🟡 Warnung"
            self.health_label.configure(style=style)
            self.health_status_var.set(text)

            if self.tracker.running and getattr(self.tracker, "window_history", None):
                last_window = self.tracker.window_history[-1]
                window_name = last_window[1] if isinstance(last_window, tuple) else last_window
                self.window_status_var.set(f"Fenster: {window_name}")
            else:
                self.window_status_var.set("Fenster: Idle")
        except Exception:  # noqa: BLE001
            self.health_label.configure(style="Status.Yellow.TLabel")
            self.health_status_var.set("⚠️ Unbekannt")

        self.root.after(self.HEALTH_POLL_MS, self.update_health_status)

    # ------------------------------------------------------------------
    # Daten & Analyse
    # ------------------------------------------------------------------
    def _update_filter_mode(self) -> None:
        mode = self.filter_mode_var.get()
        if mode == "Preset wählen":
            self.preset_label.grid(row=0, column=2, sticky="e", padx=(LAYOUT["column_pad"], 0))
            self.preset_combo.grid(row=0, column=3, sticky="w")
            self.item_entry.configure(state="disabled")
            self.type_entry.configure(state="disabled")
        else:
            self.preset_label.grid_remove()
            self.preset_combo.grid_remove()
            state = "normal" if mode == "Manuelle Eingabe" else "disabled"
            self.item_entry.configure(state=state)
            self.type_entry.configure(state=state)

    def _load_presets(self) -> None:
        presets = get_all_presets()
        names = [preset["name"] for preset in presets]
        self.preset_combo["values"] = names
        if names:
            self.preset_combo.current(0)

    def load_transactions(self) -> None:
        try:
            start_text = self.start_entry.get().strip()
            end_text = self.end_entry.get().strip()
            start_ts = f"{start_text} 00:00:00" if start_text else None
            end_ts = f"{end_text} 23:59:59" if end_text else None

            query = "SELECT * FROM transactions"
            params: list = []
            filters: list[str] = []

            if start_ts:
                filters.append("timestamp >= ?")
                params.append(start_ts)
            if end_ts:
                filters.append("timestamp <= ?")
                params.append(end_ts)

            mode = self.filter_mode_var.get()
            if mode == "Preset wählen":
                preset_name = self.preset_var.get()
                preset = get_preset_by_name(preset_name) if preset_name else None
                if not preset or not preset.get("items"):
                    self._set_status_bar("Preset leer oder nicht gefunden.", "warn")
                    return
                placeholders = ",".join(["?"] * len(preset["items"]))
                filters.append(f"item_name IN ({placeholders})")
                params.extend(preset["items"])
            elif mode == "Manuelle Eingabe":
                item_value = self.item_entry.get().strip()
                type_value = self.type_entry.get().strip().lower()
                if item_value:
                    filters.append("item_name LIKE ?")
                    params.append(f"%{item_value}%")
                if type_value in {"buy", "sell"}:
                    filters.append("transaction_type = ?")
                    params.append(type_value)

            if filters:
                query += " WHERE " + " AND ".join(filters)

            df = pd.read_sql_query(query, get_connection(), params=params)
            if df.empty:
                self._latest_df = None
                self._clear_data_tree()
                self._update_summary(None)
                self._update_plot(None)
                self._set_status_bar("Keine Transaktionen gefunden.", "warn")
                return

            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df["unit_price"] = df.apply(lambda row: (row["price"] / row["quantity"]) if row["quantity"] else None, axis=1)

            self._latest_df = df
            self._populate_data_tree(df)
            self._update_summary(df)
            self._update_plot(df)
            self._set_status_bar(f"{len(df)} Transaktionen geladen.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Analyse", str(exc))
            self._set_status_bar("Transaktionen konnten nicht geladen werden.", "error")

    def _clear_data_tree(self) -> None:
        for item in self.data_tree.get_children():
            self.data_tree.delete(item)

    def _populate_data_tree(self, df: pd.DataFrame) -> None:
        self._clear_data_tree()
        for _, row in df.sort_values("timestamp", ascending=False).iterrows():
            values = (
                row["timestamp"].strftime("%Y-%m-%d %H:%M:%S"),
                row["item_name"],
                f"{int(row['quantity']):,}" if pd.notna(row["quantity"]) else "-",
                f"{int(row['price']):,}" if pd.notna(row["price"]) else "-",
                f"{int(row['unit_price']):,}" if pd.notna(row["unit_price"]) else "-",
                row["transaction_type"],
                row.get("tx_case", "-"),
            )
            self.data_tree.insert("", "end", values=values)

    def _update_summary(self, df: pd.DataFrame | None) -> None:
        if df is None or df.empty:
            for var in self.summary_vars.values():
                var.set("-")
            return

        total_trans = len(df)
        type_counts = df["transaction_type"].value_counts()
        total_sales = int(df[df["transaction_type"] == "sell"]["price"].fillna(0).sum())
        total_buys = int(df[df["transaction_type"] == "buy"]["price"].fillna(0).sum())
        profit = total_sales - total_buys
        qty_sales = int(df[df["transaction_type"] == "sell"]["quantity"].fillna(0).sum())
        qty_buys = int(df[df["transaction_type"] == "buy"]["quantity"].fillna(0).sum())
        avg_sell = df[df["transaction_type"] == "sell"]["unit_price"].dropna().mean()
        avg_buy = df[df["transaction_type"] == "buy"]["unit_price"].dropna().mean()

        top_items = df.groupby("item_name")["price"].sum().sort_values(ascending=False).head(3)
        top_items_text = ", ".join(f"{name} ({int(value):,})" for name, value in top_items.items()) or "-"

        self.summary_vars["trans"].set(
            f"Transaktionen gesamt: {total_trans} (Sell: {type_counts.get('sell', 0)} | Buy: {type_counts.get('buy', 0)})"
        )
        self.summary_vars["sales"].set(f"Verkaufsvolumen: {total_sales:,} Silver aus {qty_sales} Einheiten")
        self.summary_vars["buys"].set(f"Kaufvolumen: {total_buys:,} Silver aus {qty_buys} Einheiten")
        self.summary_vars["profit"].set(f"Nettoumsatz: {profit:,} Silver")
        self.summary_vars["avg_prices"].set(
            "Ø Stückpreis Sell: {} | Ø Stückpreis Buy: {}".format(
                f"{int(avg_sell):,}" if not pd.isna(avg_sell) else "-",
                f"{int(avg_buy):,}" if not pd.isna(avg_buy) else "-",
            )
        )
        self.summary_vars["top_items"].set(f"Top Items (Summe): {top_items_text}")

    def _update_plot(self, df: pd.DataFrame | None) -> None:
        self.price_axes.clear()
        if df is None or df.empty or df["unit_price"].dropna().empty:
            self.price_axes.set_title("Preisverlauf (keine Daten)")
            self.canvas.draw_idle()
            return

        plot_df = df.dropna(subset=["unit_price"]).sort_values("timestamp")
        self.price_axes.plot(plot_df["timestamp"], plot_df["unit_price"], marker="o", linewidth=1)
        self.price_axes.set_title("Preisverlauf")
        self.price_axes.set_ylabel("Silver")
        self.price_axes.tick_params(axis="x", rotation=15)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def export_csv(self) -> None:
        if self._latest_df is None or self._latest_df.empty:
            self._set_status_bar("Keine Daten zum Exportieren.", "warn")
            return
        path = f"export_{int(time.time())}.csv"
        self._latest_df.to_csv(path, index=False)
        self._set_status_bar(f"CSV exportiert: {path}")

    def export_json(self) -> None:
        if self._latest_df is None or self._latest_df.empty:
            self._set_status_bar("Keine Daten zum Exportieren.", "warn")
            return
        path = f"export_{int(time.time())}.json"
        self._latest_df.to_json(path, orient="records", force_ascii=False)
        self._set_status_bar(f"JSON exportiert: {path}")

    def _show_window_history(self) -> None:
        history = getattr(self.tracker, "window_history", [])[-10:]
        if not history:
            self._set_status_bar("Keine Fenster-Historie vorhanden.", "warn")
            return

        win = tk.Toplevel(self.root)
        win.title("Fenster-Historie")
        win.geometry("360x280")
        try:
            win.iconbitmap("config/icon.ico")
        except tk.TclError:
            pass

        listbox = tk.Listbox(win)
        listbox.pack(fill="both", expand=True, padx=12, pady=12)
        for ts, window in history:
            listbox.insert("end", f"{ts.strftime('%H:%M:%S')}  •  {window}")

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def _on_order_filter_change(self, *_args) -> None:
        if self._order_filter_job:
            self.root.after_cancel(self._order_filter_job)
        self._order_filter_job = self.root.after(250, self._refresh_orders)

    def _schedule_orders_refresh(self) -> None:
        if self._orders_refresh_job:
            self.root.after_cancel(self._orders_refresh_job)
        self._orders_refresh_job = self.root.after(self.ORDERS_REFRESH_MS, self._auto_refresh_orders)

    def _auto_refresh_orders(self) -> None:
        if self.tracker.running:
            self._refresh_orders()
        self._schedule_orders_refresh()

    def _refresh_orders(self) -> None:
        for item in self.orders_tree.get_children():
            self.orders_tree.delete(item)

        status_filter = self.orders_status_var.get()
        type_filter = self.orders_type_var.get()
        search_text = self.order_search_var.get().strip().lower()

        def matches(name: str) -> bool:
            return not search_text or search_text in name.lower()

        try:
            if type_filter in ("Alle", "Preorder"):
                query = "SELECT id, item_name, quantity, quantity_filled, price, status, timestamp FROM preorders"
                params: list = []
                if status_filter != "Alle":
                    query += " WHERE status = ?"
                    params.append(status_filter)
                query += " ORDER BY timestamp DESC"
                cur = get_cursor()
                cur.execute(query, params)
                for row in cur.fetchall():
                    if not matches(row[1]):
                        continue
                    self.orders_tree.insert(
                        "",
                        "end",
                        values=(
                            row[0],
                            "Preorder",
                            row[1],
                            f"{row[2]:,}",
                            f"{row[3]:,}" if row[3] else "0",
                            f"{int(row[4]):,}",
                            row[5],
                            row[6],
                        ),
                        tags=(row[5],),
                    )

            if type_filter in ("Alle", "Listing"):
                query = "SELECT id, item_name, quantity, quantity_sold, price, status, timestamp FROM listings"
                params = []
                if status_filter != "Alle":
                    query += " WHERE status = ?"
                    params.append(status_filter)
                query += " ORDER BY timestamp DESC"
                cur = get_cursor()
                cur.execute(query, params)
                for row in cur.fetchall():
                    if not matches(row[1]):
                        continue
                    self.orders_tree.insert(
                        "",
                        "end",
                        values=(
                            row[0],
                            "Listing",
                            row[1],
                            f"{row[2]:,}",
                            f"{row[3]:,}" if row[3] else "0",
                            f"{int(row[4]):,}",
                            row[5],
                            row[6],
                        ),
                        tags=(row[5],),
                    )

            palette = self._palette()
            self.orders_tree.tag_configure("active", foreground=palette.success)
            self.orders_tree.tag_configure("collected", foreground="#1E88E5")
            self.orders_tree.tag_configure("cancelled", foreground=palette.error)
            self._set_status_bar("Orders aktualisiert.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Orders", str(exc))
            self._set_status_bar("Orders konnten nicht geladen werden.", "error")

    def _with_selected_order(self) -> tuple[int, str, str] | None:
        selection = self.orders_tree.selection()
        if not selection:
            self._set_status_bar("Bitte eine Order auswählen.", "warn")
            return None
        values = self.orders_tree.item(selection[0])["values"]
        return int(values[0]), values[1], values[6]

    def _mark_order_collected(self) -> None:
        data = self._with_selected_order()
        if not data:
            return
        order_id, order_type, status = data
        if status != "active":
            self._set_status_bar("Nur aktive Orders können abgeschlossen werden.", "warn")
            return
        if not messagebox.askyesno("Order abschließen", f"Order {order_id} als collected markieren?"):
            return
        table = "preorders" if order_type == "Preorder" else "listings"
        cur = get_cursor()
        cur.execute(
            f"UPDATE {table} SET status='collected', collected_at=CURRENT_TIMESTAMP WHERE id=?",
            (order_id,),
        )
        get_connection().commit()
        self._set_status_bar(f"Order {order_id} als collected markiert.")
        self._refresh_orders()

    def _cancel_order(self) -> None:
        data = self._with_selected_order()
        if not data:
            return
        order_id, order_type, status = data
        if status != "active":
            self._set_status_bar("Nur aktive Orders können gecancelt werden.", "warn")
            return
        if not messagebox.askyesno("Order canceln", f"Order {order_id} wirklich canceln?"):
            return
        table = "preorders" if order_type == "Preorder" else "listings"
        cur = get_cursor()
        cur.execute(f"UPDATE {table} SET status='cancelled' WHERE id=?", (order_id,))
        get_connection().commit()
        self._set_status_bar(f"Order {order_id} gecancelt.")
        self._refresh_orders()

    def _delete_order(self) -> None:
        data = self._with_selected_order()
        if not data:
            return
        order_id, order_type, _status = data
        if not messagebox.askyesno("Order löschen", f"Order {order_id} endgültig löschen?"):
            return
        table = "preorders" if order_type == "Preorder" else "listings"
        cur = get_cursor()
        cur.execute(f"DELETE FROM {table} WHERE id=?", (order_id,))
        get_connection().commit()
        self._set_status_bar(f"Order {order_id} gelöscht.")
        self._refresh_orders()

    def _open_add_order_dialog(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Order manuell hinzufügen")
        dialog.geometry("420x360")
        dialog.transient(self.root)
        dialog.grab_set()
        try:
            dialog.iconbitmap("config/icon.ico")
        except tk.TclError:
            pass

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Order-Typ:").grid(row=0, column=0, sticky="w")
        order_type_var = tk.StringVar(value="Preorder")
        order_type_combo = ttk.Combobox(frame, textvariable=order_type_var, values=["Preorder", "Listing"], state="readonly")
        order_type_combo.grid(row=0, column=1, sticky="ew")

        ttk.Label(frame, text="Item-Name:").grid(row=1, column=0, sticky="w", pady=(LAYOUT["row_pad"], 0))
        item_entry = ttk.Entry(frame)
        item_entry.grid(row=1, column=1, sticky="ew", pady=(LAYOUT["row_pad"], 0))

        ttk.Label(frame, text="Menge:").grid(row=2, column=0, sticky="w", pady=(LAYOUT["row_pad"], 0))
        qty_entry = ttk.Entry(frame)
        qty_entry.insert(0, "1000")
        qty_entry.grid(row=2, column=1, sticky="ew", pady=(LAYOUT["row_pad"], 0))

        ttk.Label(frame, text="Preis (Total):").grid(row=3, column=0, sticky="w", pady=(LAYOUT["row_pad"], 0))
        price_entry = ttk.Entry(frame)
        price_entry.insert(0, "1000000")
        price_entry.grid(row=3, column=1, sticky="ew", pady=(LAYOUT["row_pad"], 0))

        ttk.Label(frame, text="Zeitstempel (YYYY-MM-DD HH:MM:SS):").grid(row=4, column=0, columnspan=2, sticky="w", pady=(LAYOUT["row_pad"], 0))
        ts_entry = ttk.Entry(frame)
        ts_entry.insert(0, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        ts_entry.grid(row=5, column=0, columnspan=2, sticky="ew")

        frame.grid_columnconfigure(1, weight=1)

        def save() -> None:
            item_name = item_entry.get().strip()
            if not item_name:
                self._set_status_bar("Item-Name erforderlich.", "warn")
                return
            try:
                quantity = int(qty_entry.get().replace("_", "").replace(",", "").replace(".", ""))
                if quantity <= 0:
                    raise ValueError
            except ValueError:
                self._set_status_bar("Ungültige Menge.", "warn")
                return
            try:
                price = float(price_entry.get().replace("_", "").replace(",", ""))
                if price <= 0:
                    raise ValueError
            except ValueError:
                self._set_status_bar("Ungültiger Preis.", "warn")
                return
            try:
                timestamp = datetime.datetime.strptime(ts_entry.get().strip(), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                self._set_status_bar("Zeitstempel ungültig.", "warn")
                return

            table = "preorders" if order_type_var.get() == "Preorder" else "listings"
            quantity_field = "quantity_filled" if table == "preorders" else "quantity_sold"
            cur = get_cursor()
            cur.execute(
                f"INSERT INTO {table} (item_name, quantity, {quantity_field}, price, timestamp, status, created_at) "
                "VALUES (?, ?, 0, ?, ?, 'active', CURRENT_TIMESTAMP)",
                (item_name, quantity, price, timestamp),
            )
            get_connection().commit()
            self._set_status_bar(f"Order für {item_name} hinzugefügt.")
            dialog.destroy()
            self._refresh_orders()

        button_row = ttk.Frame(frame)
        button_row.grid(row=6, column=0, columnspan=2, sticky="e", pady=(LAYOUT["row_pad"], 0))
        ttk.Button(button_row, text="Speichern", style="Accent.TButton", command=save).pack(side="left")
        ttk.Button(button_row, text="Abbrechen", command=dialog.destroy).pack(side="left", padx=(LAYOUT["column_pad"], 0))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        try:
            self.tracker.stop()
            time.sleep(0.1)
        finally:
            if self._orders_refresh_job:
                self.root.after_cancel(self._orders_refresh_job)
            if self._order_filter_job:
                self.root.after_cancel(self._order_filter_job)
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
            self.root.destroy()


def start_gui() -> None:
    tracker = MarketTracker(debug=get_debug_mode(True))
    gui = MarketTrackerGUI(tracker)
    gui.start()


if __name__ == "__main__":
    start_gui()