"""
Fetch short licensed stock VIDEO clips for motion-heavy beats
(ocean waves, waterfalls, clouds, fire, space, etc.).

Uses PEXELS_API_KEY / PIXABAY_API_KEY — same as scenic niche.
Falls back to None so pipeline can use AI still + Ken Burns.
"""

from __future__ import annotations

import logging
import os
import random
import re
from typing import Any

import requests

log = logging.getLogger("stock_video")

PEXELS_VIDEOS = "https://api.pexels.com/videos/search"
PIXABAY_VIDEOS = "https://pixabay.com/api/videos/"

# Prompts that benefit from real moving footage
MOTION_RE = re.compile(
    r"\b("
    r"ocean|sea|wave|waves|water|waterfall|river|lake|rain|storm|"
    r"cloud|clouds|sky|wind|fire|lava|flame|smoke|"
    r"snow|blizzard|aurora|northern lights|"
    r"drone|aerial|timelapse|time-lapse|"
    r"stars|galaxy|nebula|planet|orbit|"
    r"crowd|traffic|city night|neon"
    r")\b",
    re.I,
)

# Map prompt keywords → stock search query (cinematic real footage)
QUERY_MAP = [
    (r"ocean|sea|wave", "ocean waves aerial cinematic"),
    (r"waterfall", "waterfall nature cinematic"),
    (r"river|lake", "river flowing water nature"),
    (r"rain|storm", "rain storm clouds cinematic"),
    (r"cloud", "moving clouds timelapse sky"),
    (r"fire|lava|flame", "fire flames cinematic"),
    (r"snow|blizzard", "snow falling mountain wind"),
    (r"aurora|northern", "northern lights aurora real"),
    (r"galaxy|nebula|stars|space|orbit|planet", "space stars galaxy cinematic"),
    (r"drone|aerial", "aerial landscape drone cinematic"),
    (r"city|neon|traffic", "city night timelapse neon"),
]


def wants_motion_video(prompt: str) -> bool:
    return bool(MOTION_RE.search(prompt or ""))


def _search_query(prompt: str) -> str:
    p = prompt or ""
    for pattern, q in QUERY_MAP:
        if re.search(pattern, p, re.I):
            return q
    # Generic from first few words
    words = re.findall(r"[a-zA-Z]+", p)[:6]
    return " ".join(words) + " cinematic video" if words else "nature cinematic"


def _best_pexels_file(video: dict) -> dict | None:
    files = video.get("video_files") or []
    if not files:
        return None

    def score(f: dict) -> tuple:
        w = int(f.get("width") or 0)
        h = int(f.get("height") or 0)
        vertical = 1 if h >= w else 0
        return (vertical, w * h)

    for f in sorted(files, key=score, reverse=True):
        if f.get("link"):
            return f
    return None


def _pexels(query: str) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    try:
        for orientation in ("portrait", None):
            params: dict[str, Any] = {"query": query, "per_page": 12}
            if orientation:
                params["orientation"] = orientation
            resp = requests.get(
                PEXELS_VIDEOS,
                headers={"Authorization": key},
                params=params,
                timeout=25,
            )
            if resp.status_code != 200:
                continue
            videos = resp.json().get("videos") or []
            random.shuffle(videos)
            for v in videos:
                best = _best_pexels_file(v)
                if not best:
                    continue
                w = int(best.get("width") or 0)
                h = int(best.get("height") or 0)
                if w * h < 480 * 480:
                    continue
                return {
                    "url": best["link"],
                    "width": w,
                    "height": h,
                    "source": "pexels",
                    "id": v.get("id"),
                    "query": query,
                }
    except Exception as e:
        log.warning("Pexels motion search: %s", e)
    return None


def _pixabay(query: str) -> dict | None:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return None
    try:
        resp = requests.get(
            PIXABAY_VIDEOS,
            params={
                "key": key,
                "q": query,
                "per_page": 15,
                "video_type": "film",
                "safesearch": "true",
            },
            timeout=25,
        )
        if resp.status_code != 200:
            return None
        hits = resp.json().get("hits") or []
        random.shuffle(hits)
        for h in hits:
            videos = h.get("videos") or {}
            for quality in ("large", "medium", "small"):
                vf = videos.get(quality) or {}
                url = vf.get("url")
                if not url:
                    continue
                return {
                    "url": url,
                    "width": int(vf.get("width") or 0),
                    "height": int(vf.get("height") or 0),
                    "source": "pixabay",
                    "id": h.get("id"),
                    "query": query,
                }
    except Exception as e:
        log.warning("Pixabay motion search: %s", e)
    return None


def find_motion_clip(image_prompt: str) -> dict | None:
    """Return stock video meta if prompt needs real motion; else None."""
    if not wants_motion_video(image_prompt):
        return None
    if not (
        os.environ.get("PEXELS_API_KEY", "").strip()
        or os.environ.get("PIXABAY_API_KEY", "").strip()
    ):
        log.info("No Pexels/Pixabay key — skip motion stock for this beat")
        return None

    query = _search_query(image_prompt)
    log.info("Motion stock search: %r", query)
    for searcher in (_pexels, _pixabay):
        hit = searcher(query)
        if hit:
            log.info(
                "Motion clip: %s id=%s %sx%s",
                hit["source"],
                hit["id"],
                hit["width"],
                hit["height"],
            )
            return hit
    log.warning("No motion stock found for %r", query)
    return None


def download_clip(url: str, path: str) -> str:
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    f.write(chunk)
    return path
