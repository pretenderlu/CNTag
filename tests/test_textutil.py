import _isolate  # noqa: F401
import unittest

from cntag.textutil import artists_match


class ArtistsMatchTests(unittest.TestCase):
    def test_traditional_vs_simplified_is_true(self):
        self.assertIs(artists_match("周杰倫", "周杰伦"), True)

    def test_multi_artist_part_match_is_true(self):
        self.assertIs(artists_match("周杰伦/费玉清", "周杰伦"), True)

    def test_different_cjk_artists_is_false(self):
        self.assertIs(artists_match("谢惜萍", "周杰伦"), False)

    def test_one_cjk_one_latin_is_none(self):
        self.assertIs(artists_match("Jay Chou", "周杰伦"), None)

    def test_case_insensitive_latin_is_true(self):
        self.assertIs(artists_match("Jay Chou", "JAY CHOU"), True)

    def test_empty_is_none(self):
        self.assertIsNone(artists_match("", "周杰伦"))
        self.assertIsNone(artists_match("周杰伦", ""))


if __name__ == "__main__":
    unittest.main()
