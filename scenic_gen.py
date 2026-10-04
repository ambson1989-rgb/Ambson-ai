"""
Pure scenic / travel Reel:
  - looped stock video (target ~40s, not a 3s clip)
  - vibe-matched background music (never silent)
  - short narration ONLY from source headlines (no invented facts)
  - on-screen captions for every spoken line
  - end CTA: stay tuned + follow
"""

from __future__ import annotations

import logging
import os
import random
import re
import subprocess
from typing import Any

import requests

from travel_scout import fetch_trending_travel
from uniqueness import is_place_used, is_stock_used
from voice_gen import generate_narration
from cta import next_cta_beat
from video_assemble import build_beat_clip, concat_clips
from image_gen import generate_image

log = logging.getLogger("scenic_gen")

PEXELS_VIDEOS = "https://api.pexels.com/videos/search"
PIXABAY_VIDEOS = "https://pixabay.com/api/videos/"

# Public CC-friendly preview tracks by vibe (Mixkit free music previews)
VIBE_BGM_URLS = {
    "calm": [
        "https://assets.mixkit.co/music/preview/mixkit-serene-view-443.mp3",
        "https://assets.mixkit.co/music/preview/mixkit-a-very-happy-christmas-897.mp3",
        "https://assets.mixkit.co/music/preview/mixkit-dreaming-big-31.mp3",
    ],
    "epic": [
        "https://assets.mixkit.co/music/preview/mixkit-tech-house-vibes-130.mp3",
        "https://assets.mixkit.co/music/preview/mixkit-driving-ambition-32.mp3",
        "https://assets.mixkit.co/music/preview/mixkit-hazy-after-hours-132.mp3",
    ],
    "warm": [
        "https://assets.mixkit.co/music/preview/mixkit-sunny-day-1122.mp3",
        "https://assets.mixkit.co/music/preview/mixkit-island-beat-500.mp3",
        "https://assets.mixkit.co/music/preview/mixkit-lifestyle-540.mp3",
    ],
    "mystical": [
        "https://assets.mixkit.co/music/preview/mixkit-spirit-in-the-woods-139.mp3",
        "https://assets.mixkit.co/music/preview/mixkit-deep-urban-114.mp3",
        "https://assets.mixkit.co/music/preview/mixkit-sleepy-cat-135.mp3",
    ],
}

TARGET_SECONDS = float(os.environ.get("SCENIC_TARGET_SECONDS", "42"))
MIN_SECONDS = 28.0


def _vibe_for_query(q: str) -> str:
    q = (q or "").lower()
    if any(w in q for w in ("northern", "aurora", "mist", "night", "cappadocia", "balloon", "kyoto", "temple")):
        return "mystical"
    if any(w in q for w in ("mountain", "alps", "canyon", "drone", "aerial", "peak", "fjord", "himalaya", "ladakh")):
        return "epic"
    if any(w in q for w in ("sunset", "desert", "tuscany", "warm", "bali", "maldives", "beach", "santorini")):
        return "warm"
    return "calm"


def _download(url: str, path: str, timeout: int = 180) -> None:
    headers = {"User-Agent": "AmbsonScenic/1.0"}
    with requests.get(url, stream=True, timeout=timeout, headers=headers) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk:
                    f.write(chunk)


def _probe_duration(path: str) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", path,
        ],
        text=True,
    ).strip()
    return float(out)


