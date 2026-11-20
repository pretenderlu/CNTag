"""Two-stage album resolution and candidate search.

Pipeline: encyclopedia (MusicBrainz/Wikidata) → iTunes translate →
per-source lookup, with a NetEase song-vote and iTunes artist-catalog
candidates as rescues.
"""
from __future__ import annotations

import time
from collections import Counter
from pathlib import Path
from typing import Callable

from . import encyclopedia as _encyc
from .catalog_itunes import (
    _itunes_artist_song_album_candidates,
    _itunes_lookup_artist_albums,
    itunes_album_detail,
    itunes_search_albums,
    itunes_search_songs,
    itunes_translate_album,
)
from .catalog_netease import netease_album_detail, netease_find_album, netease_search_songs
from .i18n import tr
from .matching import build_song_query, find_top_song
from .models import Candidate
from .textutil import has_cjk, name_match_score, normalize_text, to_zh_cn

ARTIST_CATALOG_CANDIDATE_LIMIT = 8

LogFn = Callable[[str], None] | None


def _noop(_message: str) -> None:
    pass


def _emit(log: LogFn, message: str) -> None:
    (log or _noop)(message)


# ---------- dispatch ---------- #

def search_songs(source: str, query: str, opts) -> list[dict]:
    if source == "itunes":
        return itunes_search_songs(query, opts)
    if source == "netease":
        return netease_search_songs(query, opts)
    return []


def album_detail(source: str, album_id: str, opts) -> tuple[dict, list[dict]]:
    if source == "itunes":
        return itunes_album_detail(album_id, opts)
    if source == "netease":
        return netease_album_detail(album_id, opts)
    return {}, []


# ---------- encyclopedia stage ---------- #

def _encyclopedia_resolve(raw_album: str, raw_artist: str, target_count: int,
                          opts) -> dict | None:
    """Stage 0: resolve raw artist/album to canonical Chinese names via
    external knowledge bases (MusicBrainz, with Wikidata as fallback)."""
    if not opts.use_encyclopedia or not raw_artist:
        return None
    if has_cjk(raw_album) and has_cjk(raw_artist):
        return None

    candidates = _encyc.find_artist_candidates(raw_artist)
    if not candidates:
        return None
    primary = candidates[0]
    cn_artist = to_zh_cn(primary["cn_name"], opts.simplified)

    # If the user already has a CJK album tag, trust it and just attach the
    # resolved artist name.
    if has_cjk(raw_album):
        return {
            "cn_album": raw_album,
            "cn_artist": cn_artist,
            "source": primary["source"],
            "via": f"{primary['source']}-artist-only",
            "score": 0.85,
            "ext_artist_id": primary["id"],
        }

    # Score albums against raw_album across every available source's
    # discography; pick the global best.
    best = None  # (artist_rec, album_rec, score, cn_name)
    for artist in candidates:
        for alb in _encyc.artist_albums(artist):
            cand_names = [alb.get("name") or ""] + (alb.get("aliases") or [])
            cand_names = [n for n in cand_names if n]
            for nm in cand_names:
                score = name_match_score(raw_album, nm)
                if best is None or score > best[2]:
                    cn = alb.get("cn_name") or next(
                        (n for n in cand_names if has_cjk(n)), None
                    )
                    if cn:
                        best = (artist, alb, score, cn)

    if not best or best[2] < 0.55:
        return None

    artist, alb, score, cn = best
    return {
        "cn_album": to_zh_cn(cn, opts.simplified),
        "cn_artist": cn_artist,
        "source": artist["source"],
        "via": f"{artist['source']}-discography",
        "score": round(score, 2),
        "ext_artist_id": artist["id"],
        "ext_album_id": alb.get("id"),
    }


