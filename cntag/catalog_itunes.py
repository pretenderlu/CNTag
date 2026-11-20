"""iTunes Search/Lookup API, normalized to the shared track/album shapes.

song:  {source, id, name, artist_name, album_id, album_name,
        album_artist_name, no, cd, aliases, storefront}
album: {source, id, name, artist_name, track_count, storefront,
        artwork_url, release_date}
"""
from __future__ import annotations

from dataclasses import replace

from . import __version__
from .http import http_session
from .textutil import artists_match, has_cjk, name_match_score, normalize_text, to_zh_cn

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
ITUNES_LOOKUP_URL = "https://itunes.apple.com/lookup"


def _headers() -> dict:
    return {"User-Agent": f"CNTag/{__version__}"}


def _artwork_url(raw: dict) -> str:
    url = raw.get("artworkUrl100") or ""
    return url.replace("100x100", "600x600") if url else ""


def _itunes_storefronts(opts) -> tuple[str, ...]:
    country = (opts.country or "tw").strip().lower() or "tw"
    storefronts = [country]
    if country != "us":
        storefronts.append("us")
    if country != "tw":
        storefronts.append("tw")
    return tuple(storefronts)


def _itunes_opts_for_country(opts, country: str):
    if (opts.country or "").strip().lower() == country:
        return opts
    return replace(opts, country=country)


def _dedupe_itunes_results(results: list[dict], key: str) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()
    for item in results:
        item_key = str(item.get(key, ""))
        if item_key and item_key in seen:
            continue
        if item_key:
            seen.add(item_key)
        merged.append(item)
    return merged


def itunes_search_songs(query: str, opts) -> list[dict]:
    if not query.strip():
        return []
    normalized: list[dict] = []
    for country in _itunes_storefronts(opts):
        country_opts = _itunes_opts_for_country(opts, country)
        try:
            r = http_session().get(
                ITUNES_SEARCH_URL,
                params={
                    "term": query, "country": country, "media": "music",
                    "entity": "song", "limit": opts.limit,
                },
                headers=_headers(), timeout=10,
            )
            r.raise_for_status()
            results = r.json().get("results") or []
        except Exception:
            continue
        for track in results:
            item = _itunes_track_to_normalized(track, country_opts)
            item["storefront"] = country
            normalized.append(item)
    return _dedupe_itunes_results(normalized, "id")


def itunes_search_albums(query: str, opts) -> list[dict]:
    """Album search returns much more reliable rankings than song search for
    English queries that target Chinese-language albums. Use this as the
    primary album-resolver for iTunes."""
    if not query.strip():
        return []
    albums: list[dict] = []
    for country in _itunes_storefronts(opts):
        try:
            r = http_session().get(
                ITUNES_SEARCH_URL,
                params={
                    "term": query, "country": country, "media": "music",
                    "entity": "album", "limit": opts.limit,
                },
                headers=_headers(), timeout=10,
            )
            r.raise_for_status()
            results = r.json().get("results") or []
        except Exception:
            continue
        for album in results:
            item = dict(album)
            item["storefront"] = country
            albums.append(item)
    return _dedupe_itunes_results(albums, "collectionId")


def itunes_album_detail(album_id: str, opts) -> tuple[dict, list[dict]]:
    for country in _itunes_storefronts(opts):
        country_opts = _itunes_opts_for_country(opts, country)
        try:
            r = http_session().get(
                ITUNES_LOOKUP_URL,
                params={"id": album_id, "country": country, "entity": "song"},
                headers=_headers(), timeout=10,
            )
            r.raise_for_status()
            data = r.json().get("results") or []
        except Exception:
            continue
        album_raw = next((x for x in data if x.get("wrapperType") == "collection"), {})
        track_raws = [x for x in data if x.get("wrapperType") == "track"]
        if not album_raw or not track_raws:
            continue
        album = {
            "source": "itunes",
            "id": str(album_raw.get("collectionId", "")),
            "name": to_zh_cn(album_raw.get("collectionName", ""), country_opts.simplified),
            "artist_name": to_zh_cn(album_raw.get("artistName", ""), country_opts.simplified),
            "track_count": album_raw.get("trackCount") or len(track_raws),
            "storefront": country,
            "artwork_url": _artwork_url(album_raw),
            "release_date": (album_raw.get("releaseDate") or "")[:10],
        }
        tracks = [_itunes_track_to_normalized(t, country_opts) for t in track_raws]
        for track in tracks:
            track["storefront"] = country
        return album, tracks
    return {}, []


def _itunes_track_to_normalized(t: dict, opts) -> dict:
    return {
        "source": "itunes",
        "id": str(t.get("trackId", "")),
        "name": to_zh_cn(t.get("trackName", ""), opts.simplified),
        "artist_name": to_zh_cn(t.get("artistName", ""), opts.simplified),
        "album_id": str(t.get("collectionId", "")),
        "album_name": to_zh_cn(t.get("collectionName", ""), opts.simplified),
        "album_artist_name": to_zh_cn(t.get("artistName", ""), opts.simplified),
        "no": t.get("trackNumber"),
        "cd": t.get("discNumber"),
        "aliases": [],
    }


