import tkinter as tk
import threading
import time
from tkinter import messagebox, ttk
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import datetime
from utils import log_debug 
import torch

from tracker import MarketTracker
from config import (
    DEFAULT_REGION,
    USE_GPU,
    get_capture_region,
    get_debug_mode,
    get_use_gpu,
    set_capture_region,
    set_debug_mode,
    set_use_gpu,
)
from database import conn, get_connection
from database import (
    get_all_presets,
    get_preset_by_name,
    save_preset,
    delete_preset,
)


# -----------------------
# GUI
# -----------------------
def start_gui():
    tracker = MarketTracker(debug=get_debug_mode(True))

    mode = "GPU" if torch.cuda.is_available() else "CPU"
    root = tk.Tk()
    root.title("BDO Market Tracker")
    root.geometry("640x760")
    root.minsize(560, 680)
    try:
        root.iconbitmap('config/icon.ico')
    except tk.TclError:
        pass  # Icon not found, continue without it

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"))
    style.configure("SubHeader.TLabel", font=("Segoe UI", 10))
    style.configure("Section.TLabelframe", padding=12)
    style.configure("Section.TLabelframe.Label", font=("Segoe UI", 11, "bold"))
    style.configure("Accent.TButton", padding=(10, 6))

    use_gpu_var = tk.BooleanVar(value=get_use_gpu(USE_GPU))
    debug_var = tk.BooleanVar(value=tracker.debug)
    status_var = tk.StringVar(value="Status: Idle")
    health_status_var = tk.StringVar(value="🟢 Healthy")
    window_status_var = tk.StringVar(value="Fenster: -")
    mode_var = tk.StringVar(value=f"Modus: {mode}")

    def _parse_region(value: str) -> tuple[int, int, int, int] | None:
        try:
            parts = [int(p.strip()) for p in value.split(',')]
            if len(parts) == 4:
                left, top, right, bottom = parts
                if right > left and bottom > top:
                    return left, top, right, bottom
        except Exception:
            return None
        return None

    def _apply_region_from_entry(entry: tk.Entry | None = None):
        widget = entry or region_entry
        region = _parse_region(widget.get())
        if region:
            tracker.region = region
            set_capture_region(region)
        else:
            messagebox.showwarning("Region", "Bitte vier Ganzzahlen im Format x1,y1,x2,y2 angeben.")

    def _apply_settings():
        use_gpu = use_gpu_var.get()
        debug_mode = debug_var.get()
        set_use_gpu(use_gpu)
        set_debug_mode(debug_mode)
        tracker.debug = debug_mode
        messagebox.showinfo("Einstellungen", "Einstellungen gespeichert. Bitte Anwendung neu starten, damit GPU-Änderungen wirksam werden.")

    def run_single():
        try:
            _apply_region_from_entry()
            tracker.single_scan()
            messagebox.showinfo("Einzel-Scan", "Einzel-Scan abgeschlossen.")
        except Exception as e:
            messagebox.showerror("Einzel-Scan", str(e))

    auto_thread = {"thread": None}

    def toggle_auto():
        if not tracker.running:
            # Start auto-tracking
            status_var.set("Status: Running")
            _apply_region_from_entry()
            # Log auto-track start in ocr_log.txt
            log_debug("[AUTO-TRACK] ▶️ STARTED - Auto-Track mode enabled")
            t = threading.Thread(target=tracker.auto_track, daemon=True)
            auto_thread["thread"] = t
            t.start()
            messagebox.showinfo("Auto-Tracking", "Auto-Tracking gestartet.")
            auto_button.config(text="Auto-Tracking stoppen")
        else:
            # Stop auto-tracking
            log_debug("[AUTO-TRACK] ⏸️ STOPPED - Auto-Track mode disabled")
            tracker.stop()
            status_var.set("Status: Idle")
            messagebox.showinfo("Auto-Tracking", "Auto-Tracking gestoppt.")
            auto_button.config(text="Auto-Tracking starten")

    def start_region_selection():
        selection_state = {"points": []}

        overlay = tk.Toplevel(root)
        overlay.attributes("-fullscreen", True)
        overlay.attributes("-alpha", 0.35)
        overlay.configure(background="black")
        overlay.attributes("-topmost", True)
        overlay.grab_set()

        instruction_var = tk.StringVar(value="Klick auf linke obere Ecke des Marktfensters")
        instruction_label = tk.Label(overlay, textvariable=instruction_var, fg="white", bg="black", font=("Arial", 16, "bold"))
        instruction_label.pack(expand=True)

        def finish_selection():
            overlay.grab_release()
            overlay.destroy()

        def cancel(event=None):
            finish_selection()

        def on_click(event):
            selection_state["points"].append((event.x_root, event.y_root))
            if len(selection_state["points"]) == 1:
                instruction_var.set("Klick auf rechte untere Ecke des Marktfensters")
            elif len(selection_state["points"]) >= 2:
                (x1, y1), (x2, y2) = selection_state["points"][0], selection_state["points"][1]
                left, right = sorted([x1, x2])
                top, bottom = sorted([y1, y2])
                region = (int(left), int(top), int(right), int(bottom))
                region_entry.delete(0, tk.END)
                region_entry.insert(0, ",".join(map(str, region)))
                tracker.region = region
                set_capture_region(region)
                finish_selection()

        overlay.bind("<Button-1>", on_click)
        overlay.bind("<Escape>", cancel)

    main_container = tk.Frame(root, padx=16, pady=16)
    main_container.pack(fill="both", expand=True)

    header_frame = tk.Frame(main_container)
    header_frame.pack(fill="x")
    ttk.Label(header_frame, text="BDO Market Tracker", style="Header.TLabel").pack(anchor="w")
    ttk.Label(
        header_frame,
        text="Live-OCR Tracker mit GPU-Optionen und Datenanalyse",
        style="SubHeader.TLabel",
    ).pack(anchor="w", pady=(4, 12))

    # Region & Control Section
    region_frame = ttk.LabelFrame(main_container, text="Scan-Steuerung", style="Section.TLabelframe")
    region_frame.pack(fill="x", pady=(0, 12))

    region_row = tk.Frame(region_frame)
    region_row.pack(fill="x", pady=4)
    tk.Label(region_row, text="Region (x1,y1,x2,y2):").pack(side="left")
    region_entry = tk.Entry(region_row)
    region_entry.insert(0, ",".join(map(str, DEFAULT_REGION)))
    region_entry.pack(side="left", fill="x", expand=True, padx=(6, 0))
    ttk.Button(region_row, text="Übernehmen", style="Accent.TButton", command=_apply_region_from_entry).pack(side="left", padx=6)
    ttk.Button(region_row, text="Auswahl", command=start_region_selection).pack(side="left")

    controls_row = tk.Frame(region_frame)
    controls_row.pack(fill="x", pady=(10, 0))
    ttk.Button(controls_row, text="Einmal scannen", style="Accent.TButton", command=run_single).pack(side="left")
    auto_button = ttk.Button(controls_row, text="Auto-Tracking starten", style="Accent.TButton", command=toggle_auto)
    auto_button.pack(side="left", padx=6)

    ttk.Label(region_frame, textvariable=status_var, foreground="#3a3a3a").pack(anchor="w", pady=(8, 0))

    # Settings Section
    settings_frame = ttk.LabelFrame(main_container, text="Einstellungen", style="Section.TLabelframe")
    settings_frame.pack(fill="x", pady=(0, 12))

    if mode == "GPU":
        tk.Checkbutton(settings_frame, text="GPU-Modus verwenden", variable=use_gpu_var).pack(anchor="w")
    tk.Checkbutton(settings_frame, text="Debug-Modus", variable=debug_var).pack(anchor="w", pady=(2, 0))
    ttk.Button(settings_frame, text="Speichern", style="Accent.TButton", command=_apply_settings).pack(anchor="e", pady=(8, 0))

    if mode == "GPU":
        note = tk.Label(
            settings_frame,
            text="Hinweis: GPU-Änderungen werden nach einem Neustart aktiv.",
            foreground="#666",
            font=("Segoe UI", 9, "italic"),
        )
        note.pack(anchor="w", pady=(4, 0))

    # Status Section
    status_frame = ttk.LabelFrame(main_container, text="Status", style="Section.TLabelframe")
    status_frame.pack(fill="x", pady=(0, 12))

    health_label = tk.Label(status_frame, textvariable=health_status_var, font=("Segoe UI", 11, "bold"))
    health_label.pack(anchor="w")
    tk.Label(status_frame, textvariable=window_status_var, fg="#1a4d8f").pack(anchor="w", pady=(2, 0))
    tk.Label(status_frame, textvariable=mode_var, fg="#666" if mode == "CPU" else "#00aaff").pack(anchor="w", pady=(2, 0))
    
    def update_health_status():
        """Update health status display every 500ms"""
        try:
            # Check error count and determine health
            error_count = getattr(tracker, 'error_count', 0)
            last_error_time = getattr(tracker, 'last_error_time', None)
            
            # Health logic+
            if error_count == 0:
                health_status_var.set("🟢 Healthy")
                health_label.config(fg="green")
            elif error_count < 3:
                health_status_var.set("🟡 Warning")
                health_label.config(fg="orange")
            else:
                health_status_var.set("🔴 Error")
                health_label.config(fg="red")
                
            # Update window status
            if tracker.running:
                if tracker.window_history:
                    last_window = tracker.window_history[-1][1] if len(tracker.window_history[-1]) > 1 else tracker.window_history[-1]
                    window_status_var.set(f"Window: {last_window}")
                else:
                    window_status_var.set("Window: scanning...")
            else:
                window_status_var.set("Window: idle")
                
        except Exception:
            pass
        
        root.after(500, update_health_status)
    
    update_health_status()  # Start the update loop

    # Anzeige-Panel
    data_frame = ttk.LabelFrame(main_container, text="Daten & Analyse", style="Section.TLabelframe")
    data_frame.pack(fill="x", pady=(0, 12))

    filters_row = tk.Frame(data_frame)
    filters_row.pack(fill="x")

    # Filter mode selection
    tk.Label(filters_row, text="Filter:").grid(row=0, column=0, sticky="w")
    filter_mode_var = tk.StringVar(value="manual")
    filter_mode_combo = ttk.Combobox(
        filters_row, 
        textvariable=filter_mode_var,
        values=["Alles anzeigen", "Manuelle Eingabe", "Preset wählen"],
        state="readonly",
        width=18
    )
    filter_mode_combo.grid(row=0, column=1, padx=(4, 12), sticky="w")
    filter_mode_combo.current(1)  # Default: Manuelle Eingabe

    # Preset selection (initially hidden)
    preset_label = tk.Label(filters_row, text="Preset:")
    preset_var = tk.StringVar()
    preset_combo = ttk.Combobox(
        filters_row,
        textvariable=preset_var,
        state="readonly",
        width=20
    )
    
    def update_preset_list():
        """Reload presets from database and update combo box"""
        presets = get_all_presets()
        preset_names = [p['name'] for p in presets]
        preset_combo['values'] = preset_names
        if preset_names:
            preset_combo.current(0)
    
    def on_filter_mode_change(event=None):
        """Show/hide filter controls based on selected mode"""
        mode = filter_mode_var.get()
        
        if mode == "Preset wählen":
            # Show preset selector, hide manual filters
            preset_label.grid(row=0, column=2, sticky="w", pady=(0, 0))
            preset_combo.grid(row=0, column=3, padx=(4, 12), sticky="w")
            update_preset_list()
            
            # Hide manual entry fields in next row
            item_label.grid_remove()
            item_entry.grid_remove()
            type_label.grid_remove()
            type_entry.grid_remove()
        else:
            # Hide preset selector
            preset_label.grid_remove()
            preset_combo.grid_remove()
            
            # Show/hide manual entry fields based on mode
            if mode == "Manuelle Eingabe":
                item_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
                item_entry.grid(row=1, column=1, padx=(4, 12), pady=(6, 0))
                type_label.grid(row=1, column=2, sticky="w", pady=(6, 0))
                type_entry.grid(row=1, column=3, padx=(4, 12), pady=(6, 0))
            else:  # "Alles anzeigen"
                item_label.grid_remove()
                item_entry.grid_remove()
                type_label.grid_remove()
                type_entry.grid_remove()
    
    filter_mode_combo.bind("<<ComboboxSelected>>", on_filter_mode_change)

    tk.Label(filters_row, text="Von:").grid(row=0, column=4, sticky="w", padx=(12, 0))
    start_entry = tk.Entry(filters_row, width=12)
    start_entry.insert(0, str(datetime.date.today()))
    start_entry.grid(row=0, column=5, padx=(4, 12))

    tk.Label(filters_row, text="Bis:").grid(row=0, column=6, sticky="w")
    end_entry = tk.Entry(filters_row, width=12)
    end_entry.insert(0, str(datetime.date.today()))
    end_entry.grid(row=0, column=7, padx=(4, 0))

    # Manual filter row (initially visible)
    item_label = tk.Label(filters_row, text="Item:")
    item_label.grid(row=1, column=0, sticky="w", pady=(6, 0))
    item_entry = tk.Entry(filters_row)
    item_entry.grid(row=1, column=1, padx=(4, 12), pady=(6, 0))

    type_label = tk.Label(filters_row, text="Typ:")
    type_label.grid(row=1, column=2, sticky="w", pady=(6, 0))
    type_entry = tk.Entry(filters_row, width=8)
    type_entry.grid(row=1, column=3, padx=(4, 12), pady=(6, 0))

    filters_row.grid_columnconfigure(1, weight=1)
    filters_row.grid_columnconfigure(3, weight=1)


    def export_csv():
        try:
            df = pd.read_sql_query("SELECT * FROM transactions ORDER BY timestamp DESC", get_connection())
            if df.empty:
                messagebox.showinfo("Export", "Keine Daten zum Exportieren.")
                return
            path = f"export_{int(time.time())}.csv"
            df.to_csv(path, index=False)
            messagebox.showinfo("Export", f"CSV exportiert: {path}")
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def export_json():
        try:
            df = pd.read_sql_query("SELECT * FROM transactions ORDER BY timestamp DESC", get_connection())
            if df.empty:
                messagebox.showinfo("Export", "Keine Daten zum Exportieren.")
                return
            path = f"export_{int(time.time())}.json"
            df.to_json(path, orient='records', force_ascii=False)
            messagebox.showinfo("Export", f"JSON exportiert: {path}")
        except Exception as e:
            messagebox.showerror("Export", str(e))

    def show_history():
        try:
            hist = tracker.window_history[-5:]
            if not hist:
                messagebox.showinfo("Fenster-Historie", "Keine Einträge vorhanden.")
                return
            text = "\n".join(f"{ts.strftime('%H:%M:%S')} - {w}" for ts, w in hist)
            messagebox.showinfo("Fenster-Historie", text)
        except Exception as e:
            messagebox.showerror("Fenster-Historie", str(e))

    def view_data():
        s = start_entry.get() + " 00:00:00"
        e = end_entry.get() + " 23:59:59"
        
        # Determine filter mode and build query accordingly
        filter_mode = filter_mode_var.get()
        query = "SELECT * FROM transactions WHERE timestamp BETWEEN ? AND ?"
        params = [s, e]
        
        if filter_mode == "Preset wählen":
            # Filter by preset items
            preset_name = preset_var.get()
            if not preset_name:
                messagebox.showwarning("Preset", "Bitte wählen Sie ein Preset aus.")
                return
            
            preset = get_preset_by_name(preset_name)
            if not preset or not preset['items']:
                messagebox.showwarning("Preset", f"Preset '{preset_name}' ist leer oder existiert nicht.")
                return
            
            # Add IN clause for preset items
            placeholders = ','.join('?' * len(preset['items']))
            query += f" AND item_name IN ({placeholders})"
            params.extend(preset['items'])
            
        elif filter_mode == "Manuelle Eingabe":
            # Use manual filters (item name and type)
            item = item_entry.get().strip() or None
            ttype = type_entry.get().strip().lower() or None
            
            if item:
                query += " AND item_name LIKE ?"
                params.append(f"%{item}%")
            if ttype in ("buy", "sell"):
                query += " AND transaction_type = ?"
                params.append(ttype)
        # else: "Alles anzeigen" - no additional filters
        
        df = pd.read_sql_query(query, get_connection(), params=params)
        if df.empty:
            messagebox.showinfo("Ergebnis", "Keine Daten gefunden.")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['unit_price'] = df.apply(lambda r: (r['price'] / r['quantity']) if r['quantity'] else None, axis=1)

        def _fmt_currency(val):
            if pd.isna(val):
                return "-"
            try:
                return f"{int(round(val)):,}"
            except Exception:
                return str(val)

        total_trans = len(df)
        type_counts = df['transaction_type'].value_counts().to_dict()
        total_sales = df[df['transaction_type'] == 'sell']['price'].fillna(0).sum()
        total_buys = df[df['transaction_type'] == 'buy']['price'].fillna(0).sum()
        profit = total_sales - total_buys
        qty_sales = df[df['transaction_type'] == 'sell']['quantity'].fillna(0).sum()
        qty_buys = df[df['transaction_type'] == 'buy']['quantity'].fillna(0).sum()
        avg_unit_sell = df[df['transaction_type'] == 'sell']['unit_price'].dropna().mean()
        avg_unit_buy = df[df['transaction_type'] == 'buy']['unit_price'].dropna().mean()

        top_items = (
            df.groupby('item_name')['price']
            .sum()
            .fillna(0)
            .sort_values(ascending=False)
            .head(3)
        )
        top_items_text = ", ".join(
            f"{name} ({_fmt_currency(val)} Silver)" for name, val in top_items.items()
        ) or "-"

        result_window = tk.Toplevel(root)
        result_window.title("Datenübersicht")
        result_window.geometry("820x600")
        try:
            result_window.iconbitmap('config/icon.ico')
        except tk.TclError:
            pass  # Icon not found, continue without it

        summary_frame = tk.Frame(result_window)
        summary_frame.pack(fill="x", padx=12, pady=(12, 8))

        summary_lines = [
            f"Transaktionen gesamt: {total_trans} (Sell: {type_counts.get('sell', 0)} | Buy: {type_counts.get('buy', 0)})",
            f"Verkaufsvolumen: {_fmt_currency(total_sales)} Silver aus {int(qty_sales)} Einheiten",
            f"Kaufvolumen: {_fmt_currency(total_buys)} Silver aus {int(qty_buys)} Einheiten",
            f"Nettoumsatz (Sell-Buy): {_fmt_currency(profit)} Silver",
            f"Ø Stückpreis Sell: {_fmt_currency(avg_unit_sell)} Silver | Ø Stückpreis Buy: {_fmt_currency(avg_unit_buy)} Silver",
            f"Top Items (Summe): {top_items_text}",
        ]

        for line in summary_lines:
            tk.Label(summary_frame, text=line, anchor="w").pack(fill="x", pady=2)

        tree_frame = tk.Frame(result_window)
        tree_frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        columns = ("timestamp", "item", "qty", "price", "unit_price", "type", "case")
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        tree.heading("timestamp", text="Zeitstempel")
        tree.heading("item", text="Item")
        tree.heading("qty", text="Menge")
        tree.heading("price", text="Preis (Silver)")
        tree.heading("unit_price", text="Preis/Einheit")
        tree.heading("type", text="Typ")
        tree.heading("case", text="Fall")
        tree.column("timestamp", width=150, anchor="w")
        tree.column("item", width=200, anchor="w")
        tree.column("qty", width=80, anchor="center")
        tree.column("price", width=130, anchor="e")
        tree.column("unit_price", width=130, anchor="e")
        tree.column("type", width=70, anchor="center")
        tree.column("case", width=120, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        for _, row in df.iterrows():
            ts = row['timestamp'].strftime("%Y-%m-%d %H:%M:%S")
            qty = int(row['quantity']) if not pd.isna(row['quantity']) else "-"
            price_val = row['price'] if not pd.isna(row['price']) else None
            unit_val = row['unit_price'] if not pd.isna(row['unit_price']) else None
            tree.insert(
                "",
                "end",
                values=(
                    ts,
                    row['item_name'],
                    qty,
                    _fmt_currency(price_val),
                    _fmt_currency(unit_val),
                    row['transaction_type'],
                    row.get('tx_case', "-"),
                ),
            )

        button_frame = tk.Frame(result_window)
        button_frame.pack(fill="x", padx=12, pady=(0, 12))

        def show_price_plot():
            # Compact price summary + sparkline embedded in a Toplevel window
            unit_series = df['unit_price'].dropna()
            if unit_series.empty:
                messagebox.showinfo("Preisverlauf", "Keine gültigen Stückpreise zum Anzeigen.")
                return

            min_v = unit_series.min()
            max_v = unit_series.max()
            mean_v = unit_series.mean()
            median_v = unit_series.median()
            last_vals = (
                df[['timestamp', 'unit_price']]
                .dropna()
                .sort_values('timestamp')
                .tail(10)
            )

            win = tk.Toplevel(root)
            win.title("Preisübersicht")
            win.geometry("720x360")
            try:
                win.iconbitmap('config/icon.ico')
            except tk.TclError:
                pass

            summary_frame = tk.Frame(win)
            summary_frame.pack(fill="x", padx=12, pady=8)
            tk.Label(summary_frame, text=f"Anzahl Werte: {len(unit_series)}").grid(row=0, column=0, sticky="w")
            tk.Label(summary_frame, text=f"Min: {int(round(min_v)):,} Silver").grid(row=0, column=1, sticky="w", padx=12)
            tk.Label(summary_frame, text=f"Max: {int(round(max_v)):,} Silver").grid(row=0, column=2, sticky="w", padx=12)
            tk.Label(summary_frame, text=f"Ø: {int(round(mean_v)):,} Silver").grid(row=0, column=3, sticky="w", padx=12)
            tk.Label(summary_frame, text=f"Median: {int(round(median_v)):,} Silver").grid(row=0, column=4, sticky="w", padx=12)

            plot_frame = tk.Frame(win)
            plot_frame.pack(fill="x", padx=12)
            fig = Figure(figsize=(6, 2), dpi=100)
            ax = fig.add_subplot(111)
            timestamps = pd.to_datetime(df['timestamp'])
            ax.plot(timestamps, df['unit_price'], marker='o', linewidth=1)
            ax.set_title("Stückpreis (Sparkline)")
            ax.set_ylabel("Silver")
            ax.get_xaxis().set_visible(False)
            fig.tight_layout()
            canvas = FigureCanvasTkAgg(fig, master=plot_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill="both", expand=True)

            recent_frame = tk.Frame(win)
            recent_frame.pack(fill="both", expand=True, padx=12, pady=(8, 12))
            cols = ("time", "price")
            tree = ttk.Treeview(recent_frame, columns=cols, show="headings", height=6)
            tree.heading("time", text="Zeit")
            tree.heading("price", text="Preis/Einheit")
            tree.column("time", width=180)
            tree.column("price", width=120, anchor="e")
            tree.pack(side="left", fill="both", expand=True)
            vsb = ttk.Scrollbar(recent_frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            vsb.pack(side="right", fill="y")

            for _, r in last_vals.iterrows():
                t = pd.to_datetime(r['timestamp']).strftime("%Y-%m-%d %H:%M:%S")
                p = int(round(r['unit_price']))
                tree.insert("", "end", values=(t, f"{p:,}"))

        ttk.Button(button_frame, text="Preisverlauf anzeigen", command=show_price_plot).pack(side="left")
        ttk.Button(button_frame, text="Fenster schließen", command=result_window.destroy).pack(side="right")

    def manage_presets():
        """Open preset management window"""
        manager_window = tk.Toplevel(root)
        manager_window.title("Preset-Verwaltung")
        manager_window.geometry("700x500")
        try:
            manager_window.iconbitmap('config/icon.ico')
        except tk.TclError:
            pass
        
        # Preset list (TreeView)
        list_frame = tk.Frame(manager_window)
        list_frame.pack(fill="both", expand=True, padx=12, pady=12)
        
        columns = ("name", "items_count")
        preset_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        preset_tree.heading("name", text="Preset-Name")
        preset_tree.heading("items_count", text="Anzahl Items")
        preset_tree.column("name", width=400)
        preset_tree.column("items_count", width=150, anchor="center")
        
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=preset_tree.yview)
        preset_tree.configure(yscrollcommand=vsb.set)
        preset_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        
        def refresh_preset_list():
            """Reload presets from database"""
            preset_tree.delete(*preset_tree.get_children())
            presets = get_all_presets()
            for preset in presets:
                preset_tree.insert("", "end", values=(preset['name'], len(preset['items'])))
        
        refresh_preset_list()
        
        def create_or_edit_preset(edit_mode=False):
            """Dialog to create or edit a preset"""
            selected = preset_tree.selection()
            if edit_mode and not selected:
                messagebox.showwarning("Bearbeiten", "Bitte wählen Sie ein Preset aus.")
                return
            
            # Load existing preset if editing
            existing_preset = None
            if edit_mode:
                preset_name = preset_tree.item(selected[0])['values'][0]
                existing_preset = get_preset_by_name(preset_name)
                if not existing_preset:
                    messagebox.showerror("Fehler", f"Preset '{preset_name}' nicht gefunden.")
                    return
            
            # Create dialog
            dialog = tk.Toplevel(manager_window)
            dialog.title("Preset bearbeiten" if edit_mode else "Neues Preset")
            dialog.geometry("600x500")
            try:
                dialog.iconbitmap('config/icon.ico')
            except tk.TclError:
                pass
            dialog.transient(manager_window)
            dialog.grab_set()
            
            # Name field
            name_frame = tk.Frame(dialog)
            name_frame.pack(fill="x", padx=12, pady=12)
            tk.Label(name_frame, text="Preset-Name:").pack(side="left")
            name_entry = tk.Entry(name_frame, width=40)
            name_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
            
            if existing_preset:
                name_entry.insert(0, existing_preset['name'])
                name_entry.config(state="readonly")  # Don't allow renaming
            
            # Items field
            items_frame = tk.Frame(dialog)
            items_frame.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            tk.Label(items_frame, text="Items (ein Item pro Zeile):").pack(anchor="w")
            
            items_text = tk.Text(items_frame, wrap="word", height=20)
            items_text.pack(fill="both", expand=True, pady=(4, 0))
            items_scroll = ttk.Scrollbar(items_text, orient="vertical", command=items_text.yview)
            items_text.configure(yscrollcommand=items_scroll.set)
            items_scroll.pack(side="right", fill="y")
            
            if existing_preset:
                items_text.insert("1.0", "\n".join(existing_preset['items']))
            
            # Buttons
            button_frame = tk.Frame(dialog)
            button_frame.pack(fill="x", padx=12, pady=(0, 12))
            
            def save_preset_data():
                preset_name = name_entry.get().strip()
                if not preset_name:
                    messagebox.showwarning("Validierung", "Bitte geben Sie einen Namen ein.")
                    return
                
                items_content = items_text.get("1.0", "end-1c").strip()
                if not items_content:
                    messagebox.showwarning("Validierung", "Bitte geben Sie mindestens ein Item ein.")
                    return
                
                # Parse items (one per line, remove empty lines)
                items_list = [line.strip() for line in items_content.split("\n") if line.strip()]
                
                if not items_list:
                    messagebox.showwarning("Validierung", "Keine gültigen Items gefunden.")
                    return
                
                # Save to database
                success = save_preset(preset_name, items_list)
                if success:
                    messagebox.showinfo("Erfolg", f"Preset '{preset_name}' gespeichert ({len(items_list)} Items).")
                    refresh_preset_list()
                    update_preset_list()  # Update main filter dropdown
                    dialog.destroy()
                else:
                    messagebox.showerror("Fehler", f"Preset '{preset_name}' konnte nicht gespeichert werden.")
            
            ttk.Button(button_frame, text="Speichern", style="Accent.TButton", command=save_preset_data).pack(side="left")
            ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side="left", padx=6)
        
        def delete_selected_preset():
            """Delete selected preset"""
            selected = preset_tree.selection()
            if not selected:
                messagebox.showwarning("Löschen", "Bitte wählen Sie ein Preset aus.")
                return
            
            preset_name = preset_tree.item(selected[0])['values'][0]
            
            # Confirm deletion
            confirm = messagebox.askyesno(
                "Bestätigung",
                f"Möchten Sie das Preset '{preset_name}' wirklich löschen?"
            )
            if not confirm:
                return
            
            success = delete_preset(preset_name)
            if success:
                messagebox.showinfo("Erfolg", f"Preset '{preset_name}' wurde gelöscht.")
                refresh_preset_list()
                update_preset_list()  # Update main filter dropdown
            else:
                messagebox.showerror("Fehler", f"Preset '{preset_name}' konnte nicht gelöscht werden.")
        
        # Management buttons
        button_frame = tk.Frame(manager_window)
        button_frame.pack(fill="x", padx=12, pady=(0, 12))
        ttk.Button(button_frame, text="Neu", style="Accent.TButton", command=lambda: create_or_edit_preset(False)).pack(side="left")
        ttk.Button(button_frame, text="Bearbeiten", command=lambda: create_or_edit_preset(True)).pack(side="left", padx=6)
        ttk.Button(button_frame, text="Löschen", command=delete_selected_preset).pack(side="left")
        ttk.Button(button_frame, text="Schließen", command=manager_window.destroy).pack(side="right")

    buttons_row = tk.Frame(data_frame)
    buttons_row.pack(fill="x", pady=(10, 0))
    ttk.Button(buttons_row, text="Daten anzeigen", style="Accent.TButton", command=view_data).pack(side="left")
    ttk.Button(buttons_row, text="Export CSV", command=export_csv).pack(side="left", padx=6)
    ttk.Button(buttons_row, text="Export JSON", command=export_json).pack(side="left")
    ttk.Button(buttons_row, text="Fenster-Historie", command=show_history).pack(side="left", padx=6)
    ttk.Button(buttons_row, text="Presets verwalten", command=manage_presets).pack(side="right")

    def on_close():
        try:
            tracker.stop()
            time.sleep(0.1)
        finally:
            try:
                conn.close()
            except:
                pass
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()

if __name__ == "__main__":
    start_gui()