def resolve_album_two_stage(tagged: list[tuple[Path, dict]], opts, log: LogFn = None):
    """Two-stage resolution: translate names to Chinese, then look up the
    album in each enabled source by Chinese name. Returns
    (source, album_id, confidence, expected_artist) or None, where
    expected_artist is the translated artist the resolution was made
    against (used by the caller to sanity-check the fetched album)."""
    sample = next((t for _, t in tagged if t.get("album") or t.get("artist")), None)
    if not sample:
        return None

    raw_album = (sample.get("album") or "").strip()
    raw_artist = (sample.get("artist") or "").strip()
    target = len(tagged)

    cn_album, cn_artist = raw_album, raw_artist
    itunes_match: dict | None = None

    # Stage 0: encyclopedia (MusicBrainz/Wikidata) entity resolution
    encyc_match = _encyclopedia_resolve(raw_album, raw_artist, target, opts)
    if encyc_match:
        cn_album = encyc_match["cn_album"]
        cn_artist = encyc_match["cn_artist"]
        _emit(log, tr("已翻译：{0} / {1} → {2} / {3}",
                      raw_artist, raw_album, cn_artist, cn_album))
    elif has_cjk(raw_album) and has_cjk(raw_artist):
        pass  # already Chinese; no translation needed
    else:
        # Stage 1: iTunes-translate fallback
        itunes_match = itunes_translate_album(raw_album, raw_artist, target, opts)
        if itunes_match:
            cn_album = itunes_match["album_name"]
            cn_artist = itunes_match["artist_name"]
            _emit(log, tr("已翻译：{0} / {1} → {2} / {3}",
                          raw_artist, raw_album, cn_artist, cn_album))
        else:
            _emit(log, tr("无法翻译：{0} / {1}", raw_artist, raw_album))

    # Stage 2: look up album in each source in priority order
    for source in opts.sources:
        if source == "netease":
            ne = netease_find_album(cn_album, cn_artist, target, opts)
            if ne:
                _emit(log, tr("已解析专辑：{0} - {1}（{2} 首曲目）",
                              ne["album_artist"], ne["album_name"],
                              ne["track_count"] or target))
                return ("netease", ne["album_id"], ne["score"], cn_artist)
        elif source == "itunes":
            if itunes_match:
                _emit(log, tr("已解析专辑：{0} - {1}（{2} 首曲目）",
                              cn_artist, cn_album, itunes_match["track_count"]))
                return ("itunes", itunes_match["album_id"], itunes_match["score"], cn_artist)
            t = itunes_translate_album(cn_album, cn_artist, target, opts)
            if t:
                _emit(log, tr("已解析专辑：{0} - {1}（{2} 首曲目）",
                              t["artist_name"], t["album_name"], t["track_count"]))
                return ("itunes", t["album_id"], t["score"], cn_artist)
    return None


def resolve_album_id(tagged: list[tuple[Path, dict]], opts, log: LogFn, source: str):
    """Song-vote resolution: search a few track titles, count album_ids."""
    candidates = [(f, t) for f, t in tagged if t.get("title")][: opts.vote_n]
    if not candidates:
        return None, 0.0

    votes: Counter = Counter()
    best_score = 0.0
    detail = {}
    for path, tags in candidates:
        q = build_song_query(tags, path.stem)
        songs = search_songs(source, q, opts)
        top, score = find_top_song(songs)
        if top and top.get("album_id"):
            aid = top["album_id"]
            votes[aid] += 1
            best_score = max(best_score, score)
            detail[aid] = (top.get("album_name", ""), top.get("artist_name", ""))
        time.sleep(opts.delay)

    if not votes:
        return None, 0.0
    winner, count = votes.most_common(1)[0]
    aname, aartist = detail.get(winner, ("?", "?"))
    _emit(log, tr("投票：{0}/{1} 票支持 {2} - {3}", count, len(candidates), aartist, aname))
    return winner, best_score


# ---------- iTunes artist-catalog candidates ---------- #

