"""NetEase Cloud Music web API, normalized to the shared track/album shapes."""
from __future__ import annotations

from .http import http_session

NETEASE_SEARCH_URL = "https://music.163.com/api/search/get/web"
NETEASE_ALBUM_URL = "https://music.163.com/api/v1/album/{}"
NETEASE_HEADERS = {
    "Referer": "https://music.163.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Cookie": "appver=2.0.2;",
}


def _netease_search_raw(query: str, limit: int) -> list[dict]:
    if not query.strip():
        return []
    try:
        r = http_session().post(
            NETEASE_SEARCH_URL,
            data={"s": query, "type": 1, "limit": limit, "offset": 0},
            headers=NETEASE_HEADERS, timeout=10,
        )
        r.raise_for_status()
        return ((r.json().get("result") or {}).get("songs")) or []
    except Exception:
        return []


def _netease_search_albums_raw(query: str, limit: int) -> list[dict]:
    """NetEase album search (type=10). Reliable for Chinese queries; near-empty for English."""
    if not query.strip():
        return []
    try:
        r = http_session().post(
            NETEASE_SEARCH_URL,
            data={"s": query, "type": 10, "limit": limit, "offset": 0},
            headers=NETEASE_HEADERS, timeout=10,
        )
        r.raise_for_status()
        return ((r.json().get("result") or {}).get("albums")) or []
    except Exception:
        return []


def _netease_album_raw(album_id: int) -> tuple[dict, list[dict]]:
    try:
        r = http_session().get(NETEASE_ALBUM_URL.format(album_id), headers=NETEASE_HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json()
        return data.get("album") or {}, data.get("songs") or []
    except Exception:
        return {}, []


def netease_search_songs(query: str, opts) -> list[dict]:
    raw = _netease_search_raw(query, opts.limit)
    return [_netease_song_to_normalized(s) for s in raw]


def netease_album_detail(album_id: str, opts) -> tuple[dict, list[dict]]:
    try:
        aid = int(album_id)
    except (ValueError, TypeError):
        return {}, []
    album_raw, songs_raw = _netease_album_raw(aid)
    if not album_raw or not songs_raw:
        return {}, []
    artists = album_raw.get("artists") or []
    album = {
        "source": "netease",
        "id": str(album_raw.get("id", "")),
        "name": album_raw.get("name", ""),
        "artist_name": "/".join(a.get("name", "") for a in artists if a.get("name")),
        "track_count": len(songs_raw),
    }
    tracks = [_netease_album_track_to_normalized(s) for s in songs_raw]
    return album, tracks


def _netease_song_to_normalized(s: dict) -> dict:
    artists = s.get("artists") or []
    album = s.get("album") or {}
    artist_name = "/".join(a.get("name", "") for a in artists if a.get("name"))
    return {
        "source": "netease",
        "id": str(s.get("id", "")),
        "name": s.get("name", ""),
        "artist_name": artist_name,
        "album_id": str(album.get("id", "")),
        "album_name": album.get("name", ""),
        "album_artist_name": artist_name,
        "no": None,
        "cd": None,
        "aliases": [],
    }


def _netease_album_track_to_normalized(s: dict) -> dict:
    artists = s.get("ar") or []
    album = s.get("al") or {}
    artist_name = "/".join(a.get("name", "") for a in artists if a.get("name"))
    return {
        "source": "netease",
        "id": str(s.get("id", "")),
        "name": s.get("name", ""),
        "artist_name": artist_name,
        "album_id": str(album.get("id", "")),
        "album_name": album.get("name", ""),
        "album_artist_name": artist_name,
        "no": s.get("no"),
        "cd": s.get("cd"),
        "aliases": list(s.get("alia") or []),
    }


def netease_find_album(cn_album: str, cn_artist: str, target_count: int,
                       opts) -> dict | None:
    """Find a NetEase album_id given Chinese album+artist. Tries album-search
    first (type=10), then song-search-extract as a fallback."""
    from .catalog_itunes import _score_album_candidate

    if not cn_album:
        return None
    query = f"{cn_artist} {cn_album}".strip()

    raw = _netease_search_albums_raw(query, opts.limit)
    cands = []
    if raw:
        # Prefer entries whose artist field contains cn_artist
        if cn_artist:
            primary = [a for a in raw if any(
                cn_artist in (x.get("name") or "") or (x.get("name") or "") in cn_artist
                for x in (a.get("artists") or [])
            )]
            cands = primary if primary else raw
        else:
            cands = raw
    if cands:
        def score(a):
            tc = a.get("size") or 0
            name_match = 1.0 if a.get("name") == cn_album else (
                0.7 if cn_album and cn_album in (a.get("name") or "") else 0.4)
            return _score_album_candidate(raw.index(a), tc, target_count) * name_match
        best = max(cands, key=score)
        s = score(best)
        if s >= 0.45:
            return {
                "album_id": str(best.get("id", "")),
                "album_name": best.get("name", ""),
                "album_artist": "/".join(x.get("name", "") for x in (best.get("artists") or [])),
                "track_count": best.get("size") or 0,
                "score": round(min(1.0, s), 2),
                "via": "album-search",
            }

    # Fallback: song search → extract album_id
    songs = _netease_search_raw(query, opts.limit)
    for s in songs:
        artists = s.get("artists") or []
        album = s.get("album") or {}
        a_name = album.get("name") or ""
        if cn_album and (a_name == cn_album or cn_album in a_name):
            if not cn_artist or any(cn_artist in (a.get("name") or "") for a in artists):
                return {
                    "album_id": str(album.get("id", "")),
                    "album_name": a_name,
                    "album_artist": "/".join(a.get("name", "") for a in artists if a.get("name")),
                    "track_count": 0,
                    "score": 0.75,
                    "via": "song-extract",
                }
    return None
