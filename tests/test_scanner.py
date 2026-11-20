import _isolate  # noqa: F401
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from cntag.matching import build_rows, match_file_to_track
from cntag.models import AlbumGroup, Candidate, ScanOptions
from cntag.scanner import scan_album, scan_library


def track(name, no, cd=1, **kwargs):
    base = {
        "source": "itunes", "id": f"id-{cd}-{no}", "name": name,
        "artist_name": "周杰伦", "album_id": "100", "album_name": "七里香",
        "album_artist_name": "周杰伦", "no": no, "cd": cd, "aliases": [],
    }
    base.update(kwargs)
    return base


def candidate(tracks, **kwargs):
    return Candidate(source="itunes", album_id="100", name="七里香",
                     artist="周杰伦", track_count=len(tracks), tracks=tracks,
                     **kwargs)


class ScanAlbumStatusTests(unittest.TestCase):
    def setUp(self):
        self.group = AlbumGroup(folder=Path("album"), files=[Path("a.wav"), Path("b.wav")])
        self.opts = ScanOptions(sources=("itunes",), delay=0)

    @patch("cntag.scanner.read_tags", return_value={"title": "", "artist": "J", "album": "X"})
    @patch("cntag.scanner.album_detail")
    @patch("cntag.scanner.resolve_album_two_stage")
    def test_resolved_is_matched_with_chosen(self, resolve, detail, _rt):
        resolve.return_value = ("itunes", "100", 0.9, "周杰伦")
        detail.return_value = (
            {"source": "itunes", "id": "100", "name": "七里香", "artist_name": "周杰伦"},
            [track("A", 1), track("B", 2)],
        )
        result = scan_album(self.group, self.opts)
        self.assertEqual(result.status, "matched")
        self.assertIsNotNone(result.chosen)
        self.assertIn(result.chosen, result.candidates)
        self.assertEqual(len(result.rows), 2)

    @patch("cntag.scanner.read_tags", return_value={"title": "", "artist": "J", "album": "X"})
    @patch("cntag.scanner.itunes_artist_catalog_candidates")
    @patch("cntag.scanner.album_detail")
    @patch("cntag.scanner.resolve_album_two_stage")
    def test_weak_resolution_demotes_to_needs_confirm(self, resolve, detail, catalog, _rt):
        """Resolved album whose rows mostly don't match is needs_confirm, not matched."""
        resolve.return_value = ("itunes", "100", 0.9, "谢惜萍")
        detail.return_value = (
            {"source": "itunes", "id": "100", "name": "幽幽七里香 - Single",
             "artist_name": "谢惜萍"},
            [track("X", 1), track("Y", 2), track("Z", 3)],
        )
        catalog.return_value = [
            Candidate(source="itunes", album_id="200", name="七里香",
                      artist="周杰伦", track_count=10)
        ]
        logs = []
        result = scan_album(self.group, self.opts, log=logs.append)
        self.assertEqual(result.status, "needs_confirm")
        self.assertIsNotNone(result.chosen)          # weak choice stays visible
        self.assertTrue(all(not r["apply"] for r in result.rows))
        ids = [c.album_id for c in result.candidates]
        self.assertEqual(ids[0], "100")              # chosen first
        self.assertIn("200", ids)
        self.assertEqual(len(ids), len(set(ids)))    # deduped
        self.assertTrue(any("待确认" in m for m in logs))

    @patch("cntag.scanner.read_tags", return_value={"title": "x", "artist": "Gareth.T"})
    @patch("cntag.resolve._itunes_artist_song_album_candidates")
    @patch("cntag.scanner.resolve_album_two_stage", return_value=None)
    def test_artist_catalog_is_needs_confirm_without_rows(self, _resolve, song_groups, _rt):
        song_groups.return_value = [
            ({"source": "itunes", "id": "9", "name": "玻璃 - Single",
              "artist_name": "Gareth.T", "track_count": 1},
             [track("玻璃", 1, album_id="9", album_name="玻璃 - Single",
                    artist_name="Gareth.T")])
        ]
        result = scan_album(self.group, self.opts)
        self.assertEqual(result.status, "needs_confirm")
        self.assertEqual(result.rows, [])
        self.assertIsNone(result.chosen)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].via, "artist-catalog")

    @patch("cntag.scanner.read_tags", return_value={"title": "晴天", "artist": "周杰伦"})
    @patch("cntag.scanner.scan_folder_per_track")
    @patch("cntag.scanner.itunes_artist_catalog_candidates", return_value=[])
    @patch("cntag.scanner.resolve_album_two_stage", return_value=None)
    def test_per_track_match_is_matched_without_chosen(self, _r, _c, per_track, _rt):
        per_track.return_value = [{"external_id": "t1", "file": "a.wav"}]
        result = scan_album(self.group, self.opts)
        self.assertEqual(result.status, "matched")
        self.assertIsNone(result.chosen)
        self.assertEqual(result.rows, per_track.return_value)

    @patch("cntag.scanner.read_tags", return_value={"title": "zzz"})
    @patch("cntag.scanner.scan_folder_per_track")
    @patch("cntag.scanner.itunes_artist_catalog_candidates", return_value=[])
    @patch("cntag.scanner.resolve_album_two_stage", return_value=None)
    def test_nothing_is_unmatched(self, _r, _c, per_track, _rt):
        per_track.return_value = [{"external_id": "", "apply": False, "file": "a.wav"}]
        result = scan_album(self.group, self.opts)
        self.assertEqual(result.status, "unmatched")
        self.assertTrue(all(not r["apply"] for r in result.rows))

    @patch("cntag.scanner.read_tags", side_effect=RuntimeError("io"))
    def test_exception_is_error(self, _rt):
        result = scan_album(self.group, self.opts)
        self.assertEqual(result.status, "error")
        self.assertIn("io", result.error)


