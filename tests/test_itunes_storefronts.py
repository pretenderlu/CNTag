import _isolate  # noqa: F401
import unittest
from unittest.mock import patch

from cntag import catalog_itunes
from cntag.models import ScanOptions


class FakeResponse:
    def __init__(self, results):
        self._results = results

    def raise_for_status(self):
        return None

    def json(self):
        return {"results": self._results}


def patched_get(get_mock, fake_get):
    get_mock.return_value.get.side_effect = fake_get


class ITunesStorefrontTests(unittest.TestCase):
    def test_artist_name_match_rejects_partial_artist_names(self):
        self.assertTrue(catalog_itunes._itunes_artist_name_matches("Gareth.T", "Gareth.T"))
        self.assertFalse(catalog_itunes._itunes_artist_name_matches("Gareth.T", "Gareth"))

    def test_storefronts_add_us_as_secondary_once(self):
        self.assertEqual(catalog_itunes._itunes_storefronts(ScanOptions(country="tw")), ("tw", "us"))
        self.assertEqual(catalog_itunes._itunes_storefronts(ScanOptions(country="us")), ("us", "tw"))

    @patch("cntag.catalog_itunes.http_session")
    def test_album_search_queries_current_country_then_us_and_dedupes(self, session):
        responses = {
            "tw": [
                {"wrapperType": "collection", "collectionId": 10, "collectionName": "台湾结果"},
                {"wrapperType": "collection", "collectionId": 20, "collectionName": "重复结果"},
            ],
            "us": [
                {"wrapperType": "collection", "collectionId": 20, "collectionName": "重复结果 US"},
                {"wrapperType": "collection", "collectionId": 30, "collectionName": "美国结果"},
            ],
        }

        session.return_value.get.side_effect = \
            lambda url, params=None, **kwargs: FakeResponse(responses[params["country"]])
        get = session.return_value.get

        albums = catalog_itunes.itunes_search_albums("周杰伦 七里香", ScanOptions(country="tw", limit=5))

        self.assertEqual([call.kwargs["params"]["country"] for call in get.mock_calls], ["tw", "us"])
        self.assertEqual([a["collectionId"] for a in albums], [10, 20, 30])

    @patch("cntag.catalog_itunes.http_session")
    def test_album_detail_falls_back_to_us_when_primary_has_no_collection(self, session):
        responses = {
            "tw": [],
            "us": [
                {"wrapperType": "collection", "collectionId": 99, "collectionName": "七里香",
                 "artistName": "Jay Chou", "trackCount": 1},
                {"wrapperType": "track", "trackId": 100, "trackName": "我的地盘",
                 "artistName": "Jay Chou", "collectionId": 99,
                 "collectionName": "七里香", "trackNumber": 1, "discNumber": 1},
            ],
        }

        session.return_value.get.side_effect = \
            lambda url, params=None, **kwargs: FakeResponse(responses[params["country"]])
        get = session.return_value.get

        album, tracks = catalog_itunes.itunes_album_detail("99", ScanOptions(country="tw"))

        self.assertEqual([call.kwargs["params"]["country"] for call in get.mock_calls], ["tw", "us"])
        self.assertEqual(album["id"], "99")
        self.assertEqual(album["name"], "七里香")
        self.assertEqual([t["id"] for t in tracks], ["100"])

    @patch("cntag.catalog_itunes.http_session")
    def test_album_detail_continues_when_storefront_has_collection_but_no_tracks(self, session):
        responses = {
            "us": [
                {"wrapperType": "collection", "collectionId": 1883630666,
                 "collectionName": "THE PROTEGE", "artistName": "Gareth.T", "trackCount": 12},
            ],
            "tw": [
                {"wrapperType": "collection", "collectionId": 1883630666,
                 "collectionName": "THE PROTEGE", "artistName": "Gareth.T", "trackCount": 12},
                {"wrapperType": "track", "trackId": 1883630669, "trackName": "国际孤独等级",
                 "artistName": "Gareth.T", "collectionId": 1883630666,
                 "collectionName": "THE PROTEGE", "trackNumber": 1, "discNumber": 1},
            ],
        }

        session.return_value.get.side_effect = \
            lambda url, params=None, **kwargs: FakeResponse(responses[params["country"]])
        get = session.return_value.get

        album, tracks = catalog_itunes.itunes_album_detail("1883630666", ScanOptions(country="us"))

        self.assertEqual([call.kwargs["params"]["country"] for call in get.mock_calls], ["us", "tw"])
        self.assertEqual(album["storefront"], "tw")
        self.assertEqual([t["name"] for t in tracks], ["国际孤独等级"])

    @patch("cntag.catalog_itunes.http_session")
    def test_artist_album_lookup_merges_song_search_collections(self, session):
        def fake_get(url, params=None, **kwargs):
            if params.get("entity") == "musicArtist":
                return FakeResponse([
                    {"wrapperType": "artist", "artistId": 1, "artistName": "Gareth.T"},
                ])
            if params.get("entity") == "album":
                return FakeResponse([
                    {"wrapperType": "artist", "artistId": 1, "artistName": "Gareth.T"},
                    {"wrapperType": "collection", "collectionId": 10,
                     "collectionName": "to be honest", "artistName": "Gareth.T", "trackCount": 9},
                ])
            if params.get("entity") == "song" and params.get("attribute") == "artistTerm":
                return FakeResponse([
                    {"wrapperType": "track", "trackId": 6769327013, "trackName": "玻璃",
                     "artistName": "Gareth.T", "collectionId": 6769327003,
                     "collectionName": "玻璃 - Single", "trackCount": 1},
                ])
            return FakeResponse([])

        session.return_value.get.side_effect = fake_get

        albums = catalog_itunes._itunes_lookup_artist_albums("Gareth.T", ScanOptions(country="us"))

        self.assertEqual([a["collectionId"] for a in albums], [10, 6769327003])
        self.assertEqual(albums[1]["collectionName"], "玻璃 - Single")
        self.assertEqual(albums[1]["trackCount"], 1)

    @patch("cntag.catalog_itunes.http_session")
    def test_artist_album_lookup_merges_generic_song_collections_across_catalog_storefronts(self, session):
        def fake_get(url, params=None, **kwargs):
            if params.get("entity") == "musicArtist":
                return FakeResponse([
                    {"wrapperType": "artist", "artistId": 1, "artistName": "Gareth.T"},
                ])
            if params.get("entity") == "album":
                return FakeResponse([
                    {"wrapperType": "artist", "artistId": 1, "artistName": "Gareth.T"},
                ])
            if params.get("entity") == "song" and params.get("attribute") == "artistTerm":
                return FakeResponse([])
            if params.get("entity") == "song" and params.get("country") == "cn":
                return FakeResponse([
                    {"wrapperType": "track", "trackId": 6769327013, "trackName": "玻璃",
                     "artistName": "Gareth.T", "collectionId": 6769327003,
                     "collectionName": "玻璃 - Single", "trackCount": 1},
                ])
            return FakeResponse([])

        session.return_value.get.side_effect = fake_get
        get = session.return_value.get

        albums = catalog_itunes._itunes_lookup_artist_albums("Gareth.T", ScanOptions(country="us"))

        self.assertEqual([a["collectionId"] for a in albums], [6769327003])
        song_calls = [
            call.kwargs["params"]
            for call in get.mock_calls
            if call.kwargs["params"].get("entity") == "song"
        ]
        self.assertIn("cn", [params["country"] for params in song_calls])

    @patch("cntag.catalog_itunes.http_session")
    def test_artist_song_album_candidates_preserve_apple_relevance_order(self, session):
        first_response = [
            {"wrapperType": "track", "trackId": 1, "trackName": "B Song",
             "artistName": "Gareth.T", "collectionId": 20,
             "collectionName": "B Song - Single", "trackCount": 1},
            {"wrapperType": "track", "trackId": 2, "trackName": "A Song",
             "artistName": "Gareth.T", "collectionId": 10,
             "collectionName": "A Song - Single", "trackCount": 1},
        ]
        seen_song_call = False

        def fake_get(url, params=None, **kwargs):
            nonlocal seen_song_call
            if params.get("entity") == "song" and not seen_song_call:
                seen_song_call = True
                return FakeResponse(first_response)
            return FakeResponse([])

        session.return_value.get.side_effect = fake_get

        candidates = catalog_itunes._itunes_artist_song_album_candidates("Gareth.T", ScanOptions(country="us"))

        self.assertEqual([album["id"] for album, _tracks in candidates], ["20", "10"])


