"""Apply & undo: writes tags in place with a retryable undo log."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from ..history import apply_rows, list_history, undo
from ..i18n import tr
from ..tags import NUMBER_FIELDS, TAG_FIELDS, read_tags
from .common import CARD


class ApplyMixin:
    def _build_apply_bar(self, parent) -> None:
        self.undo_button = ttk.Button(parent, text=tr("撤销…"),
                                      command=self._open_history)
        self.undo_button.pack(side="right", padx=(self._px(6), 0))
        self.apply_var = tk.StringVar(value=tr("应用到 {0} 个文件", 0))
        self.apply_button = ttk.Button(parent, textvariable=self.apply_var,
                                       style="Accent.TButton", command=self._apply)
        self.apply_button.pack(side="right")

    # ------------------------------------------------------------- counting

    def _checked_rows(self):
        rows = []
        for result in getattr(self, "albums", []):
            rows.extend(r for r in result.rows if r.get("apply"))
        return rows

    def _update_apply_count(self) -> None:
        if not hasattr(self, "apply_var"):
            return
        self.apply_var.set(tr("应用到 {0} 个文件", len(self._checked_rows())))
        self._set_apply_state()

    def _set_apply_state(self) -> None:
        if not hasattr(self, "apply_button"):
            return
        busy = getattr(self, "scanning", False) or getattr(self, "applying", False)
        self.apply_button.configure(state="disabled" if busy else "normal")
        self.undo_button.configure(state="disabled" if busy else "normal")
        if hasattr(self, "scan_button"):
            self.scan_button.configure(state="disabled" if getattr(self, "applying", False) else "normal")

    # ----------------------------------------------------------------- apply

    def _apply(self) -> None:
        if getattr(self, "scanning", False) or getattr(self, "applying", False):
            return
        rows = self._checked_rows()
        if not rows:
            messagebox.showinfo(tr("应用更改"), tr("没有选中的行。"), parent=self.root)
            return
        album_count = sum(
            1 for result in getattr(self, "albums", [])
            if any(r.get("apply") for r in result.rows))
        message = tr("将写入 {0} 个文件，涉及 {1} 张专辑。{2}\n\n是否继续？",
                     len(rows), album_count,
                     tr("同时会重命名文件。") if self.rename_var.get() else tr("不会重命名文件。"))
        if not messagebox.askyesno(tr("应用更改"), message, parent=self.root):
            return
        self.applying = True
        self._set_options_state()
        self._set_apply_state()
        rename = self.rename_var.get()

        def work():
            return apply_rows(rows, rename=rename)

        self._run_async(work, self._finish_apply,
                        lambda exc: self._apply_failed(exc))

    def _finish_apply(self, report) -> None:
        self.applying = False
        moved = report.moved
        for result in getattr(self, "albums", []):
            touched = False
            for row in result.rows:
                if row.get("file") in moved:
                    row["file"] = moved[row["file"]]
                if row.get("apply"):
                    touched = True
                    self._reread_row(row)
            if touched:
                result.applied = True
            if self.selected_index is not None and result is self.albums[self.selected_index]:
                self._show_album(result)
        self._refilter_albums()
        self._set_options_state()
        self._set_apply_state()
        self._update_apply_count()
        summary = tr("已写入 {0} 个文件，跳过 {1} 个，重命名 {2} 个。",
                     report.ok, report.skipped, report.renamed)
        if report.failures:
            failures = "\n".join(f"· {name}：{err}" for name, err in report.failures[:10])
            summary += "\n\n" + tr("失败：\n{0}", failures)
            messagebox.showwarning(tr("应用结果"), summary, parent=self.root)
        else:
            messagebox.showinfo(tr("应用结果"), summary, parent=self.root)

    def _apply_failed(self, exc) -> None:
        self.applying = False
        self._set_options_state()
        self._set_apply_state()
        messagebox.showerror(tr("应用失败"), str(exc), parent=self.root)

    def _reread_row(self, row: dict) -> None:
        """After a write, refresh the row's old_* values from disk and clear
        new_* + apply so the table shows the new baseline."""
        try:
            tags = read_tags(Path(row.get("file", ""))) or {}
        except Exception:
            tags = {}
        for f in TAG_FIELDS + NUMBER_FIELDS:
            row[f"old_{f}"] = tags.get(f, "")
            row[f"new_{f}"] = ""
        row["apply"] = False

    # ------------------------------------------------------------------ undo

    def _open_history(self) -> None:
        if getattr(self, "scanning", False) or getattr(self, "applying", False):
            return
        window = tk.Toplevel(self.root)
        window.title(tr("撤销记录"))
        window.configure(bg=CARD)
        window.transient(self.root)
        ttk.Label(window, text=tr("撤销记录"), style="Title.Card.TLabel").pack(
            anchor="w", padx=self._px(14), pady=(self._px(14), self._px(8)))
        columns = ("time", "files", "status")
        tree = ttk.Treeview(window, columns=columns, show="headings",
                            selectmode="browse", height=10)
        tree.heading("time", text=tr("时间"))
        tree.heading("files", text=tr("文件数"))
        tree.heading("status", text=tr("状态"))
        tree.column("time", width=self._px(160))
        tree.column("files", width=self._px(70), anchor="center")
        tree.column("status", width=self._px(140))
        tree.pack(fill="both", expand=True, padx=self._px(14), pady=(0, self._px(6)))

        records = {"list": list_history()}

        undo_button = ttk.Button(window, text=tr("撤销所选"))

        def record_status(record) -> str:
            if record.undone:
                return tr("已撤销")
            if record.pending < record.file_count:
                return tr("部分撤销（剩 {0}）", record.pending)
            return tr("可撤销 {0} 个文件", record.pending)

        def update_undo_button(*_args):
            selection = tree.selection()
            enabled = bool(selection) and not records["list"][int(selection[0])].undone
            undo_button.configure(state="normal" if enabled else "disabled")

        def refresh():
            tree.delete(*tree.get_children())
            records["list"] = list_history()
            for i, record in enumerate(records["list"]):
                tree.insert("", "end", iid=str(i),
                            values=(record.created.replace("T", " "),
                                    record.file_count, record_status(record)))
            update_undo_button()

        tree.bind("<<TreeviewSelect>>", update_undo_button)
        refresh()

        def undo_selected():
            selection = tree.selection()
            if not selection:
                return
            record = records["list"][int(selection[0])]
            if record.undone:
                messagebox.showinfo(tr("撤销"), tr("该记录已撤销。"), parent=window)
                return
            if not messagebox.askyesno(
                    tr("撤销"), tr("将 {0} 个文件的标签和文件名还原？",
                                   record.file_count), parent=window):
                return
            self.applying = True
            self._set_options_state()
            self._set_apply_state()

            def work():
                return undo(record.path)

            def done(report):
                self.applying = False
                self._after_undo(report)
                refresh()
                self._set_options_state()
                self._set_apply_state()
                summary = tr("已还原 {0} 个文件，跳过 {1} 个。", report.ok, report.skipped)
                if report.failures:
                    failures = "\n".join(f"· {n}：{e}" for n, e in report.failures[:10])
                    summary += "\n\n" + tr("失败：\n{0}", failures)
                    messagebox.showwarning(tr("撤销结果"), summary, parent=window)
                else:
                    messagebox.showinfo(tr("撤销结果"), summary, parent=window)

            def failed(exc):
                self.applying = False
                refresh()
                self._set_options_state()
                self._set_apply_state()
                messagebox.showerror(tr("撤销失败"), str(exc), parent=window)

            self._run_async(work, done, failed)

        undo_button.configure(command=undo_selected, state="disabled")
        undo_button.pack(pady=(0, self._px(14)))

    def _after_undo(self, report) -> None:
        moved = report.moved
        for result in getattr(self, "albums", []):
            for row in result.rows:
                if row.get("file") in moved:
                    row["file"] = moved[row["file"]]
                    self._reread_row(row)
        self._refilter_albums()
        if self.selected_index is not None and getattr(self, "albums", None):
            self._show_album(self.albums[self.selected_index])
        self._update_apply_count()
