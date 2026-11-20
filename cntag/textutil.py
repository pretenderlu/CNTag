"""Text helpers: CJK detection, transliteration-aware name matching."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from pypinyin import lazy_pinyin
from zhconv import convert as _zh_convert

CJK_RE = re.compile(r"[一-鿿㐀-䶿豈-﫿]")


def has_cjk(s: str) -> bool:
    return bool(s and CJK_RE.search(s))


def parse_int(v) -> int | None:
    if v is None:
        return None
    s = str(v).split("/")[0].strip()
    try:
        return int(s)
    except ValueError:
        return None


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, (a or "").lower().strip(), (b or "").lower().strip()).ratio()


def to_zh_cn(text: str, simplified: bool) -> str:
    """Convert Traditional → Simplified Chinese when enabled."""
    if not text or not simplified:
        return text or ""
    return _zh_convert(text, "zh-cn")


def normalize_text(s: str) -> str:
    """Lowercase and strip non-alphanumeric. Used for transliteration matching."""
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def to_pinyin(s: str) -> str:
    """Chinese text → lowercase pinyin string (no separators).
    Empty string if input has no Chinese."""
    if not s:
        return ""
    try:
        return normalize_text(" ".join(lazy_pinyin(s)))
    except Exception:
        return ""


_ARTIST_SPLIT_RE = re.compile(r"\s*(?:/|、|&|,|，|;|；|\bfeat\.?\b|\bfeaturing\b)\s*", re.I)
_ARTIST_STRIP_RE = re.compile(r"[^0-9a-zA-Z一-鿿]+")


def _artist_norm(s: str) -> str:
    return _ARTIST_STRIP_RE.sub("", to_zh_cn(s or "", True).casefold())


def artists_match(a: str, b: str) -> bool | None:
    """Do two artist names refer to the same artist?

    Returns None when a judgment can't be made: either side is empty, or
    exactly one side is CJK (e.g. 'Jay Chou' vs '周杰倫' — same person, but
    we can't tell without transliteration). Otherwise compares names after
    Traditional→Simplified conversion and punctuation stripping: equal or
    contained → True; any matching part after splitting on / 、 & , feat. →
    True; a pinyin-aware name_match_score >= 0.9 → True; else False."""
    a, b = (a or "").strip(), (b or "").strip()
    if not a or not b:
        return None
    if has_cjk(a) != has_cjk(b):
        return None
    na, nb = _artist_norm(a), _artist_norm(b)
    if not na or not nb:
        return None
    if na == nb or na in nb or nb in na:
        return True
    parts_a = {p for p in (_artist_norm(x) for x in _ARTIST_SPLIT_RE.split(a)) if p}
    parts_b = {p for p in (_artist_norm(x) for x in _ARTIST_SPLIT_RE.split(b)) if p}
    if parts_a & parts_b:
        return True
    return name_match_score(a, b) >= 0.9


def name_match_score(user_query: str, candidate_name: str) -> float:
    """Score similarity between a user query (English / pinyin / Chinese)
    and a candidate name (typically Chinese). Range: 0.0–1.0.

    Compares against the candidate's normalized form AND its pinyin form,
    so 'Dan Dan You Qing' matches '淡淡幽情'."""
    if not user_query or not candidate_name:
        return 0.0
    user_norm = normalize_text(user_query)
    cand_norm = normalize_text(candidate_name)
    cand_pinyin = to_pinyin(candidate_name)

    if user_norm and cand_pinyin:
        if user_norm == cand_pinyin:
            return 1.0
        if user_norm in cand_pinyin or cand_pinyin in user_norm:
            return 0.92
    if user_norm and cand_norm:
        if user_norm == cand_norm:
            return 1.0
        if user_norm in cand_norm or cand_norm in user_norm:
            return 0.85
    if user_norm and cand_pinyin:
        return SequenceMatcher(None, user_norm, cand_pinyin).ratio()
    return 0.0