class ScanLibraryTests(unittest.TestCase):
    @patch("cntag.scanner.scan_album")
    @patch("cntag.scanner.group_albums")
    def test_cancel_stops_before_next_album(self, group_albums, scan):
        groups = [AlbumGroup(folder=Path(f"a{i}"), files=[]) for i in range(3)]
        group_albums.return_value = groups
        cancel = threading.Event()

        def on_album(result):
            cancel.set()

        from cntag.models import AlbumResult
        scan.side_effect = lambda g, opts, **kw: AlbumResult(group=g, status="unmatched")

        results = scan_library(Path("root"), ScanOptions(delay=0), on_album, cancel=cancel)
        self.assertEqual(len(results), 1)
        self.assertEqual(scan.call_count, 1)


class MultiDiscMatchingTests(unittest.TestCase):
    def test_disc_of_used_when_tags_lack_discnumber(self):
        f1, f2 = Path("a.flac"), Path("b.flac")
        group = AlbumGroup(folder=Path("album"), files=[f1, f2],
                           disc_of={f1: 1, f2: 2})
        tracks = [track("One", 1, cd=1), track("Two", 1, cd=2)]
        tagged = [(f1, {"title": "", "tracknumber": "1"}),
                  (f2, {"title": "", "tracknumber": "1"})]
        rows = build_rows(group, tagged, candidate(tracks), 0.9, ScanOptions())
        self.assertEqual([r["new_title"] for r in rows], ["One", "Two"])
        # Multi-disc album: cd differs from the absent old discnumber → filled.
        self.assertEqual(rows[0]["new_discnumber"], "1")
        self.assertEqual(rows[1]["new_discnumber"], "2")

    def test_discnumber_not_written_for_single_disc_album(self):
        f1 = Path("a.flac")
        group = AlbumGroup(folder=Path("album"), files=[f1])
        tracks = [track("One", 1, cd=1)]
        tagged = [(f1, {"title": "", "tracknumber": "1"})]
        rows = build_rows(group, tagged, candidate(tracks), 0.9, ScanOptions())
        self.assertEqual(rows[0]["new_discnumber"], "")

    def test_fractional_tracknumber_not_rewritten(self):
        """Old '4/10' vs new track 4 parses equal → no change proposed."""
        f1 = Path("a.flac")
        group = AlbumGroup(folder=Path("album"), files=[f1])
        tracks = [track("One", 4, cd=1)]
        tagged = [(f1, {"title": "", "tracknumber": "4/10"})]
        rows = build_rows(group, tagged, candidate(tracks), 0.9, ScanOptions())
        self.assertEqual(rows[0]["new_tracknumber"], "")

    def test_different_tracknumber_is_written(self):
        f1 = Path("a.flac")
        group = AlbumGroup(folder=Path("album"), files=[f1])
        tracks = [track("One", 5, cd=1)]
        tagged = [(f1, {"title": "", "tracknumber": "4"})]
        rows = build_rows(group, tagged, candidate(tracks), 0.9, ScanOptions())
        self.assertEqual(rows[0]["new_tracknumber"], "5")

    def test_position_fallback_orders_by_disc_then_filename(self):
        a, b = Path("z01.flac"), Path("a01.flac")
        group = AlbumGroup(folder=Path("album"), files=[b, a],
                           disc_of={a: 1, b: 2})
        tracks = [track("Disc1Track", 9, cd=1), track("Disc2Track", 1, cd=2)]
        tagged = [(a, {"title": ""}), (b, {"title": ""})]
        rows = build_rows(group, tagged, candidate(tracks), 0.9, ScanOptions())
        by_file = {r["file"]: r for r in rows}
        # files sorted by (disc, name): a(disc1)→Disc1Track, b(disc2)→Disc2Track
        self.assertEqual(by_file[str(a)]["new_title"], "Disc1Track")
        self.assertEqual(by_file[str(b)]["new_title"], "Disc2Track")
        self.assertTrue(all(r["match_method"] == "position" for r in rows))


