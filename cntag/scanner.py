"""Album-level scan orchestration: resolve → match → fallbacks → status."""
from __future__ import annotations

import math
import threading
import time
from pathlib import Path
from typing import Callable

from .i18n import tr
from .library import group_albums
from .matching import build_rows, scan_folder_per_track
from .models import AlbumGroup, AlbumResult, Candidate
from .resolve import (
    album_detail,
    itunes_artist_catalog_candidates,
    resolve_album_id,
    resolve_album_two_stage,
)
from .tags import read_tags
from .textutil import artists_match


def _candidate_from_resolution(source: str, album: dict, tracks: list[dict],
                               score: float, via: str) -> Candidate:
    return Candidate(
        source=source,
        album_id=str(album.get("id", "")),
        name=album.get("name", ""),
        artist=album.get("artist_name", ""),
        track_count=len(tracks) or (album.get("track_count") or 0),
        tracks=sorted(tracks, key=lambda t: (t.get("cd") or 1, t.get("no") or 0)),
        via=via,
        score=score,
        artwork_url=album.get("artwork_url", ""),
        release_date=album.get("release_date", ""),
        storefront=album.get("storefront", ""),
    )


def weak_match(rows: list[dict], file_count: int) -> bool:
    """True when fewer than half of the files matched a track — the resolved
    album is probably wrong and should be confirmed by the user instead of
    reported as matched."""
    matched = sum(1 for r in rows if r.get("external_id"))
    return matched < math.ceil(file_count / 2)


def scan_album(group: AlbumGroup, opts, log=None,
               cancel: threading.Event | None = None) -> AlbumResult:
    """Reproduce scan_folder_album + per-track fallback semantics.

    resolved → "matched" (chosen set, rows built); only artist-catalog
    candidates → "needs_confirm" (candidates, no rows); per-track fallback
    produced matches → "matched" (chosen=None); nothing → "unmatched";
    exceptions → "error"."""
    result = AlbumResult(group=group, status="unmatched")
    if cancel is not None and cancel.is_set():
        return result

    def emit(message: str) -> None:
        if log:
            log(message)

    try:
        files = sorted(group.files)
        tagged = [(f, read_tags(f) or {}) for f in files]
        emit(tr("扫描文件夹：{0}", group.folder))

        # Path 1: two-stage (translate via iTunes → look up in source)
        resolved = resolve_album_two_stage(tagged, opts, log)
        if resolved:
            source, album_id, conf, expected_artist = resolved
            album, ne_tracks = album_detail(source, album_id, opts)
            if album and ne_tracks:
                chosen = _candidate_from_resolution(source, album, ne_tracks, conf, "resolved")
                result.chosen = chosen
                result.candidates = [chosen]
                result.rows = build_rows(group, tagged, chosen, conf, opts)
                if artists_match(album.get("artist_name", ""), expected_artist) is False:
                    _demote_to_needs_confirm(result, tagged, opts, emit,
                                             tr("解析到的专辑歌手 {0} 与预期 {1} 不符，已标记为待确认",
                                                album.get("artist_name", ""), expected_artist))
                elif weak_match(result.rows, len(files)):
                    _demote_to_needs_confirm(result, tagged, opts, emit)
                else:
                    result.status = "matched"
                return result

        # Path 2: NetEase song-vote — rescues folders whose album/artist tags
        # are missing or too garbled to translate.
        if "netease" in opts.sources:
            emit(tr("尝试来源：{0}", "netease"))
            album_id, song_score = resolve_album_id(tagged, opts, log, "netease")
            if album_id:
                album, ne_tracks = album_detail("netease", album_id, opts)
                if album and ne_tracks:
                    chosen = _candidate_from_resolution("netease", album, ne_tracks,
                                                        song_score, "song-vote")
                    result.chosen = chosen
                    result.candidates = [chosen]
                    result.rows = build_rows(group, tagged, chosen, song_score, opts)
                    if weak_match(result.rows, len(files)):
                        _demote_to_needs_confirm(result, tagged, opts, emit)
                    else:
                        result.status = "matched"
                    return result
            emit(tr("来源 {0} 未命中", "netease"))

        # Path 3: iTunes artist-catalog candidates for manual confirmation.
        candidates = itunes_artist_catalog_candidates(tagged, group.folder, opts)
        if candidates:
            emit(tr("找到 {0} 个候选专辑", len(candidates)))
            result.candidates = candidates
            result.status = "needs_confirm"
            return result

        # Path 4: per-track fallback.
        emit(tr("未能解析专辑，回退到逐曲匹配"))
        rows = scan_folder_per_track(tagged, opts, log, cancel)
        result.rows = rows
        result.status = "matched" if any(r.get("external_id") for r in rows) else "unmatched"
        return result
    except Exception as exc:
        result.status = "error"
        result.error = str(exc)
        return result


def _demote_to_needs_confirm(result: AlbumResult, tagged, opts, emit,
                             message: str | None = None) -> None:
    """A weak or wrong-artist auto-match: keep the rows (all apply=False),
    keep `chosen`, and offer artist-catalog alternatives for confirmation."""
    for row in result.rows:
        row["apply"] = False
    seen = {(result.chosen.source, result.chosen.album_id)} if result.chosen else set()
    candidates = [result.chosen] if result.chosen else []
    for c in itunes_artist_catalog_candidates(tagged, result.group.folder, opts):
        if (c.source, c.album_id) not in seen:
            seen.add((c.source, c.album_id))
            candidates.append(c)
    result.candidates = candidates
    result.status = "needs_confirm"
    emit(message or tr("自动匹配的结果较弱，已标记为待确认"))


def rows_for_candidate(group: AlbumGroup, candidate: Candidate, opts) -> list[dict]:
    """Port of /api/match-folder: fetch the album detail when the candidate
    lacks tracks, then build rows with base confidence 0.95."""
    if not candidate.tracks:
        _album, tracks = album_detail(candidate.source, candidate.album_id, opts)
        if tracks:
            candidate = Candidate(**{**candidate.__dict__, "tracks": tracks,
                                     "track_count": len(tracks)})
    tagged = [(f, read_tags(f) or {}) for f in sorted(group.files)]
    return build_rows(group, tagged, candidate, 0.95, opts)


def scan_library(root: Path, opts, on_album: Callable[[AlbumResult], None], log=None,
                 cancel: threading.Event | None = None) -> list[AlbumResult]:
    """Scan every album group under `root`, reporting each result via on_album."""
    results: list[AlbumResult] = []
    for group in group_albums(Path(root)):
        if cancel is not None and cancel.is_set():
            break
        result = scan_album(group, opts, log=log, cancel=cancel)
        results.append(result)
        if on_album:
            on_album(result)
        time.sleep(opts.delay)
    return results
