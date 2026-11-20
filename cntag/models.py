"""Data shapes shared across the scanning engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

KNOWN_SOURCES = ("itunes", "netease")
DEFAULT_SOURCES = ("itunes",)


def normalize_sources(sources) -> tuple[str, ...]:
    if sources is None:
        return DEFAULT_SOURCES
    if isinstance(sources, str):
        raw_sources = [s.strip() for s in sources.split(",")]
    else:
        raw_sources = [str(s).strip() for s in sources]

    normalized: list[str] = []
    for source in raw_sources:
        key = source.lower()
        if not key:
            continue
        if key not in KNOWN_SOURCES:
            raise ValueError(f"unknown source: {source}")
        if key not in normalized:
            normalized.append(key)
    if not normalized:
        raise ValueError("select at least one search source")
    return tuple(normalized)


@dataclass
class ScanOptions:
    country: str = "tw"
    simplified: bool = True
    sources: tuple[str, ...] = ("itunes",)
    use_encyclopedia: bool = True
    threshold: float = 0.6
    vote_n: int = 4
    limit: int = 10
    delay: float = 0.3


@dataclass
class Candidate:
    source: str
    album_id: str
    name: str
    artist: str
    track_count: int
    tracks: list[dict] = field(default_factory=list)   # normalized track dicts
    via: str = ""
    score: float = 0.0
    artwork_url: str = ""
    release_date: str = ""
    storefront: str = ""


@dataclass
class AlbumGroup:
    folder: Path                 # album root; parent of CD1/CD2 when merged
    files: list[Path]
    disc_of: dict[Path, int] = field(default_factory=dict)  # disc inferred from subfolder name (merged groups only)


@dataclass
class AlbumResult:
    group: AlbumGroup
    status: str                  # "matched" | "needs_confirm" | "unmatched" | "error"
    rows: list[dict] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    chosen: Candidate | None = None
    error: str = ""
