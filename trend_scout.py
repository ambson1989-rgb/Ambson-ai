"""
Find trending topics in history / science / space niches.

Primary: public RSS feeds (work from GitHub Actions).
Fallback: Reddit JSON (often 403 from cloud IPs).
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any
from email.utils import parsedate_to_datetime

import requests

log = logging.getLogger("trend_scout")

USER_AGENT = (
    "AmbsonAI/1.0 (+https://github.com/ambson1989-rgb/Ambson-ai; educational reels)"
)

RSS_FEEDS = [
    ("ScienceDaily", "https://www.sciencedaily.com/rss/all.xml"),
    ("NASA", "https://www.nasa.gov/rss/dyn/breaking_news.rss"),
    ("BBC Science", "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml"),
    ("Phys.org", "https://phys.org/rss-feed/"),
    ("Space.com", "https://www.space.com/feeds/all"),
    ("Smithsonian", "https://www.smithsonianmag.com/rss/science-nature/"),
    ("LiveScience", "https://www.livescience.com/feeds/all"),
]

REDDIT_SUBS = [
    "science",
    "space",
    "astronomy",
    "history",
    "Archaeology",
    "Physics",
]

BLOCK_WORDS = re.compile(
    r"\b(nsfw|porn|onlyfans|giveaway|crypto\s*pump|hate\s*crime)\b",
    re.I,
)


def _rss_items(name: str, url: str, limit: int = 8) -> list[dict[str, Any]]:
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"},
            timeout=20,
        )
        if resp.status_code != 200:
            log.warning("RSS %s status %s", name, resp.status_code)
            return []
        root = ET.fromstring(resp.content)
        # RSS 2.0 channel/item or Atom entry
        items = root.findall(".//item")
        if not items:
            # Atom
            ns = {"a": "http://www.w3.org/2005/Atom"}
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//entry")
            out = []
            for e in entries[:limit]:
                title_el = e.find("{http://www.w3.org/2005/Atom}title")
                if title_el is None:
                    title_el = e.find("title")
                title = (title_el.text or "").strip() if title_el is not None else ""
                if len(title) < 20 or BLOCK_WORDS.search(title):
                    continue
                out.append({
                    "title": title,
                    "subreddit": name,
                    "score": 50,
                    "url": "",
                    "source": "rss",
                })
            return out

        out = []
        for item in items[:limit]:
            title_el = item.find("title")
            title = (title_el.text or "").strip() if title_el is not None else ""
            if len(title) < 20 or BLOCK_WORDS.search(title):
                continue
            # Prefer fresher items slightly
            score = 40
            pub = item.find("pubDate")
            if pub is not None and pub.text:
                try:
                    parsedate_to_datetime(pub.text)
                    score = 60
                except Exception:
                    pass
            out.append({
                "title": title,
                "subreddit": name,
                "score": score,
                "url": "",
                "source": "rss",
            })
        return out
    except Exception as e:
        log.warning("RSS %s failed: %s", name, e)
        return []


def _reddit_hot(sub: str, limit: int = 6) -> list[dict[str, Any]]:
    url = f"https://www.reddit.com/r/{sub}/hot.json"
    try:
        resp = requests.get(
            url,
            params={"limit": limit, "raw_json": 1},
            headers={"User-Agent": USER_AGENT},
            timeout=15,
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
            out.append({
                "title": title,
                "subreddit": sub,
                "score": int(d.get("score") or 0),
                "url": f"https://www.reddit.com{d.get('permalink') or ''}",
                "source": "reddit",
            })
        return out
    except Exception as e:
        log.warning("Reddit r/%s failed: %s", sub, e)
        return []


def fetch_niche_trends(max_items: int = 15) -> list[dict[str, Any]]:
    seen = set()
    items: list[dict[str, Any]] = []

    for name, url in RSS_FEEDS:
        for it in _rss_items(name, url, limit=6):
            key = it["title"].lower()[:90]
            if key in seen:
                continue
            seen.add(key)
            items.append(it)

    if len(items) < 5:
        for sub in REDDIT_SUBS:
            for it in _reddit_hot(sub):
                key = it["title"].lower()[:90]
                if key in seen:
                    continue
                seen.add(key)
                items.append(it)

    items.sort(key=lambda x: x.get("score", 0), reverse=True)
    top = items[:max_items]
    log.info("Trend scout found %d candidates", len(top))
    for i, it in enumerate(top[:5]):
        log.info("  #%d [%s] %s", i + 1, it["subreddit"], it["title"][:90])
    return top