def _itunes_artist_name_matches(query: str, candidate: str) -> bool:
    q = normalize_text(query)
    c = normalize_text(candidate)
    if not q or not c:
        return False
    if q == c:
        return True
    if q in c or c in q:
        shorter, longer = sorted((len(q), len(c)))
        return shorter / longer >= 0.88
    return name_match_score(query, candidate) >= 0.75


def _itunes_catalog_storefronts(opts) -> tuple[str, ...]:
    storefronts = list(_itunes_storefronts(opts))
    for country in ("cn", "hk", "jp"):
        if country not in storefronts:
            storefronts.append(country)
    return tuple(storefronts)


def _itunes_collection_from_track(track: dict, country: str) -> dict | None:
    cid = track.get("collectionId")
    if not cid:
        return None
    return {
        "wrapperType": "collection",
        "collectionId": cid,
        "collectionName": track.get("collectionName", ""),
        "artistName": track.get("artistName", ""),
        "trackCount": track.get("trackCount") or 0,
        "artworkUrl100": track.get("artworkUrl100", ""),
        "releaseDate": track.get("releaseDate", ""),
        "storefront": country,
    }


def _itunes_artist_song_album_candidates(artist_query: str, opts) -> list[tuple[dict, list[dict]]]:
    if not artist_query.strip():
        return []

    groups: dict[str, tuple[dict, list[dict], set[str]]] = {}
    for country in _itunes_catalog_storefronts(opts):
        country_opts = _itunes_opts_for_country(opts, country)
        searches = (
            {"term": artist_query, "country": country, "media": "music",
             "entity": "song", "attribute": "artistTerm", "limit": 200},
            {"term": artist_query, "country": country, "media": "music",
             "entity": "song", "limit": 200},
        )
        for params in searches:
            try:
                r = http_session().get(ITUNES_SEARCH_URL, params=params,
                                       headers=_headers(), timeout=10)
                r.raise_for_status()
                song_results = r.json().get("results") or []
            except Exception:
                song_results = []
            for raw_track in song_results:
                if raw_track.get("wrapperType") != "track":
                    continue
                if not _itunes_artist_name_matches(artist_query, raw_track.get("artistName", "")):
                    continue
                track = _itunes_track_to_normalized(raw_track, country_opts)
                track["storefront"] = country
                album_id = track.get("album_id")
                track_id = track.get("id")
                if not album_id or not track_id:
                    continue
                if album_id not in groups:
                    groups[album_id] = (
                        {
                            "source": "itunes",
                            "id": album_id,
                            "name": track.get("album_name", ""),
                            "artist_name": track.get("album_artist_name", "") or track.get("artist_name", ""),
                            "track_count": raw_track.get("trackCount") or 0,
                            "storefront": country,
                            "artwork_url": _artwork_url(raw_track),
                            "release_date": (raw_track.get("releaseDate") or "")[:10],
                        },
                        [],
                        set(),
                    )
                album, tracks, seen = groups[album_id]
                if track_id in seen:
                    continue
                seen.add(track_id)
                tracks.append(track)

    candidates: list[tuple[dict, list[dict]]] = []
    for album, tracks, _seen in groups.values():
        tracks.sort(key=lambda t: (t.get("cd") or 1, t.get("no") or 0, t.get("name", "")))
        if not album.get("track_count"):
            album["track_count"] = len(tracks)
        candidates.append((album, tracks))
    return candidates


def _itunes_lookup_artist_albums(artist_query: str, opts) -> list[dict]:
    """Find the most likely artistId for an artist query, then return all of
    that artist's albums via /lookup. Falls back to []. Used as a second
    pass when direct album search misses (typical for albums whose English
    or pinyin alias isn't indexed)."""
    if not artist_query.strip():
        return []
    albums: list[dict] = []
    for country in _itunes_catalog_storefronts(opts):
        try:
            r = http_session().get(ITUNES_SEARCH_URL,
                                   params={"term": artist_query, "country": country,
                                           "media": "music", "entity": "musicArtist", "limit": 5},
                                   headers=_headers(), timeout=10)
            r.raise_for_status()
            artists = r.json().get("results") or []
        except Exception:
            artists = []
        if artists:
            # Prefer CJK-named artists, but US often indexes useful English aliases.
            cjk = [a for a in artists if has_cjk(a.get("artistName", ""))]
            pool = cjk if cjk else artists
            best = max(pool, key=lambda a: name_match_score(artist_query, a.get("artistName", "")))
            aid = best.get("artistId")
            if aid:
                try:
                    r = http_session().get(ITUNES_LOOKUP_URL,
                                           params={"id": aid, "country": country,
                                                   "entity": "album", "limit": 200},
                                           headers=_headers(), timeout=10)
                    r.raise_for_status()
                    results = r.json().get("results") or []
                except Exception:
                    results = []
                for album in results:
                    if album.get("wrapperType") != "collection":
                        continue
                    item = dict(album)
                    item["storefront"] = country
                    albums.append(item)

        for params in (
            {"term": artist_query, "country": country, "media": "music",
             "entity": "song", "attribute": "artistTerm", "limit": 200},
            {"term": artist_query, "country": country, "media": "music",
             "entity": "song", "limit": 200},
        ):
            try:
                r = http_session().get(ITUNES_SEARCH_URL, params=params,
                                       headers=_headers(), timeout=10)
                r.raise_for_status()
                song_results = r.json().get("results") or []
            except Exception:
                song_results = []
            for track in song_results:
                if track.get("wrapperType") != "track":
                    continue
                if not _itunes_artist_name_matches(artist_query, track.get("artistName", "")):
                    continue
                album = _itunes_collection_from_track(track, country)
                if album:
                    albums.append(album)
    return _dedupe_itunes_results(albums, "collectionId")


