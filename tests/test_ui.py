"""UI tests for CNTagApp — skipped when Tk is unavailable."""
import _isolate  # noqa: F401
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import tkinter  # noqa: F401
    _TK_OK = True
except ImportError:
    _TK_OK = False

if _TK_OK:
    try:
        import tkinter as tk
        _root_probe = tk.Tk()
        _root_probe.destroy()
    except tk.TclError:
        _TK_OK = False

from cntag.app import CNTagApp
from cntag.models import AlbumGroup, AlbumResult, Candidate


def make_group(files=2):
    return AlbumGroup(folder=Path("lib/album1"), files=[Path(f"f{i}.wav") for i in range(files)])


def make_row(file="lib/album1/a.wav", apply=True, conf=0.9, new_title="晴天"):
    return {
        "file": file, "apply": apply, "confidence": conf, "source": "itunes",
        "external_id": "1", "match_method": "exact",
        "old_title": "Qing Tian", "new_title": new_title,
        "old_artist": "Jay", "new_artist": "周杰伦",
        "old_album": "Alb", "new_album": "叶惠美",
        "old_tracknumber": "", "new_tracknumber": "",
        "old_discnumber": "", "new_discnumber": "",
        "old_albumartist": "", "new_albumartist": "",
        "old_genre": "", "new_genre": "",
    }


def make_result(status="matched", files=2, rows=None, candidates=None, chosen=None):
    group = make_group(files)
    return AlbumResult(group=group, status=status, rows=rows or [],
                       candidates=candidates or [], chosen=chosen)


class Report:
    def __init__(self, moved=None):
        self.ok = 1
        self.skipped = 0
        self.renamed = 0
        self.moved = moved or {}
        self.failures = []
        self.history_path = None


