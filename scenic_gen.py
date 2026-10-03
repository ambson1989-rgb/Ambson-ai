"""
Scenic / travel niche:
1) Scout trending travel locations
2) Find matching licensed stock video (Pexels / Pixabay — real camera, not scraped IG/TT)
3) Add vibe-matched BGM
4) Encode clean 1080x1920 for Instagram Reels (IG does not deliver 8K)

Secrets: PEXELS_API_KEY, PIXABAY_API_KEY, optional SCENIC_BGM_URL
"""

from __future__ import annotations

import logging
import os
import random
import subprocess
from typing import Any

import requests

from travel_scout import fetch_trending_travel

log = logging.getLogger("scenic_gen")

PEXELS_VIDEOS = "https://api.pexels.com/videos/search"
PIXABAY_VIDEOS = "https://pixabay.com/api/videos/"

VIBE_MUSIC = {
    "calm": ["ambient calm piano", "peaceful nature ambient"],
    "epic": ["cinematic ambient epic", "inspiring orchestral ambient"],
    "warm": ["warm acoustic sunset", "soft guitar ambient"],
    "mystical": ["ethereal ambient", "space ambient soft"],
}


def _vibe_for_query(q: str) -> str:
    q = (q or "").lower()
    if any(w in q for w in ("northern", "aurora", "mist", "night", "cappadocia", "balloon")):
        return "mystical"
    if any(w in q for w in ("mountain", "alps", "canyon", "drone", "aerial", "peak", "fjord", "himalaya")):
        return "epic"
    if any(w in q for w in ("sunset", "desert", "tuscany", "warm", "bali", "maldives", "beach")):
        return "warm"
    return "calm"


