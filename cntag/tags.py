"""Read/write audio tags via mutagen (WAVE handled through ID3 frames)."""
from __future__ import annotations

import re
from pathlib import Path

from mutagen import File as MutagenFile

from .textutil import parse_int

MUSIC_EXTS = {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".oga", ".opus", ".wav"}
# Library-junk dirs that must never be scanned (recycle bins, NAS metadata,
# downloader temp dirs). Anything dot-named is skipped on top of these.
SKIP_DIR_NAMES = {"$RECYCLE.BIN", "System Volume Information", "@eaDir",
                  "#recycle", ".deleted", ".Trash-1000", "lost+found"}
TAG_FIELDS = ["title", "artist", "album", "albumartist", "genre"]
NUMBER_FIELDS = ["tracknumber", "discnumber"]

# Easy-mutagen field → ID3 frame id, used for WAVE files (MutagenFile with
# easy=True has no easy keys for WAVE, so frames are handled directly).
_WAV_FRAMES = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "albumartist": "TPE2",
    "genre": "TCON",
    "tracknumber": "TRCK",
    "discnumber": "TPOS",
}


def _is_wav(path: Path) -> bool:
    return path.suffix.lower() == ".wav"


def read_tags(path: Path) -> dict | None:
    """All TAG_FIELDS + NUMBER_FIELDS as strings; None if unreadable."""
    if _is_wav(path):
        return _read_wav(path)
    try:
        audio = MutagenFile(str(path), easy=True)
    except Exception:
        return None
    if audio is None:
        return None
    out = {}
    for field_ in TAG_FIELDS + NUMBER_FIELDS:
        v = audio.get(field_)
        if v:
            out[field_] = v[0] if isinstance(v, list) else str(v)
        else:
            out[field_] = ""
    return out


def _read_wav(path: Path) -> dict | None:
    from mutagen.wave import WAVE

    try:
        audio = WAVE(str(path))
    except Exception:
        return None
    out = {field_: "" for field_ in TAG_FIELDS + NUMBER_FIELDS}
    tags = audio.tags
    if tags is None:
        return out
    for field_, frame_id in _WAV_FRAMES.items():
        frame = tags.get(frame_id)
        if frame is not None:
            text = getattr(frame, "text", None)
            if text:
                out[field_] = str(text[0])
    return out


_FILENAME_ILLEGAL_RE = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_filename(s: str) -> str:
    """Strip characters illegal on Windows/POSIX, trim, cap length."""
    s = _FILENAME_ILLEGAL_RE.sub("", s or "")
    s = s.strip().rstrip(".").strip()
    return s[:180]


def build_track_filename(track_no, title: str, ext: str) -> str:
    """`05 - 晴天.mp3`. If no track number, drop the prefix."""
    safe = sanitize_filename(title)
    if not safe:
        return ""
    n = parse_int(track_no)
    if n is not None:
        return f"{n:02d} - {safe}{ext}"
    return f"{safe}{ext}"


def _write_wav(path: Path, new_tags: dict) -> None:
    from mutagen.id3 import TALB, TCON, TIT2, TPE1, TPE2, TPOS, TRCK
    from mutagen.wave import WAVE

    audio = WAVE(str(path))
    if audio.tags is None:
        audio.add_tags()
    frame_types = {
        "TIT2": TIT2, "TPE1": TPE1, "TALB": TALB, "TPE2": TPE2,
        "TCON": TCON, "TRCK": TRCK, "TPOS": TPOS,
    }
    for field_, value in new_tags.items():
        frame_id = _WAV_FRAMES.get(field_)
        if not frame_id:
            continue
        if value is None:
            audio.tags.delall(frame_id)
            continue
        audio.tags.setall(frame_id, [frame_types[frame_id](encoding=3, text=str(value))])
    audio.save()


def delete_fields(path: Path, fields) -> None:
    """Remove the given tag fields (used by undo for fields that were absent)."""
    write_tags(path, {f: None for f in fields}, rename=False)


def write_tags(path: Path, new_tags: dict, rename: bool = False) -> Path:
    """Write tags to the file. A value of None deletes the field. When
    `rename=True`, also rename the file to `<NN> - <new_title>.<ext>` (the
    new tracknumber wins over the existing one). Returns the final path."""
    path = Path(path)
    if _is_wav(path):
        _write_wav(path, new_tags)
        track_no_existing = _read_wav(path).get("tracknumber") if path.exists() else ""
    else:
        audio = MutagenFile(str(path), easy=True)
        if audio is None:
            raise RuntimeError(f"unsupported format: {path.suffix}")
        if audio.tags is None:
            audio.add_tags()

        track_no_existing = ""
        v = audio.get("tracknumber")
        if v:
            track_no_existing = v[0] if isinstance(v, list) else str(v)

        for field_, value in new_tags.items():
            if value is None:
                try:
                    del audio[field_]
                except (KeyError, ValueError):
                    pass
                continue
            if not value:
                continue
            try:
                audio[field_] = value
            except (KeyError, ValueError):
                pass
        audio.save()

    if not rename:
        return path

    new_title = (new_tags.get("title") or "").strip()
    if not new_title:
        return path
    track_no = new_tags.get("tracknumber") or track_no_existing
    new_name = build_track_filename(track_no, new_title, path.suffix)
    if not new_name:
        return path
    target = path.parent / new_name
    if target == path:
        return path
    if target.exists() and target.resolve() != path.resolve():
        # Collision with a different file — append a counter
        stem = target.stem
        i = 2
        while True:
            target = path.parent / f"{stem} ({i}){path.suffix}"
            if not target.exists():
                break
            i += 1
    path.rename(target)
    return target