@unittest.skipUnless(_TK_OK, "Tk unavailable")
class UITests(unittest.TestCase):
    def setUp(self):
        try:
            with patch.object(CNTagApp, "_check_for_updates", lambda s: None):
                self.app = CNTagApp()
        except tk.TclError as exc:
            self.skipTest(f"Tk unavailable: {exc}")
        self.app.root.withdraw()
        self.app.root.update()

    def tearDown(self):
        try:
            self.app.root.destroy()
        except tk.TclError:
            pass

    def pump(self, rounds=10):
        for _ in range(rounds):
            self.app._drain_ui_queue()
            self.app.root.update()
            time.sleep(0.01)

    # ------------------------------------------------------------- scanning

    def test_scan_populates_album_tree_and_progress(self):
        result = make_result("matched")
        with tempfile.TemporaryDirectory() as tmp, \
             patch("cntag.ui.library.group_albums", return_value=[make_group()]), \
             patch("cntag.ui.library.scan_album", return_value=result):
            self.app.library_path = tmp
            self.app._start_scan()
            deadline = time.time() + 5
            while self.app.scanning and time.time() < deadline:
                self.pump(3)
            self.pump(5)
        self.assertFalse(self.app.scanning)
        items = self.app.album_tree.get_children()
        self.assertEqual(len(items), 1)
        values = self.app.album_tree.item(items[0], "values")
        self.assertIn("已匹配", values[0])
        self.assertEqual(values[2], "2")
        self.assertEqual(int(self.app.progress["value"]), 1)
        self.assertIn("1 / 1", self.app.album_count_var.get())

    def test_filter_combobox(self):
        self.app.albums = [
            make_result("matched"), make_result("needs_confirm"),
            make_result("unmatched"),
        ]
        self.app.library_path = "lib"
        self.app._refilter_albums()
        self.assertEqual(len(self.app.album_tree.get_children()), 3)
        from cntag.ui.library import filter_names
        self.app.filter_var.set(filter_names()[1])
        self.app._refilter_albums()
        self.assertEqual(len(self.app.album_tree.get_children()), 1)
        self.app.filter_var.set(filter_names()[2])
        self.app._refilter_albums()
        self.assertEqual(len(self.app.album_tree.get_children()), 1)

    def test_select_album_fills_candidates_and_compare(self):
        cand = Candidate(source="itunes", album_id="1", name="七里香",
                         artist="周杰伦", track_count=10)
        result = make_result("needs_confirm", rows=[make_row()],
                             candidates=[cand], chosen=cand)
        self.app.albums = [result]
        self.app.library_path = "lib"
        self.app._refilter_albums()
        self.app.album_tree.selection_set("0")
        self.app._on_album_select(None)
        self.pump(3)
        self.assertEqual(len(self.app.candidate_tree.get_children()), 1)
        values = self.app.candidate_tree.item("0", "values")
        self.assertIn("七里香", values[0])
        self.assertEqual(values[2], "10 / 2")
        self.assertEqual(len(self.app.compare_tree.get_children()), 1)

    # -------------------------------------------------------------- compare

    def test_toggle_and_bulk_buttons_update_apply_count(self):
        result = make_result(rows=[make_row(), make_row(file="b.wav")])
        self.app.albums = [result]
        self.app._show_rows(result)
        self.assertIn("2", self.app.apply_var.get())
        self.app._toggle_row(0)
        self.assertIn("1", self.app.apply_var.get())
        self.app._set_all(False)
        self.assertIn("0", self.app.apply_var.get())
        self.app._set_all(True)
        self.assertIn("2", self.app.apply_var.get())
        result.rows[0]["confidence"] = 0.1
        result.rows[0]["apply"] = False
        result.rows[1]["apply"] = False
        self.app._select_high_confidence()
        self.assertFalse(result.rows[0]["apply"])
        self.assertTrue(result.rows[1]["apply"])

    def test_edit_not_triggered_on_empty(self):
        self.app._show_rows(make_result(rows=[]))
        self.app._edit_selection()  # no crash

    # ----------------------------------------------------------- candidates

    def test_use_candidate_replaces_rows(self):
        cand = Candidate(source="itunes", album_id="1", name="七里香",
                         artist="周杰伦", track_count=3,
                         tracks=[{"no": 1, "cd": 1, "name": "A"}])
        result = make_result("needs_confirm", files=3, rows=[make_row(apply=False)],
                             candidates=[cand])
        new_rows = [make_row(new_title="东风破")]  # 1 matched of 3 → weak
        with patch("cntag.ui.candidates.rows_for_candidate", return_value=new_rows) as rfc:
            self.app.selected_index = 0
            self.app._current_result = result
            self.app._fill_candidates([cand], result)
            self.app.candidate_tree.selection_set("0")
            self.app._use_candidate()
            deadline = time.time() + 5
            while rfc.call_count == 0 and time.time() < deadline:
                time.sleep(0.01)
            self.pump(10)
        self.assertIs(result.rows, new_rows)
        self.assertIs(result.chosen, cand)
        self.assertEqual(result.status, "needs_confirm")  # 1/2 matched < ceil(2/2)

    def test_stale_search_result_ignored(self):
        result = make_result()
        result2 = make_result()
        self.app._current_result = result
        released = []
        with patch("cntag.ui.candidates.search_candidates",
                   side_effect=lambda *a: released.append(True) or [Candidate(
                       source="itunes", album_id="9", name="X", artist="Y",
                       track_count=1)]):
            self.app.search_album_var.set("a")
            self.app._manual_search()          # request 1 for result
            self.app._current_result = result2  # user switches album meanwhile
            self.app.search_album_var.set("b")
            self.app._manual_search()          # request 2 for result2
            deadline = time.time() + 5
            while len(released) < 2 and time.time() < deadline:
                time.sleep(0.01)
            self.pump(10)
        # Only the latest result object got the candidates (request ordering
        # is racy, so check the invariant: result was never updated).
        self.assertEqual(result.candidates, [])
        self.assertEqual(len(result2.candidates), 1)

    # ---------------------------------------------------------------- apply

    def test_apply_updates_paths_and_marks_applied(self):
        import tempfile as tf
        row = make_row(file="old.wav")
        result = make_result(rows=[row])
        self.app.albums = [result]
        self.app.selected_index = 0
        report = Report(moved={"old.wav": "new.wav"})
        with tf.TemporaryDirectory() as tmp:
            new_file = Path(tmp) / "new.wav"
            row["file"] = "old.wav"
            report.moved = {"old.wav": str(new_file)}
            with patch("cntag.ui.apply.apply_rows", return_value=report), \
                 patch("cntag.ui.apply.messagebox.askyesno", return_value=True), \
                 patch("cntag.ui.apply.messagebox.showinfo"), \
                 patch("cntag.ui.apply.read_tags", return_value={"title": "晴天"}):
                self.app._apply()
                deadline = time.time() + 5
                while self.app.applying and time.time() < deadline:
                    self.pump(3)
                self.pump(10)
        self.assertEqual(row["file"], str(new_file))
        self.assertEqual(row["old_title"], "晴天")
        self.assertEqual(row["new_title"], "")
        self.assertFalse(row["apply"])
        self.assertTrue(result.applied)

    def test_undo_window_lists_records(self):
        from cntag.history import HistoryRecord
        records = [HistoryRecord(path=Path("h/1.json"), created="2025-01-01T00:00:00",
                                 file_count=3, undone=False, pending=3),
                   HistoryRecord(path=Path("h/2.json"), created="2025-01-02T00:00:00",
                                 file_count=1, undone=True, pending=0)]
        with patch("cntag.ui.apply.list_history", return_value=records):
            self.app._open_history()
            windows = [w for w in self.app.root.winfo_children()
                       if isinstance(w, tk.Toplevel)]
            self.assertEqual(len(windows), 1)
            trees = [w for w in windows[0].winfo_children()
                     if isinstance(w, tk.ttk.Treeview)]
            self.assertEqual(len(trees), 1)
            items = trees[0].get_children()
            self.assertEqual(len(items), 2)
            windows[0].destroy()

    # -------------------------------------------------------------- options

    def test_settings_roundtrip(self):
        self.app.src_netease_var.set(True)
        self.app.rename_var.set(True)
        self.app.threshold_var.set("0.75")
        self.app.library_path = "lib"
        snapshot = self.app._persistable_options()
        self.assertTrue(snapshot["rename"])
        self.assertIn("netease", snapshot["sources"])
        self.assertEqual(snapshot["threshold"], 0.75)
        self.assertEqual(snapshot["library"], "lib")
        # simulate reload
        self.app.settings = snapshot
        self.app._init_option_vars()
        self.assertTrue(self.app.src_netease_var.get())
        self.assertEqual(self.app._threshold(), 0.75)

    def test_at_least_one_source(self):
        self.app.src_itunes_var.set(False)
        self.app._sources_changed()
        self.assertTrue(self.app.src_itunes_var.get())


if __name__ == "__main__":
    unittest.main()