if __name__ == "__main__":
    unittest.main()


class TitlePinyinMatchingTests(unittest.TestCase):
    def test_tracknumber_and_title_match_gives_highest_confidence(self):
        matched, method = match_file_to_track(
            {"title": "Qi Li Xiang", "tracknumber": "2"},
            [track("我的地盘", 1), track("七里香", 2)])
        self.assertEqual(matched["name"], "七里香")
        self.assertEqual(method, "tracknumber+title")

    def test_wrong_tracknumber_rescued_by_pinyin_title(self):
        matched, method = match_file_to_track(
            {"title": "Qi Li Xiang", "tracknumber": "5"},
            [track("七里香", 2), track("将军", 5)])
        self.assertEqual(matched["name"], "七里香")
        self.assertEqual(method, "title-pinyin")

    def test_english_title_stays_tracknumber(self):
        matched, method = match_file_to_track(
            {"title": "Grandfather's Tea", "tracknumber": "4"},
            [track("七里香", 2), track("外婆", 4)])
        self.assertEqual(matched["name"], "外婆")
        self.assertEqual(method, "tracknumber")

    def test_pinyin_title_without_tracknumber(self):
        matched, method = match_file_to_track(
            {"title": "Ge Qian", "tracknumber": ""},
            [track("七里香", 2), track("搁浅", 6)])
        self.assertEqual(matched["name"], "搁浅")
        self.assertEqual(method, "title-pinyin")


class ArtistMismatchDemotionTests(unittest.TestCase):
    """A resolved album by a different artist is demoted to needs_confirm."""

    def setUp(self):
        self.files = [Path("a.wav"), Path("b.wav")]
        self.group = AlbumGroup(folder=Path("album"), files=self.files)
        self.opts = ScanOptions(sources=("itunes",), delay=0)

    @patch("cntag.scanner.read_tags", return_value={"title": "", "artist": "J", "album": "X"})
    @patch("cntag.scanner.itunes_artist_catalog_candidates", return_value=[])
    @patch("cntag.scanner.album_detail")
    @patch("cntag.scanner.resolve_album_two_stage")
    def test_wrong_artist_demotes_even_when_rows_match(self, resolve, detail, _cat, _rt):
        resolve.return_value = ("itunes", "999", 0.9, "周杰伦")
        detail.return_value = (
            {"source": "itunes", "id": "999", "name": "幽幽七里香 - Single",
             "artist_name": "谢惜萍"},
            [track("X", 1), track("Y", 2)],
        )
        logs = []
        result = scan_album(self.group, self.opts, log=logs.append)
        self.assertEqual(result.status, "needs_confirm")
        self.assertTrue(all(not r["apply"] for r in result.rows))
        self.assertTrue(any("不符" in m for m in logs))
