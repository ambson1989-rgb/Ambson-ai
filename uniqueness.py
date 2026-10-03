"""
Strict anti-repeat for every Reel.

- Permanent bans for known repeats (Tesla, Antikythera, etc.)
- Fuzzy match on used_topics + fingerprints
- Scan topic AND full narration / image prompts
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

log = logging.getLogger("uniqueness")

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")
USED_TOPICS_MAX = int(os.environ.get("USED_TOPICS_MAX", "800"))
USED_IDS_MAX = int(os.environ.get("USED_STOCK_IDS_MAX", "500"))

# Permanent bans — single tokens OK ("tesla" is only 5 letters; must list explicitly)
HARD_BLOCK_PHRASES = (
    # Tesla family — NEVER again
    "tesla", "wardenclyffe", "wardenclyfe", "j.p. morgan", "jp morgan",
    "wireless power tower", "tesla tower", "nikola tesla",
    # Other confirmed past posts
    "antikythera", "pigeon", "cosmic microwave", "stick insect", "magnetar",
    "superfluid", "tulip mania", "orionid", "voyager", "holei", "hōlei",
    "lunar cave", "solar hydrogen", "platinum surface", "ancient chocolate",
    "mississippi chocolate", "swiss glacier", "sea arch", "helium superfluid",
    "roman concrete", "stone age invisible",
)

STOP = {
    "the", "a", "an", "and", "or", "of", "in", "on", "to", "for", "its", "it",
    "may", "this", "that", "with", "from", "by", "at", "is", "are", "was",
    "how", "why", "what", "when", "new", "old", "year", "years", "east",
    "west", "boosts", "threatens", "reveal", "birth", "origin", "secret",
    "modern", "that", "outlasts",
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
    return t[:400]


def tokens(text: str) -> set[str]:
    return {w for w in normalize(text).split() if len(w) > 2 and w not in STOP}


def fingerprint(*parts: str) -> str:
    joined = " ".join(p for p in parts if p)
    toks = sorted(tokens(joined))
    return " ".join(toks[:24])


def _overlap_ratio(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(1, min(len(a), len(b)))


def _dynamic_hard_blocks() -> set[str]:
    blocks = set(HARD_BLOCK_PHRASES)
    for u in _load().get("used_topics") or []:
        n = normalize(str(u))
        words = [w for w in n.split() if w not in STOP and len(w) >= 5]
        for w in words:
            blocks.add(w)
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i+1]}"
            if len(bigram) >= 8:
                blocks.add(bigram)
    return blocks


def _blocked_by_phrase(norm: str) -> str | None:
    for phrase in _dynamic_hard_blocks():
        if not phrase:
            continue
        # word-boundary-ish: phrase as substring is enough for multi-word;
        # for single tokens require whole word match when short
        if " " in phrase:
            if phrase in norm:
                return phrase
        else:
            if re.search(rf"\b{re.escape(phrase)}\b", norm):
                return phrase
    return None


def is_duplicate_topic(topic: str) -> bool:
    norm = normalize(topic)
    if not norm or len(norm) < 6:
        return True

    hit = _blocked_by_phrase(norm)
    if hit:
        log.warning("Hard-blocked %r in topic %r", hit, topic[:80])
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
        if norm == un or norm in un or un in norm:
            log.warning("Duplicate substring: %r ~ %r", topic[:60], u[:60])
            return True
        ut = tokens(u)
        ratio = _overlap_ratio(topic_toks, ut)
        if ratio >= 0.40 and len(topic_toks & ut) >= 2:
            log.warning("Duplicate overlap %.0f%%: %r ~ %r", ratio * 100, topic[:50], u[:50])
            return True
        shared = {t for t in (topic_toks & ut) if len(t) >= 5}
        if len(shared) >= 2:
            log.warning("Duplicate keywords %s: %r", shared, topic[:50])
            return True

    fp = fingerprint(topic)
    if fp and fp in used_fp:
        log.warning("Duplicate fingerprint: %r", fp[:80])
        return True

    for p in used_places:
        if p and (p in norm or norm in p):
            log.warning("Duplicate place %r in %r", p, topic[:50])
            return True

    return False


def is_duplicate_script(topic: str, narrations: list[str] | None = None, prompts: list[str] | None = None) -> bool:
    """Reject if topic OR any narration/prompt hits bans / past content."""
    if is_duplicate_topic(topic):
        return True
    blobs = [topic]
    blobs.extend(narrations or [])
    blobs.extend(prompts or [])
    joined = " ".join(blobs)
    norm = normalize(joined)
    hit = _blocked_by_phrase(norm)
    if hit:
        log.warning("Hard-blocked %r in full script text", hit)
        return True
    # Also compare fingerprint of narrations against used fingerprints
    fp = fingerprint(*blobs)
    used_fp = [str(x) for x in (_load().get("used_fingerprints") or [])]
    if fp and fp in used_fp:
        log.warning("Full-script fingerprint collision")
        return True
    return False


def is_stock_used(source: str, stock_id) -> bool:
    if stock_id is None:
        return False
    key = f"{source}:{stock_id}".lower()
    used = {str(x).lower() for x in (_load().get("used_stock_ids") or [])}
    if key in used:
        log.warning("Stock id already used: %s", key)
        return True
    return False


def is_place_used(place: str) -> bool:
    p = normalize(place)
    if not p:
        return False
    for u in _load().get("used_places") or []:
        un = normalize(str(u))
        if p == un or p in un or un in p:
            return True
    if is_duplicate_topic(f"Trending escape: {place}"):
        return True
    return False


def record_post(
    topic: str,
    *,
    place: str | None = None,
    stock_source: str | None = None,
    stock_id=None,
    stock_ids: list[str] | None = None,
    fingerprint_parts: list[str] | None = None,
) -> None:
    state = _load()

    used = list(state.get("used_topics") or [])
    if topic and topic not in used:
        used.append(topic)
    # Always keep Tesla ban entry present
    for forced in (
        "Tesla's Wardenclyffe Tower and why J.P. Morgan pulled funding",
        "tesla wardenclyffe BAN",
    ):
        if forced not in used:
            used.append(forced)
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
    existing = {x.lower() for x in ids}

    def _add_id(key: str) -> None:
        if key and key.lower() not in existing:
            ids.append(key)
            existing.add(key.lower())

    if stock_source is not None and stock_id is not None:
        _add_id(f"{stock_source}:{stock_id}")
    for s in stock_ids or []:
        _add_id(str(s))
    ids = ids[-USED_IDS_MAX:]

    _save(
        {
            "used_topics": used,
            "used_fingerprints": fps,
            "used_places": places,
            "used_stock_ids": ids,
            "last_run_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    )
    log.info("Recorded unique post: topic=%r", topic[:60])


def is_topic_used(topic: str) -> bool:
    return is_duplicate_topic(topic)


def record_used_topic(topic: str) -> None:
    record_post(topic)