if __name__ == "__main__":
    unittest.main()


class TranslateAlbumArtistTests(unittest.TestCase):
    """Phase A must not let a wrong artist win on name/track-count alone."""

    @patch("cntag.catalog_itunes.itunes_search_albums")
    def test_wrong_artist_single_loses_to_correct_artist(self, search):
        search.return_value = [
            {"collectionId": 999, "collectionName": "幽幽七里香 - Single",
             "artistName": "谢惜萍", "trackCount": 3},
            {"collectionId": 111, "collectionName": "七里香",
             "artistName": "周杰伦", "trackCount": 10},
        ]
        with patch("cntag.catalog_itunes._itunes_lookup_artist_albums",
                   return_value=[]):
            result = catalog_itunes.itunes_translate_album(
                "七里香", "周杰伦", 3, ScanOptions())
        self.assertIsNotNone(result)
        self.assertEqual(result["album_id"], "111")
        self.assertEqual(result["artist_name"], "周杰伦")

    @patch("cntag.catalog_itunes.itunes_search_albums")
    def test_wrong_artist_can_never_early_return(self, search):
        search.return_value = [
            {"collectionId": 999, "collectionName": "幽幽七里香 - Single",
             "artistName": "谢惜萍", "trackCount": 3},
        ]
        with patch("cntag.catalog_itunes._itunes_lookup_artist_albums",
                   return_value=[]):
            result = catalog_itunes.itunes_translate_album(
                "七里香", "周杰伦", 3, ScanOptions())
        self.assertIsNotNone(result)
        self.assertLess(result["score"], 0.85)
