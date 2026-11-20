"""Candidate album card: candidate list, cover art, manual search."""
from __future__ import annotations

import tkinter as tk
from io import BytesIO
from tkinter import ttk

from ..http import http_session
from ..i18n import tr
from ..scanner import rows_for_candidate, weak_match
from ..resolve import search_candidates
from .common import BORDER, CARD, MUTED

COVER_SIZE = 200

try:
    from PIL import Image, ImageTk
    _HAS_PIL = True
except ImportError:  # pragma: no cover
    _HAS_PIL = False


class CandidatesMixin:
    def _build_candidates_card(self, parent) -> None:
        ttk.Label(parent, text=tr("候选专辑"), style="Title.Card.TLabel").pack(
            anchor="w", pady=(0, self._px(8)))

        search_row = ttk.Frame(parent)
        search_row.pack(fill="x", pady=(0, self._px(8)))
        self.search_album_var = tk.StringVar()
        self.search_artist_var = tk.StringVar()
        self.search_album_entry = ttk.Entry(search_row, textvariable=self.search_album_var)
        self.search_album_entry.pack(side="left", fill="x", expand=True,
                                     padx=(0, self._px(6)))
        self.search_artist_entry = ttk.Entry(search_row, textvariable=self.search_artist_var)
        self.search_artist_entry.pack(side="left", fill="x", expand=True,
                                      padx=(0, self._px(6)))
        self.search_button = ttk.Button(search_row, text=tr("搜索"),
                                        command=self._manual_search)
        self.search_button.pack(side="left")

        body = ttk.Frame(parent)
        body.pack(fill="both", expand=True)

        # Pack the right-hand side panel first so it always keeps its
        # requested width; the tree takes whatever remains.
        side = ttk.Frame(body, width=self._px(COVER_SIZE))
        side.pack(side="right", fill="y", padx=(self._px(12), 0))
        side.pack_propagate(False)
        self.cover_label = tk.Label(side, bg=CARD, highlightthickness=1,
                                    highlightbackground=BORDER)
        self.cover_label.pack(side="top", fill="x")
        self.cover_image = None
        # Pack the button before the listbox: a bottom-anchored widget is
        # never squeezed below its requested height, so the label can't be
        # clipped when the card runs out of vertical space.
        self.use_button = ttk.Button(side, text=tr("使用此专辑"),
                                     style="Accent.TButton",
                                     command=self._use_candidate)
        self.use_button.pack(side="bottom", fill="x")
        self.use_button.configure(state="disabled")
        self.track_listbox = tk.Listbox(side, font=(self.ui_font, 9), height=6,
                                        highlightthickness=0, bd=0, bg=CARD, fg=MUTED,
                                        activestyle="none")
        self.track_listbox.pack(side="top", fill="both", expand=True,
                                pady=(self._px(6), self._px(6)))

        columns = ("album", "artist", "tracks", "date", "source")
        self.candidate_tree = ttk.Treeview(body, columns=columns, show="headings",
                                           selectmode="browse")
        self.candidate_tree.heading("album", text=tr("专辑"))
        self.candidate_tree.heading("artist", text=tr("歌手"))
        self.candidate_tree.heading("tracks", text=tr("曲目数"))
        self.candidate_tree.heading("date", text=tr("发行日期"))
        self.candidate_tree.heading("source", text=tr("来源"))
        self.candidate_tree.column("album", width=self._px(160))
        self.candidate_tree.column("artist", width=self._px(110))
        self.candidate_tree.column("tracks", width=self._px(60), stretch=False, anchor="center")
        self.candidate_tree.column("date", width=self._px(90), stretch=False)
        self.candidate_tree.column("source", width=self._px(110), stretch=False)
        cand_scroll = ttk.Scrollbar(body, orient="vertical",
                                    command=self.candidate_tree.yview)
        self.candidate_tree.configure(yscrollcommand=cand_scroll.set)
        cand_scroll.pack(side="right", fill="y")
        self.candidate_tree.pack(side="left", fill="both", expand=True)
        self.candidate_tree.bind("<<TreeviewSelect>>", self._on_candidate_select)

        self._cover_cache: dict[str, object] = {}
        self._cover_loading: set[str] = set()
        self._current_result = None
        self._current_candidates: list = []
        self._candidate_request = 0

    # -------------------------------------------------------------- display

    def _show_album(self, result) -> None:
        """Populate both right-hand cards for a selected album."""
        self._current_result = result
        self._candidate_request += 1
        self._show_rows(result)
        self._fill_candidates(result.candidates, result)
        if result.rows:
            first = result.rows[0]
            self.search_album_var.set(first.get("old_album") or result.group.folder.name)
            self.search_artist_var.set(first.get("old_artist") or "")
        else:
            self.search_album_var.set(result.group.folder.name)
            self.search_artist_var.set("")

    def _fill_candidates(self, candidates, result) -> None:
        self._current_candidates = list(candidates or [])
        self.candidate_tree.delete(*self.candidate_tree.get_children())
        self.track_listbox.delete(0, "end")
        local_count = len(result.group.files) if result is not None else 0
        for index, cand in enumerate(self._current_candidates):
            mark = "✓ " if result is not None and cand is result.chosen else ""
            source = cand.source + (f" · {cand.via}" if cand.via else "")
            self.candidate_tree.insert("", "end", iid=str(index), values=(
                mark + cand.name, cand.artist,
                f"{cand.track_count} / {local_count}",
                (cand.release_date or "")[:10], source))
        if self._current_candidates:
            chosen_index = 0
            if result is not None and result.chosen in self._current_candidates:
                chosen_index = self._current_candidates.index(result.chosen)
            iid = str(chosen_index)
            self.candidate_tree.selection_set(iid)
            self.candidate_tree.see(iid)
            self.use_button.configure(state="normal")
            self._show_candidate_detail(self._current_candidates[chosen_index])
        else:
            self.use_button.configure(state="disabled")
            self._show_candidate_detail(None)

    def _on_candidate_select(self, _event) -> None:
        selection = self.candidate_tree.selection()
        self.use_button.configure(state="normal" if selection else "disabled")
        if not selection:
            return
        self._show_candidate_detail(self._current_candidates[int(selection[0])])

    def _show_candidate_detail(self, cand) -> None:
        self.track_listbox.delete(0, "end")
        if cand is None:
            self.cover_label.configure(image="", text=tr("无封面"))
            self.cover_image = None
            return
        for track in cand.tracks:
            cd = track.get("cd") or 1
            no = track.get("no") or ""
            prefix = f"{cd}-{no}" if (cand.tracks and max(t.get("cd") or 1 for t in cand.tracks) > 1) else f"{no}"
            self.track_listbox.insert("end", f"{prefix} {track.get('name', '')}")
        self.cover_label.configure(image="", text=tr("无封面"))
        self.cover_image = None
        if cand.artwork_url:
            self._load_cover(cand.artwork_url)

    # -------------------------------------------------------------- artwork

    def _load_cover(self, url: str) -> None:
        if url in self._cover_cache:
            self._set_cover(self._cover_cache[url])
            return
        if url in self._cover_loading or not _HAS_PIL:
            return
        self._cover_loading.add(url)

        def work():
            response = http_session().get(url, timeout=15)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content)).convert("RGB")
            image = image.resize((COVER_SIZE, COVER_SIZE), Image.Resampling.LANCZOS)
            return url, image

        def done(result):
            self._cover_loading.discard(result[0])
            photo = ImageTk.PhotoImage(result[1])
            self._cover_cache[result[0]] = photo
            # Only show if the selected candidate still points at this URL.
            selection = self.candidate_tree.selection()
            if selection:
                cand = self._current_candidates[int(selection[0])]
                if cand.artwork_url == result[0]:
                    self._set_cover(photo)

        def failed(_exc):
            self._cover_loading.discard(url)

        self._run_async(work, done, failed)

    def _set_cover(self, photo) -> None:
        self.cover_image = photo  # keep a reference
        self.cover_label.configure(image=photo, text="")

    # --------------------------------------------------------- use / search

    def _use_candidate(self) -> None:
        if self._current_result is None:
            return
        selection = self.candidate_tree.selection()
        if not selection:
            return
        cand = self._current_candidates[int(selection[0])]
        result = self._current_result
        request = self._candidate_request = self._candidate_request + 1
        opts = self.scan_options()

        def work():
            return rows_for_candidate(result.group, cand, opts)

        def done(rows):
            if request != self._candidate_request or self._current_result is not result:
                return  # stale
            result.rows = rows
            result.chosen = cand
            result.status = ("needs_confirm"
                             if weak_match(rows, len(result.group.files))
                             else "matched")
            for row in rows:
                if result.status == "needs_confirm":
                    row["apply"] = False
            self._fill_candidates(result.candidates, result)
            self._show_rows(result)
            if self.selected_index is not None:
                self._refresh_album_row(self.selected_index)
            self._update_apply_count()

        self._run_async(work, done,
                        lambda exc: self.status_var.set(tr("载入候选专辑失败：{0}", exc)))

    def _manual_search(self) -> None:
        if self._current_result is None:
            return
        album = self.search_album_var.get().strip()
        artist = self.search_artist_var.get().strip()
        if not album and not artist:
            return
        result = self._current_result
        local_count = len(result.group.files)
        request = self._candidate_request = self._candidate_request + 1
        opts = self.scan_options()

        def work():
            return search_candidates(album, artist, local_count, opts)

        def done(candidates):
            if request != self._candidate_request or self._current_result is not result:
                return  # stale: another album/search superseded this one
            result.candidates = list(candidates)
            result.chosen = None
            if result.status == "matched":
                result.status = "needs_confirm"
            self._fill_candidates(result.candidates, result)
            if self.selected_index is not None:
                self._refresh_album_row(self.selected_index)

        self._run_async(work, done,
                        lambda exc: self.status_var.set(tr("搜索失败：{0}", exc)))
