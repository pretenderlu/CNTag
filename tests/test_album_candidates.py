import _isolate  # noqa: F401
import unittest
from pathlib import Path
from unittest.mock import patch

from cntag.models import AlbumGroup, ScanOptions
from cntag.scanner import scan_album


def track(**kwargs):
    base = {
        "source": "itunes", "id": "", "name": "", "artist_name": "",
        "album_id": "", "album_name": "", "album_artist_name": "",
        "no": None, "cd": 1, "aliases": [],
    }
    base.update(kwargs)
    return base


class AlbumCandidateTests(unittest.TestCase):
    @patch("cntag.scanner.read_tags")
    @patch("cntag.scanner.album_detail")
    @patch("cntag.scanner.resolve_album_two_stage")
    def test_confirmable_album_candidate_does_not_require_chinese_album_or_artist(
        self, resolve_album_two_stage, album_detail, read_tags
    ):
        files = [Path("01.m4a"), Path("02.m4a")]
        group = AlbumGroup(folder=Path("album-folder"), files=files)
        resolve_album_two_stage.return_value = ("itunes", "100", 0.92, "Gareth.T")
        album_detail.return_value = (
            {
                "source": "itunes", "id": "100", "name": "THE PROTEGE",
                "artist_name": "Gareth.T", "track_count": 2,
            },
            [
                track(id="t1", name="下一句", artist_name="Gareth.T",
                      album_id="100", album_name="THE PROTEGE",
                      album_artist_name="Gareth.T", no=1),
                track(id="t2", name="紧急联络人", artist_name="Gareth.T",
                      album_id="100", album_name="THE PROTEGE",
                      album_artist_name="Gareth.T", no=2),
            ],
        )
        read_tags.side_effect = [
            {"title": "Next", "artist": "Gareth.T", "album": "THE PROTEGE", "tracknumber": "1"},
            {"title": "Emergency Contact", "artist": "Gareth.T", "album": "THE PROTEGE", "tracknumber": "2"},
        ]

        result = scan_album(group, ScanOptions(sources=("itunes",)))

        self.assertEqual(result.status, "matched")
        self.assertEqual([row["new_title"] for row in result.rows], ["下一句", "紧急联络人"])
        chosen = result.chosen
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.source, "itunes")
        self.assertEqual(chosen.name, "THE PROTEGE")
        self.assertEqual(chosen.artist, "Gareth.T")
        self.assertEqual([t["name"] for t in chosen.tracks], ["下一句", "紧急联络人"])

    @patch("cntag.scanner.read_tags")
    @patch("cntag.resolve.album_detail")
    @patch("cntag.resolve._itunes_lookup_artist_albums")
    @patch("cntag.resolve._itunes_artist_song_album_candidates")
    @patch("cntag.scanner.resolve_album_two_stage")
    def test_lists_itunes_artist_lookup_candidates_when_song_groups_are_empty(
        self, resolve_album_two_stage, song_album_candidates, lookup_artist_albums, album_detail, read_tags
    ):
        files = [Path("glass.m4a")]
        group = AlbumGroup(folder=Path("glass"), files=files)
        resolve_album_two_stage.return_value = None
        song_album_candidates.return_value = []
        lookup_artist_albums.return_value = [
            {
                "collectionId": 6769327003,
                "collectionName": "玻璃 - Single",
                "artistName": "Gareth.T",
                "trackCount": 1,
            }
        ]
        album_detail.return_value = (
            {
                "source": "itunes", "id": "6769327003", "name": "玻璃 - Single",
                "artist_name": "Gareth.T", "track_count": 1,
            },
            [
                track(id="6769327013", name="玻璃", artist_name="Gareth.T",
                      album_id="6769327003", album_name="玻璃 - Single",
                      album_artist_name="Gareth.T", no=1)
            ],
        )
        read_tags.return_value = {"title": "glass", "artist": "Gareth.T", "album": "glass"}

        result = scan_album(group, ScanOptions(sources=("itunes",)))

        self.assertEqual(result.status, "needs_confirm")
        self.assertEqual(result.rows, [])
        self.assertEqual(lookup_artist_albums.call_args.args[0], "Gareth.T")
        candidate = result.candidates[0]
        self.assertEqual(candidate.source, "itunes")
        self.assertEqual(candidate.via, "artist-catalog")
        self.assertEqual(candidate.album_id, "6769327003")
        self.assertEqual(candidate.name, "玻璃 - Single")
        self.assertEqual([t["name"] for t in candidate.tracks], ["玻璃"])

    @patch("cntag.scanner.read_tags")
    @patch("cntag.resolve.album_detail")
    @patch("cntag.resolve._itunes_lookup_artist_albums")
    @patch("cntag.resolve._itunes_artist_song_album_candidates")
    @patch("cntag.scanner.resolve_album_two_stage")
    def test_artist_catalog_candidates_use_song_groups_before_album_detail(
        self, resolve_album_two_stage, song_album_candidates, lookup_artist_albums, album_detail, read_tags
    ):
        files = [Path("glass.m4a")]
        group = AlbumGroup(folder=Path("glass"), files=files)
        resolve_album_two_stage.return_value = None
        song_album_candidates.return_value = [
            (
                {
                    "source": "itunes", "id": "6769327003", "name": "玻璃 - Single",
                    "artist_name": "Gareth.T", "track_count": 1,
                },
                [
                    track(id="6769327013", name="玻璃", artist_name="Gareth.T",
                          album_id="6769327003", album_name="玻璃 - Single",
                          album_artist_name="Gareth.T", no=1)
                ],
            )
        ]
        lookup_artist_albums.return_value = []
        read_tags.return_value = {"title": "glass", "artist": "Gareth.T", "album": "glass"}

        result = scan_album(group, ScanOptions(sources=("itunes",)))

        self.assertEqual(result.status, "needs_confirm")
        album_detail.assert_not_called()
        candidate = result.candidates[0]
        self.assertEqual(candidate.album_id, "6769327003")
        self.assertEqual([t["name"] for t in candidate.tracks], ["玻璃"])

    @patch("cntag.scanner.read_tags")
    @patch("cntag.resolve._itunes_artist_song_album_candidates")
    @patch("cntag.scanner.resolve_album_two_stage")
    def test_artist_catalog_candidates_are_ranked_and_limited_by_local_names(
        self, resolve_album_two_stage, song_album_candidates, read_tags
    ):
        files = [Path("CUTIE.m4a")]
        group = AlbumGroup(folder=Path("cutie"), files=files)
        resolve_album_two_stage.return_value = None
        read_tags.return_value = {"title": "cutie", "artist": "Gareth.T", "album": "cutie"}

        candidates = []
        for i in range(10):
            album_name = f"Other Song {i} - Single"
            track_name = f"Other Song {i}"
            album_id = str(1000 + i)
            if i == 9:
                album_name = "CUTIE - Single"
                track_name = "CUTIE"
                album_id = "1692182544"
            candidates.append((
                {
                    "source": "itunes", "id": album_id, "name": album_name,
                    "artist_name": "Gareth.T", "track_count": 1,
                },
                [
                    track(id=f"t-{album_id}", name=track_name, artist_name="Gareth.T",
                          album_id=album_id, album_name=album_name,
                          album_artist_name="Gareth.T", no=1)
                ],
            ))
        song_album_candidates.return_value = candidates

        result = scan_album(group, ScanOptions(sources=("itunes",)))

        self.assertEqual(result.status, "needs_confirm")
        self.assertEqual(len(result.candidates), 8)
        self.assertEqual(result.candidates[0].album_id, "1692182544")
        self.assertEqual(result.candidates[0].name, "CUTIE - Single")


if __name__ == "__main__":
    unittest.main()
