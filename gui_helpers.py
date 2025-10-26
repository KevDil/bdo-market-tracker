from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import tkinter as tk
from tkinter import ttk


@dataclass
class Palette:
    primary: str
    accent: str
    warning: str
    success: str
    error: str
    text_primary: str
    text_secondary: str
    background: str
    surface: str

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "Palette":
        return cls(
            primary=data["primary"],
            accent=data["accent"],
            warning=data["warning"],
            success=data["success"],
            error=data["error"],
            text_primary=data["text_primary"],
            text_secondary=data["text_secondary"],
            background=data["background"],
            surface=data["surface"],
        )


class ThemeManager:
    """Handles ttk style configuration for light/dark palettes."""

    def __init__(self, root: tk.Tk, style: ttk.Style, palettes: dict[str, Palette], default: str = "light") -> None:
        self.root = root
        self.style = style
        self.palettes = palettes
        self.current_theme = default

    def apply(self, theme_name: str) -> None:
        if theme_name not in self.palettes:
            raise ValueError(f"Unknown theme '{theme_name}'")

        self.current_theme = theme_name
        palette = self.palettes[theme_name]
        self._apply_palette(palette)

    def toggle(self) -> str:
        new_theme = "dark" if self.current_theme == "light" else "light"
        self.apply(new_theme)
        return new_theme

    def _apply_palette(self, palette: Palette) -> None:
        bg = palette.background
        fg = palette.text_primary
        secondary_fg = palette.text_secondary

        # Configure root colors (Tk widgets inherit these)
        self.root.configure(bg=bg)

        # Base styles
        self.style.configure("TFrame", background=palette.surface)
        self.style.configure("Root.TFrame", background=bg)
        self.style.configure("TLabel", background=palette.surface, foreground=fg)
        self.style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), background=bg, foreground=palette.primary)
        self.style.configure("SubHeader.TLabel", font=("Segoe UI", 10), background=bg, foreground=secondary_fg)
        self.style.configure(
            "Section.TLabelframe",
            background=palette.surface,
            foreground=palette.primary,
            padding=12,
        )
        self.style.configure(
            "Section.TLabelframe.Label",
            font=("Segoe UI", 11, "bold"),
            foreground=palette.primary,
        )

        # Buttons
        self.style.configure(
            "TButton",
            background=palette.surface,
            foreground=fg,
            relief="flat",
            padding=(10, 6),
        )
        self.style.configure(
            "Accent.TButton",
            background=palette.accent,
            foreground="#ffffff",
            padding=(12, 6),
        )
        self.style.configure(
            "Danger.TButton",
            background=palette.error,
            foreground="#ffffff",
            padding=(12, 6),
        )
        self.style.map(
            "Accent.TButton",
            background=[("active", palette.primary), ("pressed", palette.primary)],
        )
        self.style.map(
            "Danger.TButton",
            background=[("active", palette.warning), ("pressed", palette.warning)],
        )

        # Status Labels
        self.style.configure("Status.Green.TLabel", foreground=palette.success, background=palette.surface)
        self.style.configure("Status.Yellow.TLabel", foreground=palette.warning, background=palette.surface)
        self.style.configure("Status.Red.TLabel", foreground=palette.error, background=palette.surface)

        # Progressbar
        self.style.configure(
            "TProgressbar",
            troughcolor=palette.surface,
            background=palette.accent,
            bordercolor=palette.surface,
            lightcolor=palette.accent,
            darkcolor=palette.primary,
        )

        # Entries
        self.style.configure(
            "Valid.TEntry",
            fieldbackground=palette.surface,
            foreground=fg,
            padding=4,
        )
        self.style.configure(
            "Invalid.TEntry",
            fieldbackground="#FFE4E4" if self.current_theme == "light" else "#4B2C31",
            foreground=fg,
            padding=4,
        )
        self.style.map(
            "Invalid.TEntry",
            fieldbackground=[("focus", "#FFC6C6" if self.current_theme == "light" else "#5C2F38")],
        )

        # Notebook
        self.style.configure(
            "TNotebook",
            background=bg,
            borderwidth=0,
            tabmargins=(6, 6, 6, 0),
        )
        self.style.configure(
            "TNotebook.Tab",
            padding=(14, 8),
            background=palette.surface,
            foreground=secondary_fg,
            font=("Segoe UI", 10, "bold"),
        )
        self.style.map(
            "TNotebook.Tab",
            background=[("selected", palette.background), ("active", palette.accent)],
            foreground=[("selected", palette.primary), ("active", palette.text_primary)],
        )

        # Treeview colors
        self.style.configure(
            "Treeview",
            background=palette.surface,
            foreground=fg,
            fieldbackground=palette.surface,
            rowheight=24,
        )
        self.style.configure(
            "Treeview.Heading",
            background=palette.primary,
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
        )
        self.style.map("Treeview.Heading", relief=[("active", "groove")])

        # Checkbuttons
        self.style.configure(
            "Settings.TCheckbutton",
            background=palette.surface,
            foreground=fg,
            focuscolor=palette.accent,
            padding=4,
            font=("Segoe UI", 10),
        )
        self.style.map(
            "Settings.TCheckbutton",
            background=[("active", palette.surface)],
            foreground=[("active", fg), ("selected", palette.primary)],
            indicatorcolor=[("selected", palette.accent), ("alternate", palette.warning)],
            indicatorbackground=[("selected", palette.accent)],
        )


