"""Offline self-test of a build: ``CNTag --self-test [report file]``.

Bundled data (icons, zhconv's dictionary, pypinyin's tables, the CA bundle) is loaded lazily, so a build that
leaves a file out still starts and only fails in the middle of a scan. build_app.py runs this against the
built application; every check works offline, in a temporary folder.
"""
from __future__ import annotations

import io
import sqlite3
import ssl
import sys
import tempfile
import wave
from pathlib import Path


def _expect(condition, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _check_assets() -> None:
    from .ui.common import _resource_path

    names = ["assets/icon.png", "LICENSE", "THIRD_PARTY_NOTICES.md", "licenses/GPL-2.0.txt"]
    if sys.platform == "win32":
        names.append("assets/icon.ico")
    missing = [name for name in names if not _resource_path(name).is_file()]
    _expect(not missing, f"missing files: {', '.join(missing)}")


def _check_zhconv() -> None:
    from .textutil import to_zh_cn

    _expect(to_zh_cn("周杰倫", True) == "周杰伦", "Traditional to Simplified conversion gave a wrong result")


def _check_pypinyin() -> None:
    from .textutil import name_match_score, to_pinyin

    _expect(to_pinyin("七里香") == "qilixiang", "pinyin conversion gave a wrong result")
    _expect(name_match_score("Qi Li Xiang", "七里香") == 1.0, "pinyin name matching gave a wrong result")


def _check_tls() -> None:
    import certifi
    import requests  # noqa: F401

    _expect(Path(certifi.where()).is_file(), "CA bundle is missing")
    ssl.create_default_context(cafile=certifi.where())


def _check_images() -> None:
    from PIL import Image, ImageTk  # noqa: F401

    from .ui.common import _resource_path

    icon = Image.open(_resource_path("assets/icon.png")).convert("RGB").resize((64, 64))
    buffer = io.BytesIO()
    icon.save(buffer, format="JPEG")
    _expect(Image.open(io.BytesIO(buffer.getvalue())).size == (64, 64), "JPEG round trip failed")


def _check_sqlite() -> None:
    with tempfile.TemporaryDirectory(prefix="cntag-selftest-") as folder:
        connection = sqlite3.connect(str(Path(folder) / "cache.db"), isolation_level=None)
        try:
            connection.execute("PRAGMA journal_mode=WAL;")
            connection.execute("CREATE TABLE cache (k TEXT PRIMARY KEY, v TEXT)")
            connection.execute("INSERT INTO cache VALUES (?, ?)", ("周杰伦", "七里香"))
            _expect(connection.execute("SELECT v FROM cache").fetchone() == ("七里香",), "sqlite round trip failed")
        finally:
            connection.close()


def _check_pipeline() -> None:
    from .history import apply_rows, undo
    from .library import group_albums
    from .matching import build_rows
    from .models import Candidate, ScanOptions
    from .tags import read_tags, write_tags

    with tempfile.TemporaryDirectory(prefix="cntag-selftest-") as folder:
        album = Path(folder) / "album"
        album.mkdir()
        source = album / "02 - Qi Li Xiang.wav"
        with wave.open(str(source), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(b"\0\0" * 800)
        write_tags(source, {"title": "Qi Li Xiang", "artist": "Jay Chou",
                            "album": "Common Jasmin Orange", "tracknumber": "2"})

        groups = group_albums(Path(folder))
        _expect([[path.name for path in group.files] for group in groups] == [[source.name]], "album grouping failed")
        group = groups[0]
        tagged = [(path, read_tags(path) or {}) for path in group.files]
        _expect(tagged[0][1].get("title") == "Qi Li Xiang", "tags could not be read back")

        candidate = Candidate(
            source="itunes", album_id="1", name="七里香", artist="周杰伦", track_count=1,
            tracks=[{"source": "itunes", "id": "t2", "name": "七里香", "artist_name": "周杰伦",
                     "no": 2, "cd": 1, "aliases": []}],
        )
        rows = build_rows(group, tagged, candidate, 0.95, ScanOptions())
        _expect(len(rows) == 1 and rows[0]["new_title"] == "七里香" and rows[0]["apply"], "file was not matched to its track")

        report = apply_rows(rows, rename=True, history_dir=Path(folder) / "history")
        renamed = album / "02 - 七里香.wav"
        _expect(report.ok == 1 and not report.failures and renamed.is_file(), "tags were not applied")
        _expect((read_tags(renamed) or {}).get("artist") == "周杰伦", "applied tags could not be read back")

        undone = undo(report.history_path)
        _expect(not undone.failures and source.is_file() and not renamed.exists(), "undo did not restore the file name")
        _expect((read_tags(source) or {}).get("title") == "Qi Li Xiang", "undo did not restore the tags")


CHECKS = (
    ("assets", _check_assets),
    ("zhconv", _check_zhconv),
    ("pypinyin", _check_pypinyin),
    ("tls", _check_tls),
    ("images", _check_images),
    ("sqlite", _check_sqlite),
    ("pipeline", _check_pipeline),
)


def run() -> list[tuple[str, str]]:
    """Runs every check; returns (name, error) pairs, with an empty error for a passing check."""
    results = []
    for name, check in CHECKS:
        try:
            check()
        except Exception as exc:
            results.append((name, f"{type(exc).__name__}: {exc}"))
        else:
            results.append((name, ""))
    return results


def main(argv: list[str]) -> int:
    results = run()
    text = "".join(f"FAIL {name}: {error}\n" if error else f"OK   {name}\n" for name, error in results)
    target = next((arg for arg in argv[argv.index("--self-test") + 1:] if not arg.startswith("-")), None)
    if target:
        Path(target).write_text(text, encoding="utf-8")
    print(text, end="")
    return 1 if any(error for _, error in results) else 0
