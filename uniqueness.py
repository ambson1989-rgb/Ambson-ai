"""
Strict anti-repeat for every Reel (facts + scenic).

Tracks:
  - used_topics (titles)
  - used_stock_ids (pexels/pixabay video ids)
  - used_places (scenic destinations)
  - used_fingerprints (normalized narration snippets)

Matching is aggressive: keyword overlap, substring, shared distinctive tokens.
"""

from __future__ import annotations

import json
import logging
import os
import re

log = logging.getLogger("uniqueness")

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")
USED_TOPICS_MAX = int(os.environ.get("USED_TOPICS_MAX", "800"))
USED_IDS_MAX = int(os.environ.get("USED_STOCK_IDS_MAX", "400"))

# Always-block clusters (even if not in state yet)
HARD_BLOCK_PHRASES = (
    "wardenclyffe", "tesla tower", "antikythera", "pigeon", "cosmic microwave",
    "stick insect", "magnetar", "superfluid quantum", "tulip mania",
    "orionid", "voyager 1 golden", "holei", "hōlei", "lunar cave",
    "solar hydrogen", "platinum surface",
)

STOP = {
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "its", "it",
    "may", "this", "that", "with", "from", "by", "at", "is", "are", "was",
    "how", "why", "what", "when", "new", "old", "year", "years", "old",
}


def _load() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save(updates: dict) -> None:
    state = _load()
    state.update(updates)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def normalize(text: str) -> str:
    t = (text or "").lower()
    t = t.replace("ē", "e").replace("ō", "o").replace("ā", "a")
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:160]


def tokens(text: str) -> set[str]:
    return {w for w in normalize(text).split() if len(w) > 2 and w not in STOP}


def fingerprint(*parts: str) -> str:
    joined = " ".join(p for p in parts if p)
    toks = sorted(tokens(joined))
    return " ".join(toks[:24])


def _overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / max(1, min(len(a), len(b)))


def is_duplicate_topic(topic: str) -> bool:
    """True if this topic is too similar to anything already used."""
    norm = normalize(topic)
    if not norm or len(norm) < 6:
        return True  # reject empty/tiny

    for phrase in HARD_BLOCK_PHRASES:
        if phrase in norm:
            log.warning("Hard-blocked phrase %r in %r", phrase, topic[:80])
            return True

    state = _load()
    used = [str(x) for x in (state.get("used_topics") or [])]
    used_fp = [str(x) for x in (state.get("used_fingerprints") or [])]
    used_places = [normalize(str(x)) for x in (state.get("used_places") or [])]

    topic_toks = tokens(topic)

    for u in used:
        un = normalize(u)
        if not un:
            continue
        # exact / substring
        if norm == un or norm in un or un in norm:
            log.warning("Duplicate substring vs used: %r ~ %r", topic[:60], u[:60])
            return True
        # high token overlap
        ut = tokens(u)
        ratio = _overlap_ratio(topic_toks, ut)
        if ratio >= 0.55 and len(topic_toks & ut) >= 2:
            log.warning(
                "Duplicate overlap %.0f%% vs used: %r ~ %r",
                ratio * 100,
                topic[:50],
                u[:50],
            )
            return True
        # shared distinctive long token
        shared = {t for t in (topic_toks & ut) if len(t) >= 6}
        if len(shared) >= 2:
            log.warning("Duplicate keywords %s: %r", shared, topic[:50])
            return True

    fp = fingerprint(topic)
    if fp and fp in used_fp:
        log.warning("Duplicate fingerprint: %r", fp[:80])
        return True

    # Scenic place already used
    for p in used_places:
        if p and (p in norm or norm in p):
            log.warning("Duplicate place %r in topic %r", p, topic[:50])
            return True

    return False


def is_stock_used(source: str, stock_id) -> bool:
    if stock_id is None:
        return False
    key = f"{source}:{stock_id}".lower()
    state = _load()
    used = {str(x).lower() for x in (state.get("used_stock_ids") or [])}
    if key in used:
        log.warning("Stock id already used: %s", key)
        return True
    return False


def is_place_used(place: str) -> bool:
    p = normalize(place)
    if not p:
        return False
    state = _load()
    for u in state.get("used_places") or []:
        un = normalize(str(u))
        if p == un or p in un or un in p:
            log.warning("Place already used: %r ~ %r", place, u)
            return True
    # also against used_topics text
    if is_duplicate_topic(f"Trending escape: {place}"):
        return True
    return False


def record_post(
    topic: str,
    *,
    place: str | None = None,
    stock_source: str | None = None,
    stock_id=None,
    fingerprint_parts: list[str] | None = None,
) -> None:
    state = _load()

    used = list(state.get("used_topics") or [])
    if topic and topic not in used:
        used.append(topic)
    used = used[-USED_TOPICS_MAX:]

    fps = list(state.get("used_fingerprints") or [])
    fp = fingerprint(topic, *(fingerprint_parts or []))
    if fp and fp not in fps:
        fps.append(fp)
    fps = fps[-USED_TOPICS_MAX:]

    places = list(state.get("used_places") or [])
    if place:
        pl = place.strip()
        if pl and normalize(pl) not in {normalize(x) for x in places}:
            places.append(pl)
    places = places[-USED_IDS_MAX:]

    ids = list(state.get("used_stock_ids") or [])
    if stock_source is not None and stock_id is not None:
        key = f"{stock_source}:{stock_id}"
        if key.lower() not in {x.lower() for x in ids}:
            ids.append(key)
    ids = ids[-USED_IDS_MAX:]

    _save(
        {
            "used_topics": used,
            "used_fingerprints": fps,
            "used_places": places,
            "used_stock_ids": ids,
        }
    )
    log.info(
        "Recorded unique post: topic=%r place=%r stock=%s:%s",
        topic[:60],
        place,
        stock_source,
        stock_id,
    )


# Back-compat aliases used by older imports
def is_topic_used(topic: str) -> bool:
    return is_duplicate_topic(topic)


def record_used_topic(topic: str) -> None:
    record_post(topic)