class Tooltip:
    """Create a tooltip for a given widget."""

    def __init__(self, widget: tk.Widget, text: str, *, delay: int = 500) -> None:
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after_id: str | None = None
        self._tip_window: tk.Toplevel | None = None
        self.widget.bind("<Enter>", self._schedule)
        self.widget.bind("<Leave>", self._hide)
        self.widget.bind("<ButtonPress>", self._hide)

    def _schedule(self, _event=None) -> None:
        self._cancel_schedule()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel_schedule(self) -> None:
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None

    def _show(self) -> None:
        if self._tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 10
        self._tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(tw, text=self.text, background="#1F2933", foreground="white", padding=(8, 4))
        label.pack()

    def _hide(self, _event=None) -> None:
        self._cancel_schedule()
        if self._tip_window is not None:
            self._tip_window.destroy()
            self._tip_window = None


def parse_region_text(value: str) -> tuple[int, int, int, int] | None:
    try:
        parts = [int(part.strip()) for part in value.split(",")]
        if len(parts) != 4:
            return None
        left, top, right, bottom = parts
        if right <= left or bottom <= top:
            return None
        return left, top, right, bottom
    except Exception:
        return None


def make_treeview_sortable(tree: ttk.Treeview, numeric_columns: Iterable[str] | None = None) -> None:
    """Enable column sorting on a ttk.Treeview."""

    numeric_columns = set(numeric_columns or [])

    def _sort(col: str, reverse: bool) -> None:
        def _parse(value: str) -> tuple:
            if col in numeric_columns:
                cleaned = value.replace(",", "").replace(" Silver", "").strip()
                try:
                    return float(cleaned)
                except ValueError:
                    return 0.0
            return value

        data = [(_parse(tree.set(k, col)), k) for k in tree.get_children("")]
        data.sort(reverse=reverse)
        for index, (_val, k) in enumerate(data):
            tree.move(k, "", index)
        tree.heading(col, command=lambda: _sort(col, not reverse))

    for col in tree["columns"]:
        tree.heading(col, command=lambda c=col: _sort(c, False))


def bind_hotkey(root: tk.Tk, sequence: str, callback: Callable[[tk.Event], None]) -> None:
    """Bind a global hotkey without triggering default key propagation."""

    def _handler(event: tk.Event) -> str:
        callback(event)
        return "break"

    root.bind(sequence, _handler)
