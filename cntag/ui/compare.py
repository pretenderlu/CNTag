"""Compare card: per-file old → new tag table with apply checkboxes."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import simpledialog, ttk

from ..i18n import tr
from ..tags import NUMBER_FIELDS, TAG_FIELDS
from ..textutil import has_cjk
from .common import CARD

DISPLAY_FIELDS = ("title", "artist", "album")


def _diff(old: str, new: str) -> str:
    if new and new != old:
        return f"{old} → {new}" if old else new
    return old


class CompareMixin:
    def _build_compare_card(self, parent) -> None:
        ttk.Label(parent, text=tr("标签对比"), style="Title.Card.TLabel").pack(
            anchor="w", pady=(0, self._px(8)))

        buttons = ttk.Frame(parent, style="Card.TFrame")
        buttons.pack(fill="x", pady=(0, self._px(8)))
        ttk.Button(buttons, text=tr("全选"), command=lambda: self._set_all(True)).pack(
            side="left", padx=(0, self._px(6)))
        ttk.Button(buttons, text=tr("全不选"), command=lambda: self._set_all(False)).pack(
            side="left", padx=(0, self._px(6)))
        ttk.Button(buttons, text=tr("仅高置信"), command=self._select_high_confidence).pack(
            side="left")

        self.confirm_hint = ttk.Label(parent, style="Muted.Card.TLabel",
                                      text=tr("自动匹配不可靠，请在上方确认专辑后再应用"))

        tree_frame = ttk.Frame(parent, style="Card.TFrame")
        tree_frame.pack(fill="both", expand=True)
        columns = ("apply", "file", "title", "artist", "album",
                   "track", "confidence", "method")
        self.compare_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.compare_tree.heading("apply", text=tr("应用"))
        self.compare_tree.heading("file", text=tr("文件"))
        self.compare_tree.heading("title", text=tr("标题"))
        self.compare_tree.heading("artist", text=tr("歌手"))
        self.compare_tree.heading("album", text=tr("专辑"))
        self.compare_tree.heading("track", text=tr("曲号"))
        self.compare_tree.heading("confidence", text=tr("置信度"))
        self.compare_tree.heading("method", text=tr("方法"))
        self.compare_tree.column("apply", width=self._px(44), stretch=False, anchor="center")
        self.compare_tree.column("file", width=self._px(150))
        self.compare_tree.column("title", width=self._px(170))
        self.compare_tree.column("artist", width=self._px(120))
        self.compare_tree.column("album", width=self._px(140))
        self.compare_tree.column("track", width=self._px(60), stretch=False, anchor="center")
        self.compare_tree.column("confidence", width=self._px(60), stretch=False, anchor="center")
        self.compare_tree.column("method", width=self._px(90), stretch=False)
        scroll = ttk.Scrollbar(tree_frame, orient="vertical",
                               command=self.compare_tree.yview)
        self.compare_tree.configure(yscrollcommand=scroll.set)
        self.compare_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.compare_tree.bind("<Button-1>", self._on_compare_click)
        self.compare_tree.bind("<space>", lambda _e: self._toggle_selection())
        self.compare_tree.bind("<Return>", lambda _e: self._edit_selection())
        self.compare_tree.bind("<Double-Button-1>", self._on_compare_double)
        self._compare_result = None

    # -------------------------------------------------------------- display

    def _show_rows(self, result) -> None:
        self._compare_result = result
        if result.status == "needs_confirm":
            self.confirm_hint.pack(anchor="w", pady=(0, self._px(6)),
                                   before=self.compare_tree.master)
        else:
            self.confirm_hint.pack_forget()
        self.compare_tree.delete(*self.compare_tree.get_children())
        for index, row in enumerate(result.rows):
            self.compare_tree.insert("", "end", iid=str(index),
                                     values=self._row_values(row))
        self._update_apply_count()

    def _row_values(self, row: dict):
        return (
            "☑" if row.get("apply") else "☐",
            Path(row.get("file", "")).name,
            _diff(row.get("old_title", ""), row.get("new_title", "")),
            _diff(row.get("old_artist", ""), row.get("new_artist", "")),
            _diff(row.get("old_album", ""), row.get("new_album", "")),
            _diff(row.get("old_tracknumber", ""), row.get("new_tracknumber", "")),
            f"{row.get('confidence', 0.0):.2f}",
            row.get("match_method", ""),
        )

    def _refresh_row_item(self, index: int) -> None:
        row = self._compare_result.rows[index]
        self.compare_tree.item(str(index), values=self._row_values(row))

    # --------------------------------------------------------------- toggle

    def _row_index_from_event(self, event) -> int | None:
        if self._compare_result is None:
            return None
        iid = self.compare_tree.identify_row(event.y)
        if not iid:
            return None
        return int(iid)

    def _on_compare_click(self, event):
        if self.compare_tree.identify_column(event.x) != "#1":
            return None
        index = self._row_index_from_event(event)
        if index is None:
            return "break"
        self._toggle_row(index)
        return "break"

    def _on_compare_double(self, event):
        index = self._row_index_from_event(event)
        if index is not None:
            self._edit_row(index)
            return "break"
        return None

    def _toggle_row(self, index: int) -> None:
        row = self._compare_result.rows[index]
        row["apply"] = not row.get("apply")
        self._refresh_row_item(index)
        self._update_apply_count()

    def _toggle_selection(self):
        if self._compare_result is None:
            return
        for iid in self.compare_tree.selection():
            self._toggle_row(int(iid))

    def _set_all(self, value: bool) -> None:
        if self._compare_result is None:
            return
        for index, row in enumerate(self._compare_result.rows):
            if bool(row.get("apply")) != value:
                row["apply"] = value
                self._refresh_row_item(index)
        self._update_apply_count()

    def _select_high_confidence(self) -> None:
        if self._compare_result is None:
            return
        threshold = self._threshold()
        for index, row in enumerate(self._compare_result.rows):
            value = (row.get("confidence", 0.0) >= threshold
                     and (has_cjk(row.get("new_title", ""))
                          or has_cjk(row.get("new_artist", ""))))
            if bool(row.get("apply")) != bool(value):
                row["apply"] = bool(value)
                self._refresh_row_item(index)
        self._update_apply_count()

    # ------------------------------------------------------------------ edit

    def _edit_selection(self):
        if self._compare_result is None:
            return
        selection = self.compare_tree.selection()
        if selection:
            self._edit_row(int(selection[0]))

    def _edit_row(self, index: int) -> None:
        row = self._compare_result.rows[index]
        dialog = RowEditDialog(self.root, row, self.ui_font, self._px)
        if dialog.result is None:
            return
        for field_name, value in dialog.result.items():
            row[f"new_{field_name}"] = value
        row["apply"] = True
        self._refresh_row_item(index)
        self._update_apply_count()


EDIT_FIELDS = TAG_FIELDS + NUMBER_FIELDS


class RowEditDialog(simpledialog.Dialog):
    """Modal editor for a row's new_* fields."""

    def __init__(self, parent, row: dict, font, px):
        self.row = row
        self.font = font
        self.px = px
        self.entries: dict[str, tk.Entry] = {}
        self.result: dict | None = None
        super().__init__(parent, tr("编辑标签"))

    def body(self, master):
        master.configure(bg=CARD)
        labels = {
            "title": tr("标题"), "artist": tr("歌手"), "album": tr("专辑"),
            "albumartist": tr("专辑歌手"), "genre": tr("流派"),
            "tracknumber": tr("曲号"), "discnumber": tr("碟号"),
        }
        for i, field_name in enumerate(EDIT_FIELDS):
            tk.Label(master, text=labels[field_name], bg=CARD,
                     font=(self.font, 10)).grid(row=i, column=0, sticky="w",
                                                padx=self.px(10), pady=self.px(4))
            entry = tk.Entry(master, width=42, font=(self.font, 10))
            value = self.row.get(f"new_{field_name}") or self.row.get(f"old_{field_name}") or ""
            entry.insert(0, value)
            entry.grid(row=i, column=1, sticky="we", padx=self.px(10), pady=self.px(4))
            self.entries[field_name] = entry
        return next(iter(self.entries.values()))

    def apply(self):
        self.result = {f: e.get().strip() for f, e in self.entries.items()}
