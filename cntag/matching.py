"""File→track matching and result-row building."""
from __future__ import annotations

import threading
import time
from pathlib import Path

from .models import AlbumGroup, Candidate
from .tags import TAG_FIELDS
from .textutil import has_cjk, name_match_score, parse_int, similarity

ROW_NUMBER_FIELDS = ("tracknumber", "discnumber")


def empty_new_tags() -> dict:
    return {f: "" for f in TAG_FIELDS}


def build_row(path: Path, old: dict, new: dict, *, apply: bool,
              confidence: float, source: str = "", external_id: str = "",
              method: str = "", track: dict | None = None,
              multi_disc: bool = False) -> dict:
    row = {
        "file": str(path),
        "apply": bool(apply),
        "confidence": float(confidence),
        "source": source,
        "external_id": external_id,
        "match_method": method,
    }
    for f in TAG_FIELDS:
        row[f"old_{f}"] = (old or {}).get(f, "")
        row[f"new_{f}"] = (new or {}).get(f, "")
    for f in ROW_NUMBER_FIELDS:
        old_v = (old or {}).get(f, "")
        row[f"old_{f}"] = old_v
        new_v = ""
        if track:
            if f == "discnumber" and not multi_disc:
                pass  # only write disc numbers for multi-disc albums
            else:
                raw = track.get("no") if f == "tracknumber" else track.get("cd")
                if parse_int(raw) is not None and parse_int(raw) != parse_int(old_v):
                    new_v = str(parse_int(raw))
        row[f"new_{f}"] = new_v
    return row


def is_multi_disc(tracks: list[dict], group: AlbumGroup) -> bool:
    """Multi-disc when any candidate track is on cd > 1, or the group spans
    more than one disc folder."""
    if any((t.get("cd") or 1) > 1 for t in tracks):
        return True
    return len(set(group.disc_of.values())) > 1


def find_top_song(songs: list[dict]) -> tuple[dict | None, float]:
    if not songs:
        return None, 0.0

    def has_cn(s):
        return has_cjk(s.get("name", "")) or has_cjk(s.get("artist_name", ""))

    ranked = [(i, s) for i, s in enumerate(songs) if has_cn(s)]
    if not ranked:
        return None, 0.0
    rank, best = ranked[0]
    base = 0.85 if rank == 0 else (0.70 if rank == 1 else 0.55)
    artist = best.get("artist_name", "")
    if artist:
        same = sum(1 for s in songs if s.get("artist_name", "") == artist)
        if same >= 3:
            base = min(1.0, base + 0.10)
    return best, round(base, 2)


def build_song_query(tags: dict, fallback: str) -> str:
    parts, seen = [], set()
    for key in ("artist", "albumartist", "album", "title"):
        v = (tags.get(key) or "").strip()
        if v and v.lower() not in seen:
            parts.append(v)
            seen.add(v.lower())
    return " ".join(parts) or fallback


def _title_score(title: str, track: dict) -> float:
    """Best transliteration-aware score of a file title against a track's
    name and aliases."""
    best = 0.0
    for cand in [track.get("name", "")] + list(track.get("aliases") or []):
        if cand:
            best = max(best, name_match_score(title, cand))
    return best


def match_file_to_track(tags: dict, ne_tracks: list[dict],
                        disc_hint: int | None = None) -> tuple[dict | None, str]:
    title = (tags.get("title") or "").strip()
    track_no = parse_int(tags.get("tracknumber"))
    disc_no = parse_int(tags.get("discnumber"))
    if not disc_no and disc_hint:
        disc_no = disc_hint

    scores = {}
    if title:
        scores = {id(t): _title_score(title, t) for t in ne_tracks}
        best_title_track = max(ne_tracks, key=lambda t: scores[id(t)], default=None)
        best_title_score = scores.get(id(best_title_track), 0.0) if best_title_track else 0.0
    else:
        best_title_track, best_title_score = None, 0.0

    if track_no:
        cands = [t for t in ne_tracks if t.get("no") == track_no]
        if disc_no:
            cands = [t for t in cands if t.get("cd") == disc_no] or cands
        if len(cands) == 1:
            track = cands[0]
            if scores.get(id(track), 0.0) >= 0.9:
                return track, "tracknumber+title"
            if (best_title_track is not None and best_title_score >= 0.9
                    and scores.get(id(track), 0.0) < 0.5):
                return best_title_track, "title-pinyin"
            return track, "tracknumber"
        if cands:
            for t in cands:
                if title and title.lower() in [a.lower() for a in t.get("aliases", [])]:
                    return t, "tracknumber+alias"
            track = cands[0]
            if scores.get(id(track), 0.0) >= 0.9:
                return track, "tracknumber+title"
            return track, "tracknumber"

    if title:
        tl = title.lower()
        for t in ne_tracks:
            if any(tl == a.lower() for a in t.get("aliases", [])):
                return t, "alias-exact"
        if best_title_track is not None and best_title_score >= 0.9:
            return best_title_track, "title-pinyin"
        tl = title.lower()
        for t in ne_tracks:
            if any(tl == a.lower() for a in t.get("aliases", [])):
                return t, "alias-exact"
        best, best_sim = None, 0.0
        for t in ne_tracks:
            cands = list(t.get("aliases") or []) + [t.get("name", "")]
            for c in cands:
                if not c:
                    continue
                s = similarity(title, c)
                if s > best_sim:
                    best_sim, best = s, t
        if best and best_sim >= 0.85:
            return best, f"alias-fuzzy({best_sim:.2f})"

    return None, "no-match"


