"""Builds the main window widgets."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .. import __version__, i18n
from ..i18n import tr
from ..rounded_panel import RoundedPanel
from .common import (
    ACCENT,
    BACKGROUND,
)


class LayoutMixin:
    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg="#1D1C31", height=self._px(96))
        header.pack(fill="x")
        header.pack_propagate(False)
        header_content = tk.Frame(header, bg="#1D1C31")
        header_content.pack(fill="both", expand=True, padx=self._px(26), pady=self._px(16))
        if hasattr(self, "header_icon"):
            self.header_icon_label = tk.Label(header_content, image=self.header_icon, bg="#1D1C31")
            self.header_icon_label.pack(side="left", padx=(0, self._px(15)))
        titles = tk.Frame(header_content, bg="#1D1C31")
        titles.pack(side="left", fill="y")
        tk.Label(titles, text="CNTag", bg="#1D1C31", fg="#FFFFFF", font=(self.ui_semibold, 24)).pack(anchor="w")
        tk.Label(titles, text=tr("还中文音乐库以中文标签与文件名"), bg="#1D1C31", fg="#BAB8D0", font=(self.cjk_font, 10)).pack(anchor="w")
        tk.Label(header_content, text=tr("拼音 / 英文标签  →  中文标签"), bg="#1D1C31", fg="#BDB5FF", font=(self.ui_semibold, 12)).pack(side="right", pady=self._px(14))

        body = ttk.Frame(self.root, padding=(self._px(22), self._px(18), self._px(22), self._px(12)))
        body.pack(fill="both", expand=True)

        content = ttk.Frame(body)
        content.pack(fill="both", expand=True)
        left_panel = RoundedPanel(content, padding=self._px(18), width=self._px(405), radius=self._px(10))
        left = left_panel.content
        left_panel.pack(side="left", fill="y", padx=(0, self._px(12)))
        left_panel.pack_propagate(False)
        ttk.Label(left, text=tr("音乐库"), style="Title.Card.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(
            left,
            text=tr("选择音乐库文件夹后在此显示专辑"),
            style="Muted.Card.TLabel",
            justify="left",
            wraplength=self._px(360),
        ).pack(anchor="w")
        ttk.Label(left, textvariable=self.library_var, style="Muted.Card.TLabel").pack(side="bottom", anchor="w", pady=(10, 0))

        right_column = ttk.Frame(content)
        right_column.pack(side="left", fill="both", expand=True)
        candidates_panel = RoundedPanel(right_column, padding=self._px(18), radius=self._px(10))
        candidates = candidates_panel.content
        candidates_panel.pack(fill="both", expand=True, pady=(0, self._px(12)))
        ttk.Label(candidates, text=tr("候选专辑"), style="Title.Card.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(
            candidates,
            text=tr("这里会列出可还原为中文的候选专辑"),
            style="Muted.Card.TLabel",
            justify="left",
        ).pack(anchor="w")

        compare_panel = RoundedPanel(right_column, padding=self._px(18), radius=self._px(10))
        compare = compare_panel.content
        compare_panel.pack(fill="both", expand=True)
        ttk.Label(compare, text=tr("标签对比"), style="Title.Card.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(
            compare,
            text=tr("这里会对比当前标签与即将写入的中文标签"),
            style="Muted.Card.TLabel",
            justify="left",
        ).pack(anchor="w")

        status_bar = ttk.Frame(self.root)
        status_bar.pack(side="bottom", fill="x")
        status = ttk.Label(status_bar, textvariable=self.status_var, padding=(self._px(22), 0, self._px(12), self._px(10)), anchor="w")
        status.pack(side="left", fill="x", expand=True)
        version_frame = tk.Frame(status_bar, bg=BACKGROUND)
        version_frame.pack(side="right", padx=(self._px(12), self._px(22)))
        self.github_link = tk.Label(
            version_frame,
            text=f"GitHub  ·  v{__version__}",
            bg=BACKGROUND,
            fg=ACCENT,
            font=(self.ui_font, 10),
            cursor="hand2",
            padx=0,
            pady=self._px(7),
        )
        self.language_link = tk.Label(
            version_frame,
            text="English" if i18n.language() == "zh" else "中文",
            bg=BACKGROUND,
            fg=ACCENT,
            font=(self.ui_font, 10),
            cursor="hand2",
            padx=0,
            pady=self._px(7),
        )
        self.language_link.pack(side="left", padx=(0, self._px(14)))
        self.language_link.bind("<Button-1>", lambda _event: self._switch_language())
        self.github_link.pack(side="left")
        self.update_dot = tk.Label(
            version_frame,
            text="●",
            bg=BACKGROUND,
            fg="#1A9B72",
            font=(self.ui_font, 9),
            cursor="hand2",
            padx=0,
        )
        self.github_link.bind("<Button-1>", lambda _event: self._open_latest_release())
        self.update_dot.bind("<Button-1>", lambda _event: self._open_latest_release())
