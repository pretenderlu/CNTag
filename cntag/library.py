"""Library walking and album grouping."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from .models import AlbumGroup
from .tags import MUSIC_EXTS, SKIP_DIR_NAMES

_DISC_DIR_RES = (
    re.compile(r"^(?:cd|disc|disk|碟)\s*[-_.]?\s*(\d+)$", re.IGNORECASE),
    re.compile(r"^第?\s*(\d+)\s*碟$"),
)


def disc_number_from_name(name: str) -> int | None:
    """Disc number from a folder name like 'CD2', 'Disc 1', '第2碟', or None."""
    for pattern in _DISC_DIR_RES:
        m = pattern.match(name.strip())
        if m:
            return int(m.group(1))
    return None


def iter_music_files(root: Path) -> Iterator[Path]:
    """Walk `root` collecting audio files, skipping hidden/system dirs.

    Manual walk instead of rglob so skipped dirs (.deleted recycle bins,
    root-owned NAS metadata...) are never *descended into* — rglob would
    still enter them and raise PermissionError mid-scan."""
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = list(d.iterdir())
        except (PermissionError, OSError):
            continue
        for e in entries:
            if e.name in SKIP_DIR_NAMES or e.name.startswith("."):
                continue
            if e.is_dir():
                stack.append(e)
            elif e.is_file() and e.suffix.lower() in MUSIC_EXTS:
                yield e


def group_albums(root: Path) -> list[AlbumGroup]:
    """One AlbumGroup per folder, except disc-named subfolders (CD1, Disc 2,
    第2碟…) which merge into a single group under their parent.

    The parent's own loose audio files join the merged group as disc 1 —
    unless a disc folder numbered 1 exists, in which case the loose files
    stay a separate group under the parent."""
    root = Path(root)
    by_folder: dict[Path, list[Path]] = {}
    for f in iter_music_files(root):
        by_folder.setdefault(f.parent, []).append(f)

    merged: dict[Path, AlbumGroup] = {}
    standalone: dict[Path, list[Path]] = {}

    for folder, files in sorted(by_folder.items()):
        disc = disc_number_from_name(folder.name)
        if disc is not None and folder.parent != folder:
            group = merged.setdefault(folder.parent, AlbumGroup(folder=folder.parent, files=[]))
            group.files.extend(files)
            for f in files:
                group.disc_of[f] = disc
        else:
            standalone[folder] = files

    for group in merged.values():
        loose = standalone.pop(group.folder, [])
        if loose and not any(d == 1 for d in group.disc_of.values()):
            group.files.extend(loose)
            for f in loose:
                group.disc_of[f] = 1
        elif loose:
            standalone[group.folder] = loose
        group.files.sort()

    groups = list(merged.values())
    groups.extend(AlbumGroup(folder=folder, files=sorted(files))
                  for folder, files in standalone.items())
    groups.sort(key=lambda g: str(g.folder))
    return groups
