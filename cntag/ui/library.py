"""Library card: folder selection, scanning, album list."""
from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from ..i18n import tr
from ..library import group_albums
from ..scanner import scan_album


def filter_names() -> list[str]:
    return [tr("全部"), tr("待确认"), tr("未匹配"), tr("已匹配")]


FILTER_STATUSES = (None, "needs_confirm", "unmatched", "matched")


def status_label(status: str) -> str:
    return {
        "matched": tr("✓ 已匹配"),
        "needs_confirm": tr("? 待确认"),
        "unmatched": tr("— 未匹配"),
        "error": tr("! 出错"),
        "applied": tr("● 已应用"),
    }.get(status, status)


class LibraryMixin:
    def _build_library_card(self, parent) -> None:
        ttk.Label(parent, text=tr("音乐库"), style="Title.Card.TLabel").pack(
            anchor="w", pady=(0, self._px(10)))

        self.choose_button = ttk.Button(parent, text=tr("选择文件夹…"),
                                        command=self._choose_folder)
        self.choose_button.pack(anchor="w")
        ttk.Label(parent, textvariable=self.library_var, style="Muted.Card.TLabel",
                  wraplength=self._px(330), justify="left").pack(
            anchor="w", pady=(self._px(6), self._px(10)))

        scan_row = ttk.Frame(parent)
        scan_row.pack(fill="x")
        self.scan_button = ttk.Button(scan_row, text=tr("开始扫描"),
                                      style="Accent.TButton", command=self._toggle_scan)
        self.scan_button.pack(side="left")
        self.progress = ttk.Progressbar(scan_row, mode="determinate", length=self._px(120))
        self.progress.pack(side="left", padx=(self._px(10), self._px(6)), fill="x", expand=True)
        self.album_count_var = tk.StringVar(value="")
        ttk.Label(scan_row, textvariable=self.album_count_var,
                  style="Muted.Card.TLabel").pack(side="left")

        self.filter_var = tk.StringVar(value=filter_names()[0])
        self.filter_combo = ttk.Combobox(parent, textvariable=self.filter_var,
                                         values=filter_names(), state="readonly")
        self.filter_combo.pack(fill="x", pady=(self._px(10), self._px(6)))
        self.filter_combo.bind("<<ComboboxSelected>>", lambda _e: self._refilter_albums())

        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True)
        columns = ("status", "folder", "files", "match")
        self.album_tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                       selectmode="browse")
        self.album_tree.heading("status", text=tr("状态"))
        self.album_tree.heading("folder", text=tr("文件夹"))
        self.album_tree.heading("files", text=tr("文件"))
        self.album_tree.heading("match", text=tr("匹配"))
        self.album_tree.column("status", width=self._px(70), stretch=False)
        self.album_tree.column("folder", width=self._px(170), stretch=False)
        self.album_tree.column("files", width=self._px(40), stretch=False, anchor="center")
        self.album_tree.column("match", width=self._px(160))
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical",
                                  command=self.album_tree.yview)
        self.album_tree.configure(yscrollcommand=scrollbar.set)
        self.album_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.album_tree.bind("<<TreeviewSelect>>", self._on_album_select)

        # Restore last library path (display only; nothing scanned yet).
        saved = (getattr(self, "settings", {}) or {}).get("library")
        if saved and Path(saved).is_dir():
            self.library_path = saved
            self.library_var.set(saved)

    # ------------------------------------------------------------------ scan

    def _choose_folder(self) -> None:
        if getattr(self, "scanning", False) or getattr(self, "applying", False):
            return
        initial = self.library_path or str(Path.home())
        folder = filedialog.askdirectory(parent=self.root, initialdir=initial,
                                         title=tr("选择音乐库文件夹"))
        if not folder:
            return
        self.library_path = folder
        self.library_var.set(folder)
        self._save_settings()

    def _toggle_scan(self) -> None:
        if getattr(self, "scanning", False):
            if self.scan_cancel is not None:
                self.scan_cancel.set()
            return
        self._start_scan()

    def _start_scan(self) -> None:
        if getattr(self, "scanning", False) or getattr(self, "applying", False):
            return
        if not self.library_path or not Path(self.library_path).is_dir():
            self._choose_folder()
            if not self.library_path:
                return
        self.scanning = True
        self.scan_cancel = threading.Event()
        self.albums = []
        self.selected_index = None
        self.album_tree.delete(*self.album_tree.get_children())
        self.progress.configure(value=0, maximum=1)
        self.album_count_var.set("")
        self.scan_button.configure(text=tr("取消扫描"))
        self._set_options_state()
        self._set_apply_state()

        root = Path(self.library_path)
        opts = self.scan_options()
        cancel = self.scan_cancel

        def work():
            groups = group_albums(root)
            self._post(lambda: self._set_scan_total(len(groups)))

            def log(message: str) -> None:
                self._post(lambda m=message: self.status_var.set(m))

            for group in groups:
                if cancel.is_set():
                    break
                result = scan_album(group, opts, log=log, cancel=cancel)
                self._post(lambda r=result: self._on_album_scanned(r))
            return True

        self._run_async(
            work,
            lambda _r: self._finish_scan(),
            lambda exc: self._scan_failed(exc),
        )

    def _set_scan_total(self, total: int) -> None:
        self.progress.configure(maximum=max(total, 1))

    def _on_album_scanned(self, result) -> None:
        self.albums.append(result)
        if self._album_visible(result):
            self._insert_album_row(len(self.albums) - 1)
        done = len(self.albums)
        self.progress.configure(value=done)
        total = int(self.progress["maximum"])
        self.album_count_var.set(tr("{0} / {1} 张专辑", done, total))

    def _finish_scan(self) -> None:
        self.scanning = False
        self.scan_button.configure(text=tr("开始扫描"))
        self._set_options_state()
        self._set_apply_state()

    def _scan_failed(self, exc) -> None:
        self._finish_scan()
        self.status_var.set(tr("扫描出错：{0}", exc))

    # ------------------------------------------------------------- album list

    def _album_status(self, result) -> str:
        return "applied" if getattr(result, "applied", False) else result.status

    def _album_visible(self, result) -> bool:
        try:
            index = filter_names().index(self.filter_var.get())
        except ValueError:
            index = 0
        wanted = FILTER_STATUSES[index]
        if wanted is None:
            return True
        status = result.status if not getattr(result, "applied", False) else "matched"
        return status == wanted

    def _album_row_values(self, result):
        try:
            folder = os.path.relpath(result.group.folder, self.library_path)
        except (ValueError, TypeError):
            folder = str(result.group.folder)
        match = ""
        if result.chosen is not None:
            match = f"{result.chosen.artist} / {result.chosen.name}"
        elif result.status == "error" and result.error:
            match = result.error
        return (status_label(self._album_status(result)), folder,
                len(result.group.files), match)

    def _insert_album_row(self, index: int) -> None:
        self.album_tree.insert("", "end", iid=str(index),
                               values=self._album_row_values(self.albums[index]))

    def _refresh_album_row(self, index: int) -> None:
        iid = str(index)
        if self.album_tree.exists(iid):
            self.album_tree.item(iid, values=self._album_row_values(self.albums[index]))

    def _refilter_albums(self) -> None:
        self.album_tree.delete(*self.album_tree.get_children())
        for index, result in enumerate(getattr(self, "albums", [])):
            if self._album_visible(result):
                self._insert_album_row(index)

    def _on_album_select(self, _event) -> None:
        selection = self.album_tree.selection()
        if not selection:
            return
        index = int(selection[0])
        self.selected_index = index
        result = self.albums[index]
        match = ""
        if result.chosen is not None:
            match = f" · {result.chosen.artist} / {result.chosen.name}"
        self.status_var.set(f"{result.group.folder}{match}")
        self._show_album(result)