def build_rows(group: AlbumGroup, tagged: list[tuple[Path, dict]], candidate: Candidate,
               base_confidence: float, opts) -> list[dict]:
    """Port of music-cn-tagger's _build_rows_for_album.

    Position fallback sorts files by (disc, filename) and tracks by (cd, no);
    the disc comes from tags' discnumber, else group.disc_of."""
    album = {"name": candidate.name, "artist_name": candidate.artist}
    ne_tracks = candidate.tracks
    source = candidate.source
    multi_disc = is_multi_disc(ne_tracks, group)

    def disc_key(item):
        path, tags = item
        return (parse_int(tags.get("discnumber")) or group.disc_of.get(path) or 1,
                path.name.lower())

    sorted_files = sorted(tagged, key=disc_key)
    sorted_tracks = sorted(ne_tracks, key=lambda t: (t.get("cd") or 1, t.get("no") or 0))
    pos_map = {}
    if len(sorted_files) == len(sorted_tracks):
        pos_map = {sorted_files[i][0]: sorted_tracks[i] for i in range(len(sorted_files))}

    rows = []
    for path, tags in tagged:
        ne_track, method = match_file_to_track(tags, ne_tracks, disc_hint=group.disc_of.get(path))
        if not ne_track and pos_map.get(path):
            ne_track, method = pos_map[path], "position"
        if not ne_track:
            rows.append(build_row(path, tags, empty_new_tags(),
                                  apply=False, confidence=0.0,
                                  source=source, method=method))
            continue
        new = {
            "title": ne_track.get("name", ""),
            "artist": ne_track.get("artist_name", ""),
            "album": album["name"],
            "albumartist": album["artist_name"],
            "genre": "",
        }
        if method == "tracknumber+title":
            conf = 0.98
        elif method.startswith(("tracknumber", "alias-exact")):
            conf = 0.95
        elif method == "title-pinyin":
            conf = 0.90
        elif method.startswith("alias-fuzzy"):
            conf = 0.80
        elif method == "position":
            conf = 0.65
        else:
            conf = base_confidence
        result_cn = has_cjk(new["title"]) or has_cjk(new["artist"])
        apply_default = bool(conf >= opts.threshold and result_cn)
        rows.append(build_row(path, tags, new,
                              apply=apply_default, confidence=conf,
                              source=source, external_id=ne_track.get("id", ""),
                              method=method, track=ne_track, multi_disc=multi_disc))
    return rows


def scan_folder_per_track(tagged: list[tuple[Path, dict]], opts, log=None,
                          cancel: threading.Event | None = None) -> list[dict]:
    """Per-track fallback: search each file's title independently."""
    from .resolve import search_songs

    rows = []
    for path, old in tagged:
        if cancel is not None and cancel.is_set():
            break
        already_cn = has_cjk(old.get("title", "")) and has_cjk(old.get("artist", ""))
        if already_cn:
            rows.append(build_row(path, old, empty_new_tags(),
                                  apply=False, confidence=1.0, method="already-cn"))
            continue

        query = build_song_query(old, path.stem)
        best = None
        best_score = 0.0
        used_source = ""
        for source in opts.sources:
            songs = search_songs(source, query, opts)
            cand, score = find_top_song(songs)
            if cand:
                best, best_score, used_source = cand, score, source
                break

        new = empty_new_tags()
        ext_id = ""
        if best:
            ext_id = best.get("id", "")
            new["title"] = best.get("name", "")
            new["artist"] = best.get("artist_name", "")
            new["album"] = best.get("album_name", "")
            new["albumartist"] = best.get("album_artist_name", "") or best.get("artist_name", "")

        result_cn = best and (has_cjk(new["title"]) or has_cjk(new["artist"]))
        apply_default = bool(best and best_score >= opts.threshold and result_cn)
        method = "per-track" if best else "no-match"

        rows.append(build_row(path, old, new,
                              apply=apply_default, confidence=best_score,
                              source=used_source, external_id=ext_id, method=method))
        time.sleep(opts.delay)
    return rows