def _run_ffmpeg(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {(proc.stderr or '')[-900:]}")


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


def _search_pexels(query: str) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    try:
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
                continue
            videos = resp.json().get("videos") or []
            random.shuffle(videos)
            for v in videos:
                best = _best_pexels_file(v)
                if not best:
                    continue
                sid = v.get("id")
                if is_stock_used("pexels", sid):
                    continue
                w, h = int(best.get("width") or 0), int(best.get("height") or 0)
                if w * h < 720 * 720:
                    continue
                return {
                    "source": "pexels",
                    "id": sid,
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
                "min_width": 720,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            log.warning("Pixabay HTTP %s", resp.status_code)
            return None
        hits = resp.json().get("hits") or []
        random.shuffle(hits)
        for h in hits:
            sid = h.get("id")
            if is_stock_used("pixabay", sid):
                continue
            videos = h.get("videos") or {}
            for quality in ("large", "medium", "small"):
                vf = videos.get(quality) or {}
                url = vf.get("url")
                if not url:
                    continue
                w = int(vf.get("width") or 0)
                ht = int(vf.get("height") or 0)
                if w * ht < 720 * 720:
                    continue
                return {
                    "source": "pixabay",
                    "id": sid,
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
    trends = fetch_trending_travel(max_items=18)
    trends = [t for t in trends if not is_place_used(t.get("place", ""))]
    if not trends:
        raise RuntimeError("All listed travel places already used — try again later")

    trends = sorted(trends, key=lambda x: x.get("score", 0), reverse=True)
    top = trends[:12]
    random.shuffle(top)

    last_err = None
    for t in top:
        place = t.get("place", "")
        if is_place_used(place):
            continue
        query = t["query"]
        log.info("Trying stock for NEW place %s → %r", place, query)
        for searcher in (_search_pixabay, _search_pexels):
            try:
                hit = searcher(query)
                if hit and not is_stock_used(hit["source"], hit["id"]):
                    log.info("Matched NEW %s via %s id=%s", place, hit["source"], hit["id"])
                    return hit, t
            except Exception as e:
                last_err = e
        simple = f"{place} landscape nature"
        for searcher in (_search_pixabay, _search_pexels):
            try:
                hit = searcher(simple)
                if hit and not is_stock_used(hit["source"], hit["id"]):
                    return hit, t
            except Exception as e:
                last_err = e

    raise RuntimeError(f"No unused stock for unused travel places. last={last_err}")


def _fetch_bgm(vibe: str, out_mp3: str) -> bool:
    """Always try to land real music matching the place vibe."""
    url = os.environ.get("SCENIC_BGM_URL", "").strip()
    if url:
        try:
            _download(url, out_mp3)
            if os.path.getsize(out_mp3) > 8000:
                log.info("BGM from SCENIC_BGM_URL")
                return True
        except Exception as e:
            log.warning("SCENIC_BGM_URL failed: %s", e)

    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if key:
        terms = {
            "calm": ["calm ambient", "soft piano", "peaceful"],
            "epic": ["cinematic", "epic ambient", "adventure"],
            "warm": ["acoustic guitar", "summer chill", "tropical"],
            "mystical": ["ethereal", "ambient space", "meditation"],
        }.get(vibe, ["ambient"])
        for term in terms:
            try:
                resp = requests.get(
                    "https://pixabay.com/api/",
                    params={
                        "key": key,
                        "q": term,
                        "media_type": "music",
                        "per_page": 12,
                        "safesearch": "true",
                    },
                    timeout=25,
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
                        if os.path.getsize(out_mp3) > 8000:
                            log.info("BGM from Pixabay music q=%r", term)
                            return True
                    except Exception:
                        continue
            except Exception as e:
                log.warning("Pixabay music failed: %s", e)

    for track in VIBE_BGM_URLS.get(vibe, VIBE_BGM_URLS["calm"]):
        try:
            _download(track, out_mp3)
            if os.path.getsize(out_mp3) > 8000:
                log.info("BGM from Mixkit vibe=%s", vibe)
                return True
        except Exception as e:
            log.warning("Mixkit BGM failed: %s", e)

    # Last resort: soft stereo ambient (audible, not silent)
    log.warning("Synthesizing soft ambient BGM fallback")
    _run_ffmpeg(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=44100:duration=60",
            "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=44100:duration=60",
            "-filter_complex",
            "[0:a]volume=0.12[a0];[1:a]volume=0.08[a1];[a0][a1]amix=inputs=2:duration=longest,afade=t=in:st=0:d=2,afade=t=out:st=55:d=4",
            "-t", "60", out_mp3,
        ]
    )
    return os.path.isfile(out_mp3) and os.path.getsize(out_mp3) > 1000


def _sourced_lines(place: str, trend: dict) -> list[str]:
    """
    Build narration lines ONLY from the travel headline/source text.
    No invented heights, records, dates, or statistics.
    """
    headline = (trend.get("title") or trend.get("headline") or "").strip()
    # Strip site prefixes
    headline = re.sub(r"^(CNN Travel|BBC Travel|NatGeo|Smithsonian)[:\s-]+", "", headline, flags=re.I)
    headline = re.sub(r"\s+", " ", headline).strip()

    lines: list[str] = []
    lines.append(f"Travel with us to {place}.")

    if headline and len(headline) > 12:
        # Use the published headline wording — do not expand into unverified claims
        safe = headline
        if len(safe.split()) > 22:
            safe = " ".join(safe.split()[:22])
        lines.append(safe)
    else:
        lines.append(f"A place travelers keep returning to — {place}.")

    source = (trend.get("source") or trend.get("subreddit") or "").strip()
    if source:
        lines.append(f"As reported by {source}.")

    return lines[:3]


def _wrap_caption(text: str, width: int = 28) -> str:
    words = text.split()
    lines, cur = [], []
    for w in words:
        cur.append(w)
        if sum(len(x) for x in cur) + len(cur) - 1 >= width:
            lines.append(" ".join(cur))
            cur = []
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines[:4])


def _make_main_clip(
    raw_video: str,
    bgm_path: str | None,
    voice_path: str | None,
    caption_lines: list[str],
    out_path: str,
    target_sec: float,
) -> None:
    """Loop stock to target length, mix voice+BGM, burn captions."""
    caption_path = out_path + ".cap.txt"
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(_wrap_caption("  ·  ".join(caption_lines)))

    font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if not os.path.isfile(font):
        font = os.path.join(os.path.dirname(__file__), "fonts", "Montserrat-Bold.ttf")

    # Prefer bundled font if present
    bundled = os.path.join(os.path.dirname(__file__), "fonts", "Montserrat-Bold.ttf")
    if os.path.isfile(bundled):
        font = bundled

    draw = (
        f"drawtext=fontfile='{font}':"
        f"textfile='{caption_path}':reload=0:"
        f"fontsize=42:fontcolor=white:borderw=3:bordercolor=black@0.7:"
        f"x=(w-text_w)/2:y=h*0.72:line_spacing=12"
    )
    vf = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"crop=1080:1920,"
        f"eq=contrast=1.08:saturation=1.12:brightness=0.02,"
        f"unsharp=5:5:0.6,"
        f"{draw}"
    )
    vf = "".join(vf)

    inputs = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", raw_video]
    # audio inputs
    n_audio = 0
    if voice_path and os.path.isfile(voice_path):
        inputs += ["-i", voice_path]
        voice_idx = 1 + n_audio
        n_audio += 1
    else:
        voice_idx = None
    if bgm_path and os.path.isfile(bgm_path):
        inputs += ["-stream_loop", "-1", "-i", bgm_path]
        bgm_idx = 1 + n_audio
        n_audio += 1
    else:
        bgm_idx = None

    if voice_idx is not None and bgm_idx is not None:
        fc = (
            f"[{voice_idx}:a]volume=1.0,aformat=sample_rates=44100:channel_layouts=stereo[v];"
            f"[{bgm_idx}:a]volume=0.22,aformat=sample_rates=44100:channel_layouts=stereo[b];"
            f"[v][b]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        map_a = ["-map", "[aout]"]
        extra = ["-filter_complex", fc]
    elif voice_idx is not None:
        extra = []
        map_a = ["-map", f"{voice_idx}:a"]
    elif bgm_idx is not None:
        extra = []
        map_a = ["-map", f"{bgm_idx}:a"]
    else:
        inputs += ["-f", "lavfi", "-i", "sine=frequency=200:sample_rate=44100"]
        extra = ["-filter_complex", "[1:a]volume=0.15[aout]"]
        map_a = ["-map", "[aout]"]

    cmd = inputs + [
        "-t", str(target_sec),
        "-vf", vf,
        *extra,
        "-map", "0:v:0",
        *map_a,
        "-c:v", "libx264", "-preset", "medium", "-crf", "17",
        "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        out_path,
    ]
    try:
        _run_ffmpeg(cmd)
    finally:
        if os.path.exists(caption_path):
            os.remove(caption_path)

    dur = _probe_duration(out_path)
    log.info("Scenic main clip duration=%.1fs", dur)
    if dur < MIN_SECONDS:
        raise RuntimeError(f"Scenic still too short ({dur:.1f}s) after loop")


def build_scenic_reel(work_dir: str) -> dict[str, Any]:
    os.makedirs(work_dir, exist_ok=True)
    stock, trend = _pick_stock_for_trends()
    place = trend.get("place") or "Wanderlust"
    if is_place_used(place):
        raise RuntimeError(f"Strict uniqueness blocked scenic place: {place}")

    vibe = _vibe_for_query(stock["query"] + " " + place)
    log.info("Scenic place=%s vibe=%s stock=%s:%s", place, vibe, stock["source"], stock["id"])

    raw_path = os.path.join(work_dir, "scenic_raw.mp4")
    bgm_path = os.path.join(work_dir, "scenic_bgm.mp3")
    voice_path = os.path.join(work_dir, "scenic_voice.mp3")
    main_path = os.path.join(work_dir, "scenic_main.mp4")
    final_path = os.path.join(work_dir, "final.mp4")

    _download(stock["url"], raw_path)
    has_bgm = _fetch_bgm(vibe, bgm_path)

    lines = _sourced_lines(place, trend)
    narration = " ".join(lines)
    log.info("Sourced narration: %s", narration[:160])
    generate_narration(narration, voice_path)

    target = min(float(os.environ.get("MAX_REEL_SECONDS", "58")) - 8.0, TARGET_SECONDS)
    target = max(target, MIN_SECONDS)

    _make_main_clip(
        raw_path,
        bgm_path if has_bgm else None,
        voice_path,
        lines,
        main_path,
        target_sec=target,
    )

    # CTA beat (stay tuned + follow) — default for every scenic reel
    cta = next_cta_beat()
    cta_img = os.path.join(work_dir, "cta.png")
    cta_audio = os.path.join(work_dir, "cta.mp3")
    cta_clip = os.path.join(work_dir, "cta.mp4")
    generate_image(cta["image_prompt"], cta_img)
    generate_narration(cta["narration"], cta_audio)
    build_beat_clip(cta_img, cta_audio, cta["on_screen_text"], cta_clip)

    concat_clips([main_path, cta_clip], final_path)

    topic = f"Travel: {place}"
    credit = f"Video: {stock['photographer']} via {stock['source'].title()}"
    source_name = trend.get("source") or trend.get("subreddit") or "travel press"
    return {
        "topic": topic,
        "final_path": final_path,
        "source": "scenic",
        "vibe": vibe,
        "credit": credit + f" | Facts from: {source_name}",
        "stock": stock,
        "trend": trend,
        "place": place,
        "narration_text": narration,
    }