def itunes_translate_album(raw_album: str, raw_artist: str, target_count: int,
                           opts) -> dict | None:
    """Multi-phase iTunes translation:
       Phase A — direct combined album search (works when iTunes indexes
                 the album's English/pinyin alias, e.g. Jay Chou 'Yeh Hui-mei').
       Phase B — artist lookup → list all of artist's albums → match by
                 track count + pinyin/name similarity (rescues cases where
                 the alias isn't indexed, e.g. 'Dan Dan You Qing' → 淡淡幽情).
    """
    direct: dict | None = None

    # Phase A
    parts, seen = [], set()
    for v in (raw_artist, raw_album):
        v = (v or "").strip()
        if v and v.lower() not in seen:
            parts.append(v)
            seen.add(v.lower())
    if parts:
        query = " ".join(parts)
        albums = itunes_search_albums(query, opts)
        cjk = [a for a in albums if has_cjk(a.get("collectionName", "")) or has_cjk(a.get("artistName", ""))]
        if cjk:
            def artist_factor(a):
                match = artists_match(raw_artist, a.get("artistName", ""))
                return {True: 1.0, None: 0.5}.get(match, 0.0)

            def s_direct(a):
                base = _score_album_candidate(albums.index(a), a.get("trackCount") or 0, target_count)
                ns = name_match_score(raw_album, a.get("collectionName", ""))
                return base * 0.35 + ns * 0.35 + artist_factor(a) * 0.30
            # A wrong-artist album is only eligible when nothing else is —
            # its score can then never reach the 0.85 early-return below.
            eligible = [a for a in cjk if artist_factor(a) > 0] or cjk
            best = max(eligible, key=s_direct)
            score = s_direct(best)
            direct = {
                "album_id": str(best.get("collectionId", "")),
                "album_name": to_zh_cn(best.get("collectionName", ""), opts.simplified),
                "artist_name": to_zh_cn(best.get("artistName", ""), opts.simplified),
                "track_count": best.get("trackCount") or 0,
                "score": round(min(1.0, score), 2),
                "query": query,
                "phase": "direct",
            }
            if direct["score"] >= 0.85:
                return direct

    # Phase B: artist → albums + name/count match
    if raw_artist:
        cands = _itunes_lookup_artist_albums(raw_artist, opts)
        if cands:
            window = [a for a in cands if abs((a.get("trackCount") or 0) - target_count) <= 2]
            pool = window if window else cands
            scored = [(a, name_match_score(raw_album, a.get("collectionName", ""))) for a in pool]
            scored.sort(key=lambda x: x[1], reverse=True)
            if scored and scored[0][1] >= 0.7:
                best, ns = scored[0]
                tc = best.get("trackCount") or 0
                tc_diff = abs(tc - target_count)
                tc_score = 1.0 if tc_diff == 0 else (0.85 if tc_diff <= 1 else 0.55)
                total = ns * 0.6 + tc_score * 0.4
                phase_b = {
                    "album_id": str(best.get("collectionId", "")),
                    "album_name": to_zh_cn(best.get("collectionName", ""), opts.simplified),
                    "artist_name": to_zh_cn(best.get("artistName", ""), opts.simplified),
                    "track_count": tc,
                    "score": round(min(1.0, total), 2),
                    "query": f"artist:{raw_artist}",
                    "phase": "artist-list",
                }
                if not direct or phase_b["score"] > direct["score"]:
                    return phase_b

    return direct


def _score_album_candidate(rank: int, candidate_track_count: int, target_count: int) -> float:
    rank_score = max(0.0, 1.0 - rank * 0.08)
    diff = abs((candidate_track_count or 0) - target_count)
    if diff == 0:
        cs = 1.0
    elif diff <= 1:
        cs = 0.92
    elif diff <= 3:
        cs = 0.82
    else:
        cs = 0.65
    return rank_score * cs