def _download(url: str, path: str, timeout: int = 180) -> None:
    with requests.get(url, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    f.write(chunk)


def _best_pexels_file(video: dict) -> dict | None:
    files = video.get("video_files") or []
    if not files:
        return None

    def score(f: dict) -> tuple:
        w = int(f.get("width") or 0)
        h = int(f.get("height") or 0)
        vertical = 1 if h >= w else 0
        return (vertical, w * h, int(f.get("fps") or 0))

    ranked = sorted(files, key=score, reverse=True)
    for f in ranked:
        if f.get("link"):
            return f
    return None


def _search_pexels(query: str) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    try:
        # Try portrait first, then any orientation (travel stock is often landscape drone)
        for orientation in ("portrait", None):
            params: dict[str, Any] = {"query": query, "per_page": 15}
            if orientation:
                params["orientation"] = orientation
            resp = requests.get(
                PEXELS_VIDEOS,
                headers={"Authorization": key},
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                log.warning("Pexels HTTP %s", resp.status_code)
                continue
            videos = resp.json().get("videos") or []
            random.shuffle(videos)
            for v in videos:
                best = _best_pexels_file(v)
                if not best:
                    continue
                w, h = int(best.get("width") or 0), int(best.get("height") or 0)
                if w * h < 640 * 360:
                    continue
                return {
                    "source": "pexels",
                    "id": v.get("id"),
                    "url": best["link"],
                    "width": w,
                    "height": h,
                    "duration": int(v.get("duration") or 0),
                    "photographer": (v.get("user") or {}).get("name") or "Pexels",
                    "query": query,
                }
    except Exception as e:
        log.warning("Pexels search failed: %s", e)
    return None


def _search_pixabay(query: str) -> dict | None:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return None
    try:
        resp = requests.get(
            PIXABAY_VIDEOS,
            params={
                "key": key,
                "q": query,
                "per_page": 20,
                "video_type": "film",
                "safesearch": "true",
            },
            timeout=30,
        )
        if resp.status_code != 200:
            log.warning("Pixabay HTTP %s", resp.status_code)
            return None
        hits = resp.json().get("hits") or []
        random.shuffle(hits)
        for h in hits:
            videos = h.get("videos") or {}
            for quality in ("large", "medium", "small", "tiny"):
                vf = videos.get(quality) or {}
                url = vf.get("url")
                if not url:
                    continue
                w = int(vf.get("width") or 0)
                ht = int(vf.get("height") or 0)
                if w * ht < 640 * 360:
                    continue
                return {
                    "source": "pixabay",
                    "id": h.get("id"),
                    "url": url,
                    "width": w,
                    "height": ht,
                    "duration": int(h.get("duration") or 0),
                    "photographer": h.get("user") or "Pixabay",
                    "query": query,
                }
    except Exception as e:
        log.warning("Pixabay search failed: %s", e)
    return None


def _pick_stock_for_trends() -> tuple[dict, dict]:
    """
    Prefer trending travel locations; try stock search per location.
    Returns (stock_meta, trend_meta).
    """
    trends = fetch_trending_travel(max_items=14)
    random.shuffle(trends)  # avoid always same top headline
    # Prefer higher score but still shuffle within top
    trends = sorted(trends, key=lambda x: x.get("score", 0), reverse=True)

    last_err = None
    for t in trends:
        query = t["query"]
        log.info("Trying stock for trending place %s → %r", t["place"], query)
        for searcher in (_search_pexels, _search_pixabay):
            try:
                hit = searcher(query)
                if hit:
                    # Also try simpler place name if needed — already have hit
                    log.info(
                        "Matched %s via %s id=%s %sx%s",
                        t["place"],
                        hit["source"],
                        hit["id"],
                        hit["width"],
                        hit["height"],
                    )
                    return hit, t
            except Exception as e:
                last_err = e
        # Fallback: search just the place name
        simple = f"{t['place']} travel landscape"
        for searcher in (_search_pexels, _search_pixabay):
            try:
                hit = searcher(simple)
                if hit:
                    log.info("Matched %s (simple query) via %s", t["place"], hit["source"])
                    return hit, t
            except Exception as e:
                last_err = e

    raise RuntimeError(
        f"No stock video for trending travel locations. "
        f"Set PEXELS_API_KEY and/or PIXABAY_API_KEY. last={last_err}"
    )


def _fetch_bgm(vibe: str, out_mp3: str) -> bool:
    url = os.environ.get("SCENIC_BGM_URL", "").strip()
    if url:
        try:
            _download(url, out_mp3)
            log.info("BGM from SCENIC_BGM_URL")
            return True
        except Exception as e:
            log.warning("SCENIC_BGM_URL failed: %s", e)

    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if key:
        for term in VIBE_MUSIC.get(vibe, VIBE_MUSIC["calm"]):
            try:
                resp = requests.get(
                    "https://pixabay.com/api/",
                    params={
                        "key": key,
                        "q": term,
                        "media_type": "music",
                        "per_page": 10,
                        "safesearch": "true",
                    },
                    timeout=20,
                )
                if resp.status_code != 200:
                    continue
                hits = resp.json().get("hits") or []
                random.shuffle(hits)
                for h in hits:
                    audio_url = h.get("url") or h.get("previewURL")
                    if not audio_url:
                        continue
                    try:
                        _download(audio_url, out_mp3)
                        log.info("BGM Pixabay term=%r", term)
                        return True
                    except Exception:
                        continue
            except Exception as e:
                log.warning("Pixabay music failed: %s", e)

    log.warning("No BGM — quiet pad fallback")
    return False


def _ffmpeg_scenic(
    video_in: str,
    audio_in: str | None,
    video_out: str,
    max_seconds: float = 45.0,
) -> None:
    vf = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "eq=contrast=1.05:saturation=1.08:brightness=0.02,"
        "unsharp=3:3:0.4"
    )
    vf = "".join(vf)

    if audio_in and os.path.isfile(audio_in):
        cmd = [
            "ffmpeg", "-y",
            "-i", video_in,
            "-i", audio_in,
            "-t", str(max_seconds),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            video_out,
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-i", video_in,
            "-f", "lavfi", "-i", "sine=frequency=110:sample_rate=44100",
            "-t", str(max_seconds),
            "-vf", vf,
            "-c:v", "libx264", "-preset", "slow", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-c:a", "aac", "-b:a", "128k",
            "-filter_complex", "[1:a]volume=0.04[a]",
            "-map", "0:v", "-map", "[a]",
            "-shortest",
            "-movflags", "+faststart",
            video_out,
        ]

    log.info("ffmpeg scenic encode…")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg scenic failed: {proc.stderr[-800:]}")


def build_scenic_reel(work_dir: str) -> dict[str, Any]:
    os.makedirs(work_dir, exist_ok=True)
    stock, trend = _pick_stock_for_trends()
    vibe = _vibe_for_query(stock["query"] + " " + trend.get("place", ""))

    raw_path = os.path.join(work_dir, "scenic_raw.mp4")
    bgm_path = os.path.join(work_dir, "scenic_bgm.mp3")
    final_path = os.path.join(work_dir, "final.mp4")

    log.info("Downloading matching travel stock for %s…", trend.get("place"))
    _download(stock["url"], raw_path)

    has_bgm = _fetch_bgm(vibe, bgm_path)
    max_sec = min(float(os.environ.get("MAX_REEL_SECONDS", "58")), 45.0)
    _ffmpeg_scenic(raw_path, bgm_path if has_bgm else None, final_path, max_seconds=max_sec)

    place = trend.get("place") or "Wanderlust"
    topic = f"Trending escape: {place}"
    if trend.get("headline") and trend.get("source") != "evergreen":
        # Keep caption topic short; headline informs engagement caption body optionally
        pass
    credit = f"Video: {stock['photographer']} via {stock['source'].title()}"

    return {
        "topic": topic,
        "final_path": final_path,
        "source": "scenic",
        "vibe": vibe,
        "credit": credit,
        "stock": stock,
        "trend": trend,
        "narration_text": (
            f"Trending travel destination look: {place}. "
            f"Cinematic location footage. {credit}."
        ),
    }