def _candidate_from_album(album: dict, tracks: list[dict], via: str, score: float) -> Candidate:
    return Candidate(
        source=album.get("source", "itunes"),
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


def _raw_album_artist_from_tagged(tagged: list[tuple[Path, dict]]) -> tuple[str, str]:
    sample = next((t for _, t in tagged if t.get("album") or t.get("artist")), None)
    if not sample:
        return "", ""
    return (sample.get("album") or "").strip(), (sample.get("artist") or "").strip()


def _candidate_local_terms(tagged: list[tuple[Path, dict]], folder: Path) -> list[str]:
    terms: list[str] = [folder.name]
    raw_album, _raw_artist = _raw_album_artist_from_tagged(tagged)
    if raw_album:
        terms.append(raw_album)
    for path, tags in tagged:
        terms.extend([
            path.stem,
            (tags.get("title") or "").strip(),
            (tags.get("album") or "").strip(),
        ])

    seen: set[str] = set()
    result: list[str] = []
    for term in terms:
        normalized = normalize_text(term)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(term)
    return result


def _score_artist_catalog_candidate(
    album: dict,
    tracks: list[dict],
    terms: list[str],
    target_count: int,
    rank: int,
) -> float:
    names = [album.get("name", "")]
    names.extend(t.get("name", "") for t in tracks)
    name_score = max(
        (name_match_score(term, name) for term in terms for name in names if term and name),
        default=0.0,
    )

    candidate_count = album.get("track_count") or len(tracks)
    diff = abs((candidate_count or 0) - target_count)
    if diff == 0:
        count_score = 1.0
    elif diff <= 1:
        count_score = 0.75
    elif diff <= 3:
        count_score = 0.45
    else:
        count_score = 0.15

    rank_score = max(0.0, 1.0 - rank * 0.03)
    if name_score > 0:
        return name_score * 0.65 + count_score * 0.20 + rank_score * 0.15
    return count_score * 0.20 + rank_score * 0.30


def _rank_artist_catalog_candidates(
    tagged: list[tuple[Path, dict]],
    folder: Path,
    candidates: list[tuple[dict, list[dict]]],
) -> list[tuple[dict, list[dict], float]]:
    terms = _candidate_local_terms(tagged, folder)
    target_count = len(tagged)
    scored = [
        (_score_artist_catalog_candidate(album, tracks, terms, target_count, rank), rank, album, tracks)
        for rank, (album, tracks) in enumerate(candidates)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [(album, tracks, score) for score, _rank, album, tracks in scored[:ARTIST_CATALOG_CANDIDATE_LIMIT]]


def itunes_artist_catalog_candidates(
    tagged: list[tuple[Path, dict]],
    folder: Path,
    opts,
) -> list[Candidate]:
    """Ranked iTunes candidates from the artist's catalog, used when the
    two-stage pipeline produced nothing. Song groups first, then album
    lookups."""
    if "itunes" not in opts.sources:
        return []

    _, raw_artist = _raw_album_artist_from_tagged(tagged)
    if not raw_artist:
        return []

    out: list[Candidate] = []
    for album, tracks, score in _rank_artist_catalog_candidates(
        tagged, folder, _itunes_artist_song_album_candidates(raw_artist, opts)
    ):
        out.append(_candidate_from_album(album, tracks, "artist-catalog", score))
    if out:
        return out

    detail_candidates: list[tuple[dict, list[dict]]] = []
    for raw_album in _itunes_lookup_artist_albums(raw_artist, opts):
        album_id = str(raw_album.get("collectionId", ""))
        if not album_id:
            continue
        album, tracks = album_detail("itunes", album_id, opts)
        if not album or not tracks:
            continue
        detail_candidates.append((album, tracks))

    for album, tracks, score in _rank_artist_catalog_candidates(tagged, folder, detail_candidates):
        out.append(_candidate_from_album(album, tracks, "artist-catalog", score))
    return out


# ---------- manual candidate search (port of /api/itunes-preview) ---------- #

def search_candidates(album: str, artist: str, local_count: int, opts) -> list[Candidate]:
    """iTunes album candidates for a user-supplied album/artist query —
    phases A (direct search) + B (artist discography), top 6, with the
    track list of each candidate filled in."""
    album = (album or "").strip()
    artist = (artist or "").strip()
    if not album and not artist:
        return []

    target_count = local_count or 0
    candidates: list[Candidate] = []
    seen: set[str] = set()

    def make_candidate(a, phase, score):
        return Candidate(
            source="itunes",
            album_id=str(a.get("collectionId", "")),
            name=to_zh_cn(a.get("collectionName", ""), opts.simplified),
            artist=to_zh_cn(a.get("artistName", ""), opts.simplified),
            track_count=a.get("trackCount") or 0,
            via=phase,
            score=round(score, 3),
            artwork_url=(a.get("artworkUrl100") or "").replace("100x100", "600x600"),
            release_date=(a.get("releaseDate") or "")[:10],
            storefront=a.get("storefront", ""),
        )

    # Phase A: direct combined search.
    parts = [p for p in (artist, album) if p]
    if parts:
        direct = itunes_search_albums(" ".join(parts), opts)
        for idx, a in enumerate(direct):
            aid = str(a.get("collectionId", ""))
            if not aid or aid in seen:
                continue
            seen.add(aid)
            rank_score = max(0.0, 1.0 - idx * 0.10)
            tc = a.get("trackCount") or 0
            if target_count:
                tc_diff = abs(tc - target_count)
                tc_score = 1.0 if tc_diff == 0 else (0.85 if tc_diff <= 1 else 0.5)
            else:
                tc_score = 0.6
            ns = name_match_score(album, a.get("collectionName", "")) if album else 0.5
            score = rank_score * 0.3 + tc_score * 0.3 + ns * 0.4
            candidates.append(make_candidate(a, "direct", score))

    # Phase B: artist→albums + name/count match.
    if artist:
        for a in _itunes_lookup_artist_albums(artist, opts):
            aid = str(a.get("collectionId", ""))
            if not aid or aid in seen:
                continue
            ns = name_match_score(album, a.get("collectionName", "")) if album else 0.4
            tc = a.get("trackCount") or 0
            if target_count and abs(tc - target_count) <= 2:
                ns += 0.15
            if ns < 0.35:
                continue
            seen.add(aid)
            candidates.append(make_candidate(a, "artist-list", ns + 0.05))

    candidates.sort(key=lambda c: c.score, reverse=True)
    candidates = candidates[:6]
    for c in candidates:
        _, tracks = itunes_album_detail(c.album_id, opts)
        c.tracks = tracks
        if tracks:
            c.track_count = len(tracks)
    return candidates
