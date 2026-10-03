"""
Scenic places niche: real licensed stock video + matching BGM.

IMPORTANT
- We do NOT scrape random websites / YouTube (copyright).
- Sources: Pexels and/or Pixabay (free commercial licence, real camera footage).
- Instagram Reels do NOT support true 8K delivery. Spec is effectively
  1080x1920 (max width ~1920). We always pick the highest-quality stock
  file available, then encode clean 1080x1920 for IG.

Secrets:
  PEXELS_API_KEY   — https://www.pexels.com/api/
  PIXABAY_API_KEY  — https://pixabay.com/api/docs/ (fallback)
  SCENIC_BGM_URL   — optional direct URL to a royalty-free MP3 you host
"""

from __future__ import annotations

import logging
import os
import random
import re
import subprocess
import tempfile
from typing import Any

import requests

log = logging.getLogger("scenic_gen")

PEXELS_VIDEOS = "https://api.pexels.com/videos/search"
PIXABAY_VIDEOS = "https://pixabay.com/api/videos/"

# Places / landscape queries — real professional stock, not AI stills
SCENIC_QUERIES = [
    "mountain landscape aerial",
    "ocean waves coastline drone",
    "forest mist morning",
    "desert sand dunes sunset",
    "northern lights aurora",
    "waterfall tropical",
    "snowy peaks aerial",
    "lavender field sunset",
    "cliff ocean europe",
    "sakura cherry blossom park",
    "swiss alps lake",
    "iceland waterfall",
    "bali rice terraces",
    "grand canyon aerial",
    "japanese garden pond",
    "tuscany hills sunrise",
    "patagonia mountains",
    "maldives beach clear water",
    "norwegian fjord",
    "sahara desert sunrise",
]

# Mood → music search terms (Pixabay) / default vibe label
VIBE_MUSIC = {
    "calm": ["ambient calm piano", "peaceful nature ambient"],
    "epic": ["cinematic ambient epic", "inspiring orchestral ambient"],
    "warm": ["warm acoustic sunset", "soft guitar ambient"],
    "mystical": [" ethereal ambient", "space ambient soft"],
}


def _vibe_for_query(q: str) -> str:
    q = q.lower()
    if any(w in q for w in ("northern", "aurora", "mist", "forest", "night")):
        return "mystical"
    if any(w in q for w in ("mountain", "alps", "canyon", "drone", "aerial", "peak")):
        return "epic"
    if any(w in q for w in ("sunset", "desert", "tuscany", "lavender", "warm")):
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
    # Prefer tall 9:16-ish, then highest pixel count
    def score(f: dict) -> tuple:
        w = int(f.get("width") or 0)
        h = int(f.get("height") or 0)
        vertical = 1 if h >= w else 0
        return (vertical, w * h, int(f.get("fps") or 0))

    ranked = sorted(files, key=score, reverse=True)
    for f in ranked:
        link = f.get("link")
        if link:
            return f
    return None


def _search_pexels(query: str) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    try:
        resp = requests.get(
            PEXELS_VIDEOS,
            headers={"Authorization": key},
            params={"query": query, "per_page": 15, "orientation": "portrait"},
            timeout=30,
        )
        if resp.status_code != 200:
            log.warning("Pexels HTTP %s: %s", resp.status_code, resp.text[:160])
            return None
        videos = resp.json().get("videos") or []
        random.shuffle(videos)
        for v in videos:
            best = _best_pexels_file(v)
            if not best:
                continue
            w, h = int(best.get("width") or 0), int(best.get("height") or 0)
            if w * h < 720 * 1280:
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
            # Prefer large / medium
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


def _pick_stock() -> dict:
    queries = list(SCENIC_QUERIES)
    random.shuffle(queries)
    last_err = None
    for q in queries[:8]:
        for searcher in (_search_pexels, _search_pixabay):
            try:
                hit = searcher(q)
                if hit:
                    log.info(
                        "Scenic stock: %s id=%s %sx%s query=%r",
                        hit["source"],
                        hit["id"],
                        hit["width"],
                        hit["height"],
                        q,
                    )
                    return hit
            except Exception as e:
                last_err = e
    raise RuntimeError(
        f"No scenic stock video found. Set PEXELS_API_KEY and/or PIXABAY_API_KEY. last={last_err}"
    )


def _fetch_bgm(vibe: str, out_mp3: str) -> bool:
    # 1) Explicit hosted royalty-free track
    url = os.environ.get("SCENIC_BGM_URL", "").strip()
    if url:
        try:
            _download(url, out_mp3)
            log.info("BGM from SCENIC_BGM_URL")
            return True
        except Exception as e:
            log.warning("SCENIC_BGM_URL failed: %s", e)

    # 2) Pixabay audio (if key supports music search)
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if key:
        terms = VIBE_MUSIC.get(vibe, VIBE_MUSIC["calm"])
        for term in terms:
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
                if not hits:
                    continue
                random.shuffle(hits)
                for h in hits:
                    audio_url = h.get("url") or h.get("previewURL")
                    # Pixabay music often has url field on full license pages;
                    # preview may be short — still usable as bed.
                    if not audio_url:
                        continue
                    if not audio_url.endswith((".mp3", ".wav", ".ogg")):
                        # try alternate keys
                        audio_url = h.get("audio") or audio_url
                    try:
                        _download(audio_url, out_mp3)
                        log.info("BGM from Pixabay music term=%r", term)
                        return True
                    except Exception:
                        continue
            except Exception as e:
                log.warning("Pixabay music search failed: %s", e)

    log.warning("No BGM available — scenic will use soft generated ambient pad")
    return False


def _ffmpeg_scenic(
    video_in: str,
    audio_in: str | None,
    video_out: str,
    max_seconds: float = 45.0,
) -> None:
    """Crop/scale to 1080x1920, high quality H.264, mix BGM."""
    # Scale to cover 1080x1920 then center crop — cinematic vertical
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
        # Soft low sine pad so IG has an audio track (very quiet)
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
    """
    Download real stock scenery + BGM, encode IG-ready vertical MP4.
    Returns dict with topic, final_path, caption bits, source meta.
    """
    os.makedirs(work_dir, exist_ok=True)
    stock = _pick_stock()
    vibe = _vibe_for_query(stock["query"])

    raw_path = os.path.join(work_dir, "scenic_raw.mp4")
    bgm_path = os.path.join(work_dir, "scenic_bgm.mp3")
    final_path = os.path.join(work_dir, "final.mp4")

    log.info("Downloading scenic video…")
    _download(stock["url"], raw_path)

    has_bgm = _fetch_bgm(vibe, bgm_path)
    max_sec = float(os.environ.get("MAX_REEL_SECONDS", "58"))
    max_sec = min(max_sec, 45.0)  # scenic clips stay punchy

    _ffmpeg_scenic(
        raw_path,
        bgm_path if has_bgm else None,
        final_path,
        max_seconds=max_sec,
    )

    place = stock["query"].strip().title()
    topic = f"Scenic escape: {place}"
    # Credit stock (good practice; Pexels asks for attribution when using API)
    credit = f"Video: {stock['photographer']} via {stock['source'].title()}"

    return {
        "topic": topic,
        "final_path": final_path,
        "source": "scenic",
        "vibe": vibe,
        "credit": credit,
        "stock": stock,
        "narration_text": f"A quiet look at {place}. {credit}.",
    }
