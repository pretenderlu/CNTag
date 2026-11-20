import _isolate  # noqa: F401
import unittest
from unittest.mock import patch

from cntag.models import ScanOptions
from cntag.resolve import search_candidates


class SearchCandidatesTests(unittest.TestCase):
    @patch("cntag.resolve._itunes_lookup_artist_albums", return_value=[])
    @patch("cntag.resolve.itunes_album_detail")
    @patch("cntag.resolve.itunes_search_albums")
    def test_candidates_list_matched_album_even_when_album_and_artist_are_not_chinese(
        self, itunes_search_albums, itunes_album_detail, _itunes_lookup_artist_albums
    ):
        itunes_search_albums.return_value = [
            {
                "wrapperType": "collection",
                "collectionId": 100,
                "collectionName": "THE PROTEGE",
                "artistName": "Gareth.T",
                "trackCount": 2,
                "releaseDate": "2024-01-01T00:00:00Z",
            }
        ]
        itunes_album_detail.return_value = (
            {"id": "100", "name": "THE PROTEGE", "artist_name": "Gareth.T"},
            [
                {"no": 1, "cd": 1, "name": "下一句", "artist_name": "Gareth.T"},
                {"no": 2, "cd": 1, "name": "紧急联络人", "artist_name": "Gareth.T"},
            ],
        )

        candidates = search_candidates("THE PROTEGE", "Gareth.T", 0,
                                       ScanOptions(country="tw"))

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.name, "THE PROTEGE")
        self.assertEqual(candidate.artist, "Gareth.T")
        self.assertEqual([track["name"] for track in candidate.tracks], ["下一句", "紧急联络人"])


if __name__ == "__main__":
    unittest.main()
