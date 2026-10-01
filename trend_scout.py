"""
Find trending topics inside history / science / space niches.

Sources (no paid APIs):
  - Reddit public JSON (r/science, r/space, r/history, r/astronomy, ...)
  - Optional: ScienceDaily / NASA-style headlines via simple HTTP if Reddit fails

Returns a shortlist of candidate headlines for Gemini to turn into a Reel script.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import requests

log = logging.getLogger("trend_scout")

REDDIT_SUBS = [
    "science",
    "space",
    "astronomy",
    "history",
    "AncientCivilizations",
    "Archaeology",
    "Physics",
    "EverythingScience",
]

# Soft filter: keep educational, drop pure politics/meme noise
BLOCK_WORDS = re.compile(
    r"\b(nsfw|porn|onlyfans|giveaway|crypto\s*pump|hate\s*crime)\b",
    re.I,
)

USER_AGENT = "AmbsonAI/1.0 (educational reels bot; contact: github.com/ambson1989-rgb/Ambson-ai)"


def _reddit_hot(sub: str, limit: int = 8) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{sub}/hot.json"
    try:
        resp = requests.get(
            url,
            params={"limit": limit, "raw_json": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=20,
        )
        if resp.status_code != 200:
            log.warning("Reddit r/%s status %s", sub, resp.status_code)
            return []
        children = resp.json().get("data", {}).get("children", [])
        out = []
        for child in children:
            d = child.get("data") or {}
            if d.get("stickied"):
                continue
            title = (d.get("title") or "").strip()
            if len(title) < 20 or BLOCK_WORDS.search(title):
                continue
            out.append(
                {
                    "title": title,
                    "subreddit": sub,
                    "score": int(d.get("score") or 0),
                    "url": f"https://www.reddit.com{d.get('permalink') or ''}",
                    "source": "reddit",
                }
            )
        return out
    except Exception as e:
        log.warning("Reddit r/%s failed: %s", sub, e)
        return []


def fetch_niche_trends(max_items: int = 12) -> list[dict[str, Any]]:
    """Aggregate and rank niche-trending headlines."""
    seen = set()
    items: list[dict[str, Any]] = []
    for sub in REDDIT_SUBS:
        for it in _reddit_hot(sub, limit=6):
            key = it["title"].lower()[:80]
            if key in seen:
                continue
            seen.add(key)
            items.append(it)

    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = items[:max_items]
    log.info("Trend scout found %d candidates", len(top))
    for i, it in enumerate(top[:5]):
        log.info("  #%d [%s] %s (score=%s)", i + 1, it["subreddit"], it["title"][:90], it["score"])
    return top
