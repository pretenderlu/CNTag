import _isolate  # noqa: F401
import tempfile
import unittest
from pathlib import Path

from cntag.library import disc_number_from_name, group_albums, iter_music_files


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


class DiscNameTests(unittest.TestCase):
    def test_disc_patterns(self):
        for name, expect in (
            ("CD1", 1), ("cd 2", 2), ("CD-3", 3), ("Disc 2", 2), ("disk_1", 1),
            ("碟2", 2), ("第2碟", 2), ("第 3 碟", 3), ("2碟", 2),
        ):
            self.assertEqual(disc_number_from_name(name), expect, name)
        for name in ("Album", "CD", "CD 版", "CD Collection", "discography", ""):
            self.assertIsNone(disc_number_from_name(name), name)


class GroupAlbumsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_cd_subfolders_merge_into_parent(self):
        a = touch(self.root / "Album" / "CD1" / "t1.flac")
        b = touch(self.root / "Album" / "CD2" / "t2.flac")
        other = touch(self.root / "Other" / "o.mp3")

        groups = group_albums(self.root)
        self.assertEqual(len(groups), 2)
        merged = next(g for g in groups if g.folder == self.root / "Album")
        self.assertEqual(set(merged.files), {a, b})
        self.assertEqual(merged.disc_of, {a: 1, b: 2})

        single = next(g for g in groups if g.folder == self.root / "Other")
        self.assertEqual(single.files, [other])
        self.assertEqual(single.disc_of, {})

    def test_disc_2_and_chinese_disc_names(self):
        a = touch(self.root / "A" / "Disc 2" / "x.wav")
        b = touch(self.root / "B" / "第2碟" / "y.flac")
        groups = group_albums(self.root)
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].disc_of, {a: 2})
        self.assertEqual(groups[1].disc_of, {b: 2})

    def test_loose_files_become_disc_1_when_no_disc1_folder(self):
        loose = touch(self.root / "Album" / "bonus.flac")
        d2 = touch(self.root / "Album" / "CD2" / "t2.flac")
        groups = group_albums(self.root)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].disc_of, {loose: 1, d2: 2})

    def test_loose_files_stay_separate_when_disc1_exists(self):
        loose = touch(self.root / "Album" / "bonus.flac")
        d1 = touch(self.root / "Album" / "CD1" / "t1.flac")
        d2 = touch(self.root / "Album" / "CD2" / "t2.flac")
        groups = group_albums(self.root)
        self.assertEqual(len(groups), 2)
        merged = next(g for g in groups if set(g.files) == {d1, d2})
        self.assertEqual(merged.disc_of, {d1: 1, d2: 2})
        loose_group = next(g for g in groups if g.files == [loose])
        self.assertEqual(loose_group.folder, self.root / "Album")

    def test_hidden_and_system_dirs_are_skipped(self):
        touch(self.root / ".hidden" / "x.mp3")
        touch(self.root / "$RECYCLE.BIN" / "y.mp3")
        touch(self.root / "@eaDir" / "z.mp3")
        touch(self.root / ".DS_Store_dir" / "w.mp3")
        keep = touch(self.root / "Album" / "ok.flac")
        self.assertEqual(list(iter_music_files(self.root)), [keep])

    def test_groups_sorted_by_folder(self):
        touch(self.root / "b" / "x.mp3")
        touch(self.root / "a" / "y.mp3")
        groups = group_albums(self.root)
        self.assertEqual([g.folder for g in groups], [self.root / "a", self.root / "b"])


if __name__ == "__main__":
    unittest.main()
