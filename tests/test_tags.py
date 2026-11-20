import _isolate  # noqa: F401
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from cntag.tags import (
    TAG_FIELDS,
    NUMBER_FIELDS,
    delete_fields,
    read_tags,
    sanitize_filename,
    build_track_filename,
    write_tags,
)


def make_wav(path: Path, seconds: float = 0.05, rate: int = 8000) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00" * int(rate * seconds) * 2)
    return path


def make_flac(path: Path) -> Path:
    """Minimal FLAC: signature + one STREAMINFO metadata block.

    STREAMINFO (34 bytes): min/max blocksize (4096), min/max framesize (0),
    then 8 bytes packing sample-rate:channels:bps:total-samples, then a
    16-byte (zeroed) MD5. mutagen only needs this to open the file; the
    file has no audio frames, which tag writing doesn't require."""
    streaminfo = struct.pack(">HH", 4096, 4096) + b"\x00" * 6
    packed = (44100 << 44) | (1 << 41) | (15 << 36)
    streaminfo += packed.to_bytes(8, "big") + b"\x00" * 16
    header = b"\x80" + len(streaminfo).to_bytes(3, "big")  # last-block | type 0
    path.write_bytes(b"fLaC" + header + streaminfo)
    return path


class ReadWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_flac_fixture_is_parseable(self):
        from mutagen.flac import FLAC
        path = make_flac(self.dir / "a.flac")
        self.assertIsNotNone(FLAC(str(path)))

    def test_wav_read_write_read(self):
        path = make_wav(self.dir / "raw.wav")
        self.assertEqual(read_tags(path), {f: "" for f in TAG_FIELDS + NUMBER_FIELDS})

        write_tags(path, {"title": "晴天", "artist": "周杰伦",
                          "album": "叶惠美", "tracknumber": "4"})
        tags = read_tags(path)
        self.assertEqual(tags["title"], "晴天")
        self.assertEqual(tags["artist"], "周杰伦")
        self.assertEqual(tags["album"], "叶惠美")
        self.assertEqual(tags["tracknumber"], "4")
        self.assertEqual(tags["discnumber"], "")

    def test_wav_delete_field(self):
        path = make_wav(self.dir / "del.wav")
        write_tags(path, {"title": "X", "artist": "Y"})
        delete_fields(path, ["artist"])
        tags = read_tags(path)
        self.assertEqual(tags["title"], "X")
        self.assertEqual(tags["artist"], "")

    def test_flac_read_write_rename(self):
        path = make_flac(self.dir / "04 - Old Title.flac")
        write_tags(path, {"title": "七里香", "tracknumber": "4"})
        tags = read_tags(path)
        self.assertEqual(tags["title"], "七里香")

        new_path = write_tags(path, {"title": "晴天", "tracknumber": "5"}, rename=True)
        self.assertEqual(new_path.name, "05 - 晴天.flac")
        self.assertTrue(new_path.exists())
        self.assertFalse(path.exists())

    def test_write_tags_none_deletes_field(self):
        path = make_wav(self.dir / "none.wav")
        write_tags(path, {"genre": "Pop", "title": "A"})
        write_tags(path, {"genre": None})
        self.assertEqual(read_tags(path)["genre"], "")
        self.assertEqual(read_tags(path)["title"], "A")


class FilenameTests(unittest.TestCase):
    def test_sanitize_strips_illegal_chars(self):
        self.assertEqual(sanitize_filename('a/b:c*d?"e<>f|g'), "abcdefg")
        self.assertEqual(sanitize_filename(" name. "), "name")

    def test_build_track_filename(self):
        self.assertEqual(build_track_filename("5", "晴天", ".mp3"), "05 - 晴天.mp3")
        self.assertEqual(build_track_filename(None, "晴天", ".mp3"), "晴天.mp3")
        self.assertEqual(build_track_filename("4/10", "七里香", ".flac"), "04 - 七里香.flac")


if __name__ == "__main__":
    unittest.main()
