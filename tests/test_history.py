import _isolate  # noqa: F401
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from cntag import history
from cntag.tags import read_tags


def make_wav(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00" * 400)
    return path


def row(path, apply=True, **new):
    r = {"file": str(path), "apply": apply,
         "old_title": "", "old_artist": "", "old_album": "",
         "old_albumartist": "", "old_genre": "",
         "old_tracknumber": "", "old_discnumber": ""}
    for f in ("title", "artist", "album", "albumartist", "genre",
              "tracknumber", "discnumber"):
        r[f"new_{f}"] = new.get(f, "")
    return r


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.history_dir = self.dir / "history"

    def test_apply_then_undo_restores_tags_and_filename(self):
        path = make_wav(self.dir / "old.wav")
        history.write_tags(path, {"title": "Old", "artist": "A", "genre": "Pop"})
        report = history.apply_rows(
            [row(path, title="晴天", artist="周杰伦", genre="", tracknumber="4")],
            rename=True, history_dir=self.history_dir)

        self.assertEqual(report.ok, 1)
        self.assertEqual(report.renamed, 1)
        self.assertEqual(report.moved, {str(path): str(self.dir / "04 - 晴天.wav")})
        self.assertFalse(path.exists())
        new_path = self.dir / "04 - 晴天.wav"
        self.assertTrue(new_path.exists())
        self.assertIsNotNone(report.history_path)

        data = json.loads(report.history_path.read_text(encoding="utf-8"))
        self.assertFalse(data["undone"])
        self.assertEqual(len(data["entries"]), 1)
        # Only fields that were actually written are captured.
        self.assertEqual(data["entries"][0]["old_tags"]["title"], "Old")
        self.assertEqual(data["entries"][0]["old_tags"]["artist"], "A")
        self.assertNotIn("genre", data["entries"][0]["old_tags"])
        self.assertIsNone(data["entries"][0]["old_tags"]["tracknumber"])

        undo_report = history.undo(report.history_path)
        self.assertEqual(undo_report.failures, [])
        self.assertTrue(path.exists())
        tags = read_tags(path)
        self.assertEqual(tags["title"], "Old")
        self.assertEqual(tags["artist"], "A")
        self.assertEqual(tags["genre"], "Pop")
        # Fields that were absent before the apply must be deleted, not blanked.
        self.assertEqual(tags["tracknumber"], "")
        self.assertTrue(json.loads(report.history_path.read_text(encoding="utf-8"))["undone"])

    def test_history_written_after_each_file(self):
        """A crash (exception on file 2) still leaves an accurate log for file 1."""
        good = make_wav(self.dir / "good.wav")
        bad = make_wav(self.dir / "bad.wav")
        real_write = history.write_tags

        def flaky(path, new_tags, rename=False):
            if Path(path).name == "bad.wav":
                raise RuntimeError("boom")
            return real_write(path, new_tags, rename=rename)

        with patch("cntag.history.write_tags", side_effect=flaky):
            report = history.apply_rows(
                [row(good, title="A"), row(bad, title="B")],
                rename=False, history_dir=self.history_dir)

        self.assertEqual(report.ok, 1)
        self.assertEqual(len(report.failures), 1)
        self.assertIsNotNone(report.history_path)
        data = json.loads(report.history_path.read_text(encoding="utf-8"))
        self.assertEqual([e["original"] for e in data["entries"]], [str(good)])

    def test_no_history_when_nothing_written(self):
        report = history.apply_rows([row(self.dir / "missing.wav")],
                                    rename=False, history_dir=self.history_dir)
        self.assertIsNone(report.history_path)
        self.assertFalse(self.history_dir.exists())

    def test_undo_missing_current_is_failure(self):
        path = make_wav(self.dir / "x.wav")
        report = history.apply_rows([row(path, title="新")], rename=False,
                                    history_dir=self.history_dir)
        path.unlink()
        undo_report = history.undo(report.history_path)
        self.assertEqual(len(undo_report.failures), 1)
        self.assertEqual(undo_report.ok, 0)

    def test_undo_is_retryable_after_failure(self):
        """A failed entry stays pending; fixing the blocker and retrying
        completes the undo and only then marks the record undone."""
        path = make_wav(self.dir / "r.wav")
        history.write_tags(path, {"title": "Old"})
        report = history.apply_rows([row(path, title="新标题", tracknumber="1")],
                                    rename=True, history_dir=self.history_dir)
        renamed = self.dir / "01 - 新标题.wav"
        blocker = make_wav(path)  # occupy the original name
        first = history.undo(report.history_path)
        self.assertEqual(len(first.failures), 1)
        self.assertFalse(json.loads(report.history_path.read_text(encoding="utf-8"))["undone"])
        blocker.unlink()
        second = history.undo(report.history_path)
        self.assertEqual(second.failures, [])
        self.assertEqual(second.moved, {str(renamed): str(path)})
        self.assertTrue(path.exists())
        self.assertEqual(read_tags(path)["title"], "Old")
        self.assertTrue(json.loads(report.history_path.read_text(encoding="utf-8"))["undone"])
        with self.assertRaises(ValueError):
            history.undo(report.history_path)

    def test_undo_when_original_name_taken_keeps_file_but_restores_tags(self):
        path = make_wav(self.dir / "t.wav")
        history.write_tags(path, {"title": "Old"})
        report = history.apply_rows([row(path, title="新标题", tracknumber="1")],
                                    rename=True, history_dir=self.history_dir)
        renamed = self.dir / "01 - 新标题.wav"
        self.assertTrue(renamed.exists())
        # Recreate a file at the original name — undo must not clobber it.
        make_wav(path)
        undo_report = history.undo(report.history_path)
        self.assertEqual(len(undo_report.failures), 1)
        self.assertTrue(renamed.exists())
        self.assertEqual(read_tags(renamed)["title"], "Old")

    def test_double_undo_raises(self):
        path = make_wav(self.dir / "d.wav")
        report = history.apply_rows([row(path, title="A")], rename=False,
                                    history_dir=self.history_dir)
        history.undo(report.history_path)
        with self.assertRaises(ValueError):
            history.undo(report.history_path)

    def test_list_history_newest_first(self):
        import time
        for i in range(2):
            p = make_wav(self.dir / f"f{i}.wav")
            history.apply_rows([row(p, title=f"T{i}")], rename=False,
                               history_dir=self.history_dir)
            time.sleep(0.01)
        records = history.list_history(self.history_dir)
        self.assertEqual(len(records), 2)
        self.assertEqual([r.file_count for r in records], [1, 1])
        self.assertGreaterEqual(records[0].created, records[1].created)
        self.assertFalse(any(r.undone for r in records))


if __name__ == "__main__":
    unittest.main()
