import tkinter as tk
import threading
import time
from tkinter import messagebox, ttk
import pandas as pd
import matplotlib.pyplot as plt
import datetime

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

# -----------------------
# GUI
# -----------------------
def start_gui():
    tracker = MarketTracker(debug=get_debug_mode(True))

    root = tk.Tk()
    root.title("BDO Market Tracker")
    root.geometry("520x640")

    tk.Label(root, text="Screen-Region (x1,y1,x2,y2):").pack()
    region_entry = tk.Entry(root)
    region_entry.insert(0, ",".join(map(str, DEFAULT_REGION)))
    region_entry.pack()

    use_gpu_var = tk.BooleanVar(value=get_use_gpu(USE_GPU))
    debug_var = tk.BooleanVar(value=tracker.debug)

    status_var = tk.StringVar(value="Idle")

    def _apply_region_from_entry():
        try:
            parts = [int(p.strip()) for p in region_entry.get().split(',')]
            if len(parts) == 4:
                region = tuple(parts)
                tracker.region = region
                set_capture_region(region)
        except Exception:
            pass

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
            messagebox.showinfo("Info", "Einzel-Scan abgeschlossen.")
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    auto_thread = {"thread": None}

    def start_auto():
        if tracker.running:
            messagebox.showinfo("Info", "Auto-Tracking läuft bereits.")
            return
        status_var.set("Running")
        _apply_region_from_entry()
        # Log auto-track start in ocr_log.txt
        from utils import log_debug
        log_debug("[AUTO-TRACK] ▶️ STARTED - Auto-Track mode enabled")
        t = threading.Thread(target=tracker.auto_track, daemon=True)
        auto_thread["thread"] = t
        t.start()
        messagebox.showinfo("Info", "Auto-Tracking gestartet.")

    def stop_auto():
        # Log auto-track stop in ocr_log.txt
        from utils import log_debug
        log_debug("[AUTO-TRACK] ⏸️ STOPPED - Auto-Track mode disabled")
        tracker.stop()
        status_var.set("Idle")
        messagebox.showinfo("Info", "Auto-Tracking gestoppt.")

    # Debug Toggle
    def toggle_debug():
        tracker.debug = not tracker.debug
        debug_var.set(tracker.debug)
        set_debug_mode(tracker.debug)
        messagebox.showinfo("Debug", f"Debug ist nun {'AN' if tracker.debug else 'AUS'}")

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

    tk.Button(root, text="Region festlegen", command=start_region_selection).pack(pady=6)
    tk.Button(root, text="Einmal scannen", command=run_single).pack(pady=6)
    tk.Button(root, text="Auto-Tracking starten", command=start_auto).pack(pady=6)
    tk.Button(root, text="Auto-Tracking stoppen", command=stop_auto).pack(pady=6)

    settings_frame = tk.LabelFrame(root, text="Einstellungen", padx=8, pady=8)
    settings_frame.pack(fill="x", padx=12, pady=8)

    tk.Checkbutton(settings_frame, text="GPU-Modus verwenden", variable=use_gpu_var).pack(anchor="w")
    tk.Checkbutton(settings_frame, text="Debug-Modus", variable=debug_var).pack(anchor="w")
    tk.Button(settings_frame, text="Übernehmen", command=_apply_settings).pack(pady=(8, 0))
    tk.Label(root, textvariable=status_var).pack(pady=4)
    
    # System Health Status
    health_status_var = tk.StringVar(value="🟢 Healthy")
    health_label = tk.Label(root, textvariable=health_status_var, font=("Arial", 10, "bold"))
    health_label.pack(pady=2)
    
    # Live Window Status
    window_status_var = tk.StringVar(value="Window: -")
    tk.Label(root, textvariable=window_status_var, fg="blue").pack(pady=2)
    
    def update_health_status():
        """Update health status display every 500ms"""
        try:
            # Check error count and determine health
            error_count = getattr(tracker, 'error_count', 0)
            last_error_time = getattr(tracker, 'last_error_time', None)
            
            # Health logic
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
    tk.Label(root, text="Zeitraum (YYYY-MM-DD):").pack()
    start_entry = tk.Entry(root); start_entry.insert(0, str(datetime.date.today())); start_entry.pack()
    end_entry = tk.Entry(root); end_entry.insert(0, str(datetime.date.today())); end_entry.pack()
    tk.Label(root, text="Item (optional):").pack(); item_entry = tk.Entry(root); item_entry.pack()
    tk.Label(root, text="Typ (buy/sell - optional):").pack(); type_entry = tk.Entry(root); type_entry.pack()

    def view_data():
        s = start_entry.get() + " 00:00:00"
        e = end_entry.get() + " 23:59:59"
        item = item_entry.get().strip() or None
        ttype = type_entry.get().strip().lower() or None
        query = "SELECT * FROM transactions WHERE timestamp BETWEEN ? AND ?"
        params = [s, e]
        if item:
            query += " AND item_name LIKE ?"
            params.append(f"%{item}%")
        if ttype in ("buy", "sell"):
            query += " AND transaction_type = ?"
            params.append(ttype)
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
            plt.figure(figsize=(10, 5))
            for t in df['transaction_type'].dropna().unique():
                sub = df[df['transaction_type'] == t]
                plt.plot(sub['timestamp'], sub['unit_price'], marker='o', label=t.upper())
            plt.title("Stückpreisverlauf")
            plt.xlabel("Zeit")
            plt.ylabel("Preis pro Einheit (Silver)")
            plt.legend()
            plt.tight_layout()
            plt.show()

        tk.Button(button_frame, text="Preisverlauf anzeigen", command=show_price_plot).pack(side="left")
        tk.Button(button_frame, text="Fenster schließen", command=result_window.destroy).pack(side="right")

    tk.Button(root, text="Daten anzeigen", command=view_data).pack(pady=8)

    # Export-Funktionen
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
            messagebox.showerror("Export-Fehler", str(e))

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
            messagebox.showerror("Export-Fehler", str(e))

    tk.Button(root, text="Export CSV", command=export_csv).pack(pady=4)
    tk.Button(root, text="Export JSON", command=export_json).pack(pady=4)

    def show_history():
        try:
            hist = tracker.window_history[-5:]
            if not hist:
                messagebox.showinfo("Fenster-Historie", "Keine Einträge vorhanden.")
                return
            text = "\n".join(f"{ts.strftime('%H:%M:%S')} - {w}" for ts, w in hist)
            messagebox.showinfo("Fenster-Historie", text)
        except Exception as e:
            messagebox.showerror("Fehler", str(e))

    tk.Button(root, text="Fenster-Historie", command=show_history).pack(pady=4)

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