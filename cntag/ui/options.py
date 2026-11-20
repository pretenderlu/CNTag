"""Options bar: sources, country, conversion, threshold, rename — persisted."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..i18n import tr
from ..models import ScanOptions, normalize_sources
from .common import CARD

COUNTRIES = ("tw", "cn", "hk", "jp", "us")


def country_names() -> list[str]:
    return [tr("台湾"), tr("中国大陆"), tr("香港"), tr("日本"), tr("美国")]


def _float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class OptionsMixin:
    def _init_option_vars(self) -> None:
        """Create the option variables from loaded settings."""
        settings = getattr(self, "settings", {}) or {}
        saved_sources = normalize_sources(settings.get("sources"))
        self.src_itunes_var = tk.BooleanVar(value="itunes" in saved_sources)
        self.src_netease_var = tk.BooleanVar(value="netease" in saved_sources)
        country = str(settings.get("country", "tw"))
        self.country_index = COUNTRIES.index(country) if country in COUNTRIES else 0
        self.country_var = tk.StringVar(value=country_names()[self.country_index])
        self.simplified_var = tk.BooleanVar(value=bool(settings.get("simplified", True)))
        self.encyclopedia_var = tk.BooleanVar(value=bool(settings.get("encyclopedia", True)))
        threshold = _float(settings.get("threshold"), 0.6)
        self.threshold_var = tk.StringVar(value=f"{min(max(threshold, 0.3), 0.95):.2f}")
        self.rename_var = tk.BooleanVar(value=bool(settings.get("rename", False)))

    def _build_options_bar(self, parent) -> None:
        self._init_option_vars()
        bar = tk.Frame(parent, bg=CARD, highlightthickness=1,
                       highlightbackground="#E3E6EF")
        bar.pack(fill="x", pady=(self._px(12), 0))
        inner = tk.Frame(bar, bg=CARD)
        inner.pack(fill="x", padx=self._px(14), pady=self._px(8))

        self._option_widgets: list[tk.Widget] = []

        def add(widget) -> None:
            widget.pack(side="left", padx=(0, self._px(10)))
            self._option_widgets.append(widget)

        ttk.Label(inner, text=tr("数据源"), style="Card.TLabel").pack(
            side="left", padx=(0, self._px(6)))
        add(ttk.Checkbutton(inner, text="iTunes", variable=self.src_itunes_var,
                            command=self._sources_changed))
        add(ttk.Checkbutton(inner, text=tr("网易云"), variable=self.src_netease_var,
                            command=self._sources_changed))

        ttk.Label(inner, text=tr("iTunes 地区"), style="Card.TLabel").pack(
            side="left", padx=(self._px(8), self._px(6)))
        self.country_combo = ttk.Combobox(inner, textvariable=self.country_var,
                                          values=country_names(), state="readonly",
                                          width=8)
        self.country_combo.bind("<<ComboboxSelected>>", lambda _e: self._options_changed())
        add(self.country_combo)

        add(ttk.Checkbutton(inner, text=tr("繁转简"), variable=self.simplified_var,
                            command=self._options_changed))
        add(ttk.Checkbutton(inner, text=tr("百科解析"), variable=self.encyclopedia_var,
                            command=self._options_changed))

        ttk.Label(inner, text=tr("置信度阈值"), style="Card.TLabel").pack(
            side="left", padx=(self._px(8), self._px(6)))
        self.threshold_spin = ttk.Spinbox(inner, from_=0.3, to=0.95, increment=0.05,
                                          textvariable=self.threshold_var, width=5,
                                          command=self._options_changed)
        self.threshold_spin.bind("<FocusOut>", lambda _e: self._options_changed())
        add(self.threshold_spin)

        add(ttk.Checkbutton(inner, text=tr("同时重命名文件"), variable=self.rename_var,
                            command=self._options_changed))

        # Right side: undo + apply.
        self._build_apply_bar(inner)

    def _sources_changed(self) -> None:
        """Keep at least one source selected."""
        if not self.src_itunes_var.get() and not self.src_netease_var.get():
            self.src_itunes_var.set(True)
        self._options_changed()

    def _options_changed(self) -> None:
        self._update_apply_count()
        try:
            self._save_settings()
        except Exception:
            pass

    def _threshold(self) -> float:
        return _float(self.threshold_var.get(), 0.6)

    def _country(self) -> str:
        try:
            index = country_names().index(self.country_var.get())
        except ValueError:
            index = self.country_index
        return COUNTRIES[index]

    def scan_options(self) -> ScanOptions:
        sources = []
        if self.src_itunes_var.get():
            sources.append("itunes")
        if self.src_netease_var.get():
            sources.append("netease")
        return ScanOptions(
            country=self._country(),
            simplified=self.simplified_var.get(),
            sources=normalize_sources(sources),
            use_encyclopedia=self.encyclopedia_var.get(),
            threshold=self._threshold(),
        )

    def _set_options_state(self) -> None:
        """Disable option widgets while scanning or applying."""
        busy = getattr(self, "scanning", False) or getattr(self, "applying", False)
        state = "disabled" if busy else "normal"
        for widget in getattr(self, "_option_widgets", []):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        if hasattr(self, "country_combo"):
            self.country_combo.configure(state="disabled" if busy else "readonly")

    def _persistable_options(self) -> dict:
        sources = []
        if self.src_itunes_var.get():
            sources.append("itunes")
        if self.src_netease_var.get():
            sources.append("netease")
        return {
            "sources": normalize_sources(sources),
            "country": self._country(),
            "simplified": bool(self.simplified_var.get()),
            "encyclopedia": bool(self.encyclopedia_var.get()),
            "threshold": self._threshold(),
            "rename": bool(self.rename_var.get()),
            "library": getattr(self, "library_path", "") or "",
        }
