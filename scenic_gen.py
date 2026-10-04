"""Pure scenic reel — longer clips, soft ping-pong (not 3x hard loop), full CTA voice."""
from __future__ import annotations
import logging, os, random, re, subprocess
from typing import Any
import requests
from travel_scout import fetch_trending_travel
from uniqueness import is_place_used, is_stock_used
from voice_gen import generate_narration
from cta import next_cta_beat
from video_assemble import build_beat_clip
from image_gen import generate_image

log = logging.getLogger("scenic_gen")
PEXELS_VIDEOS = "https://api.pexels.com/videos/search"
PIXABAY_VIDEOS = "https://pixabay.com/api/videos/"
# Prefer ~30–38s so we rarely need more than one soft reverse pass
TARGET_SECONDS = float(os.environ.get("SCENIC_TARGET_SECONDS", "34"))
MIN_SECONDS = 26.0
MIN_STOCK_DURATION = 12.0  # reject tiny clips that force 3x loops

def _vibe_for_query(q: str) -> str:
    q = (q or "").lower()
    if any(w in q for w in ("aurora", "mist", "night", "cappadocia", "kyoto")): return "mystical"
    if any(w in q for w in ("mountain", "alps", "canyon", "peak", "fjord", "ladakh")): return "epic"
    if any(w in q for w in ("sunset", "desert", "bali", "maldives", "beach", "santorini")): return "warm"
    return "calm"

def _download(url: str, path: str, timeout: int = 180) -> None:
    with requests.get(url, stream=True, timeout=timeout, headers={"User-Agent": "AmbsonScenic/1.0"}) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                if chunk: f.write(chunk)

def _probe_duration(path: str) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", path],
        text=True,
    ).strip()
    return float(out)

def _is_audio_file(path: str) -> bool:
    if not path or not os.path.isfile(path) or os.path.getsize(path) < 2000:
        return False
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        return "audio" in out.lower()
    except Exception:
        return False

def _run_ffmpeg(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {(proc.stderr or '')[-900:]}")

def _search_pixabay(query: str) -> dict | None:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return None
    try:
        resp = requests.get(
            PIXABAY_VIDEOS,
            params={"key": key, "q": query, "per_page": 20, "video_type": "film",
                    "safesearch": "true", "min_width": 720},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        hits = resp.json().get("hits") or []
        # Prefer longer clips first
        hits = sorted(hits, key=lambda h: int(h.get("duration") or 0), reverse=True)
        random.shuffle(hits[:8])  # shuffle among longer ones
        for h in hits:
            sid = h.get("id")
            if is_stock_used("pixabay", sid):
                continue
            dur = float(h.get("duration") or 0)
            if dur and dur < MIN_STOCK_DURATION:
                continue
            videos = h.get("videos") or {}
            for quality in ("large", "medium", "small"):
                vf = videos.get(quality) or {}
                url = vf.get("url")
                if not url:
                    continue
                w, ht = int(vf.get("width") or 0), int(vf.get("height") or 0)
                if w * ht < 720 * 720:
                    continue
                return {
                    "source": "pixabay", "id": sid, "url": url,
                    "width": w, "height": ht,
                    "duration": dur,
                    "photographer": h.get("user") or "Pixabay",
                    "query": query,
                }
    except Exception as e:
        log.warning("Pixabay search failed: %s", e)
    return None

def _search_pexels(query: str) -> dict | None:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    try:
        resp = requests.get(
            PEXELS_VIDEOS,
            headers={"Authorization": key},
            params={"query": query, "per_page": 15},
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        videos = resp.json().get("videos") or []
        videos = sorted(videos, key=lambda v: int(v.get("duration") or 0), reverse=True)
        for v in videos:
            dur = float(v.get("duration") or 0)
            if dur and dur < MIN_STOCK_DURATION:
                continue
            files = v.get("video_files") or []
            files = sorted(
                files,
                key=lambda f: (
                    1 if int(f.get("height") or 0) >= int(f.get("width") or 0) else 0,
                    int(f.get("width") or 0) * int(f.get("height") or 0),
                ),
                reverse=True,
            )
            if not files or not files[0].get("link"):
                continue
            best = files[0]
            sid = v.get("id")
            if is_stock_used("pexels", sid):
                continue
            w, h = int(best.get("width") or 0), int(best.get("height") or 0)
            if w * h < 720 * 720:
                continue
            return {
                "source": "pexels", "id": sid, "url": best["link"],
                "width": w, "height": h, "duration": dur,
                "photographer": (v.get("user") or {}).get("name") or "Pexels",
                "query": query,
            }
    except Exception as e:
        log.warning("Pexels failed: %s", e)
    return None

def _pick_stock_for_trends():
    trends = [t for t in fetch_trending_travel(max_items=18) if not is_place_used(t.get("place", ""))]
    if not trends:
        raise RuntimeError("All listed travel places already used")
    top = sorted(trends, key=lambda x: x.get("score", 0), reverse=True)[:12]
    random.shuffle(top)
    last_err = None
    for t in top:
        place = t.get("place", "")
        if is_place_used(place):
            continue
        for q in (t["query"], f"{place} landscape nature", f"{place} drone aerial"):
            for searcher in (_search_pixabay, _search_pexels):
                try:
                    hit = searcher(q)
                    if hit and not is_stock_used(hit["source"], hit["id"]):
                        log.info(
                            "Matched %s via %s id=%s dur=%s",
                            place, hit["source"], hit["id"], hit.get("duration"),
                        )
                        return hit, t
                except Exception as e:
                    last_err = e
    raise RuntimeError(f"No unused stock. last={last_err}")

def _fetch_bgm(vibe: str, out_mp3: str) -> bool:
    def try_url(url: str, label: str) -> bool:
        try:
            _download(url, out_mp3)
            if _is_audio_file(out_mp3):
                log.info("BGM OK %s", label)
                return True
            log.warning("Not audio: %s", label)
        except Exception as e:
            log.warning("%s: %s", label, e)
        try:
            if os.path.isfile(out_mp3):
                os.remove(out_mp3)
        except OSError:
            pass
        return False

    url = os.environ.get("SCENIC_BGM_URL", "").strip()
    if url and try_url(url, "env"):
        return True

    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if key:
        for term in {"calm": ["ambient piano"], "epic": ["cinematic"], "warm": ["acoustic guitar"], "mystical": ["ethereal"]}.get(vibe, ["ambient"]):
            try:
                resp = requests.get(
                    "https://pixabay.com/api/",
                    params={"key": key, "q": term, "media_type": "music", "per_page": 12, "safesearch": "true"},
                    timeout=25,
                )
                if resp.status_code != 200:
                    continue
                hits = resp.json().get("hits") or []
                random.shuffle(hits)
                for h in hits:
                    audio_url = h.get("url")
                    if audio_url and try_url(str(audio_url), f"pixabay:{term}"):
                        return True
            except Exception as e:
                log.warning("pixabay music: %s", e)

    for track in (
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-9.mp3",
        "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-15.mp3",
    ):
        if try_url(track, "soundhelix"):
            return True

    log.warning("Synth ambient BGM")
    _run_ffmpeg([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=196:sample_rate=44100:duration=60",
        "-f", "lavfi", "-i", "sine=frequency=294:sample_rate=44100:duration=60",
        "-filter_complex",
        "[0:a]volume=0.14[a0];[1:a]volume=0.09[a1];[a0][a1]amix=inputs=2:duration=longest,afade=t=in:st=0:d=2,afade=t=out:st=55:d=4",
        "-t", "60", out_mp3,
    ])
    return _is_audio_file(out_mp3)

def _sourced_lines(place: str, trend: dict) -> list[str]:
    headline = (trend.get("title") or trend.get("headline") or "").strip()
    headline = re.sub(r"^(CNN Travel|BBC Travel|NatGeo|Smithsonian)[:\s-]+", "", headline, flags=re.I)
    headline = re.sub(r"\s+", " ", headline).strip()
    lines = [f"Travel with us to {place}."]
    if headline and len(headline) > 12 and "evergreen travel favourite" not in headline.lower():
        lines.append(" ".join(headline.split()[:22]))
    else:
        lines.append(f"A destination travelers keep seeking — {place}.")
    return lines[:2]

def _wrap_caption(text: str, width: int = 28) -> str:
    words, lines, cur = text.split(), [], []
    for w in words:
        cur.append(w)
        if sum(len(x) for x in cur) + len(cur) - 1 >= width:
            lines.append(" ".join(cur))
            cur = []
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines[:4])

def _extend_video_soft(raw_video: str, target_sec: float, out_video: str) -> None:
    """
    Extend short stock without hard 3x cut-loops.
    Uses forward + reverse (ping-pong) once, then trims to target.
    Feels like continuous camera motion instead of a jump-cut restart.
    """
    stock_dur = _probe_duration(raw_video)
    log.info("Stock duration=%.1fs target=%.1fs", stock_dur, target_sec)

    vf_base = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        "eq=contrast=1.08:saturation=1.12:brightness=0.02,"
        "unsharp=5:5:0.6"
    )
    vf_base = "".join(vf_base)

    if stock_dur >= target_sec - 0.5:
        # Long enough — just trim
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", raw_video, "-t", f"{target_sec:.2f}",
            "-vf", vf_base,
            "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
            "-pix_fmt", "yuv420p", "-r", "30", out_video,
        ])
        return

    # Ping-pong once (forward + reverse) ≈ 2x length, soft turnaround
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", raw_video,
        "-filter_complex",
        f"[0:v]{vf_base},split[f][r];[r]reverse[rr];"
        f"[f][rr]concat=n=2:v=1:a=0,trim=0:{target_sec:.2f},setpts=PTS-STARTPTS[vout]",
        "-map", "[vout]",
        "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
        "-pix_fmt", "yuv420p", "-r", "30", out_video,
    ])

def _make_main_clip(raw_video, bgm_path, voice_path, caption_lines, out_path, target_sec):
    caption_path = out_path + ".cap.txt"
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(_wrap_caption("  ·  ".join(caption_lines)))

    font = os.path.join(os.path.dirname(__file__), "fonts", "Montserrat-Bold.ttf")
    if not os.path.isfile(font):
        font = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    extended = out_path + ".ext.mp4"
    _extend_video_soft(raw_video, target_sec, extended)

    t = f"{target_sec:.2f}"
    mixed_audio = out_path + ".mixed.m4a"
    if voice_path and _is_audio_file(voice_path) and bgm_path and _is_audio_file(bgm_path):
        _run_ffmpeg([
            "ffmpeg", "-y",
            "-i", voice_path,
            "-stream_loop", "-1", "-i", bgm_path,
            "-filter_complex",
            f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo,apad=whole_dur={t},atrim=0:{t},volume=1.15[v];"
            f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{t},volume=0.22[b];"
            f"[v][b]amix=inputs=2:duration=longest:dropout_transition=0[aout]",
            "-map", "[aout]", "-t", t, "-c:a", "aac", "-b:a", "192k", mixed_audio,
        ])
    elif voice_path and _is_audio_file(voice_path):
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", voice_path,
            "-af", f"aformat=sample_rates=44100:channel_layouts=stereo,apad=whole_dur={t},atrim=0:{t},volume=1.15",
            "-t", t, "-c:a", "aac", "-b:a", "192k", mixed_audio,
        ])
    else:
        _run_ffmpeg([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", bgm_path if bgm_path else voice_path,
            "-af", f"aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{t},volume=0.35",
            "-t", t, "-c:a", "aac", "-b:a", "192k", mixed_audio,
        ])

    draw = (
        f"drawtext=fontfile='{font}':textfile='{caption_path}':"
        f"fontsize=42:fontcolor=white:borderw=3:bordercolor=black@0.7:"
        f"x=(w-text_w)/2:y=h*0.72:line_spacing=12"
    )
    try:
        _run_ffmpeg([
            "ffmpeg", "-y",
            "-i", extended,
            "-i", mixed_audio,
            "-t", t,
            "-vf", draw,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17",
            "-pix_fmt", "yuv420p", "-r", "30",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            out_path,
        ])
    finally:
        for p in (caption_path, mixed_audio, extended):
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    dur = _probe_duration(out_path)
    log.info("Scenic main duration=%.1fs (target=%.1fs)", dur, target_sec)
    if dur < MIN_SECONDS - 2:
        raise RuntimeError(f"Scenic too short ({dur:.1f}s)")

def _concat_reencode(clips: list[str], out_path: str) -> None:
    """Always re-encode so CTA audio is never dropped by stream-copy mismatch."""
    list_path = out_path + ".list.txt"
    with open(list_path, "w") as f:
        for p in clips:
            f.write(f"file '{os.path.abspath(p)}'\n")
    try:
        _run_ffmpeg([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path,
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            out_path,
        ])
    finally:
        if os.path.exists(list_path):
            os.remove(list_path)

def build_scenic_reel(work_dir: str) -> dict[str, Any]:
    os.makedirs(work_dir, exist_ok=True)
    stock, trend = _pick_stock_for_trends()
    place = trend.get("place") or "Wanderlust"
    if is_place_used(place):
        raise RuntimeError(f"Place blocked: {place}")
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
    log.info("Narration: %s", narration[:160])
    generate_narration(narration, voice_path)
    if not _is_audio_file(voice_path):
        raise RuntimeError("TTS produced no audio")

    # Cap target near stock length so we don't need 3 hard loops
    stock_dur = _probe_duration(raw_path)
    target = min(TARGET_SECONDS, max(MIN_SECONDS, stock_dur * 1.85))
    target = min(target, float(os.environ.get("MAX_REEL_SECONDS", "58")) - 10.0)
    log.info("Using target=%.1fs from stock=%.1fs", target, stock_dur)

    _make_main_clip(raw_path, bgm_path if has_bgm else None, voice_path, lines, main_path, target)

    # CTA with loud, clear narration (not caption-only)
    cta = next_cta_beat()
    cta_img = os.path.join(work_dir, "cta.png")
    cta_audio = os.path.join(work_dir, "cta.mp3")
    cta_clip = os.path.join(work_dir, "cta.mp4")
    generate_image(cta["image_prompt"], cta_img)
    cta_text = cta["narration"]
    log.info("CTA narration: %s", cta_text[:120])
    generate_narration(cta_text, cta_audio)
    if not _is_audio_file(cta_audio):
        raise RuntimeError("CTA TTS produced no audio")
    # Boost CTA voice slightly so it's never buried
    cta_loud = os.path.join(work_dir, "cta_loud.mp3")
    _run_ffmpeg([
        "ffmpeg", "-y", "-i", cta_audio,
        "-af", "volume=1.35,loudnorm=I=-14:TP=-1.5:LRA=11",
        "-c:a", "libmp3lame", "-b:a", "192k", cta_loud,
    ])
    build_beat_clip(cta_img, cta_loud if _is_audio_file(cta_loud) else cta_audio,
                    cta["on_screen_text"], cta_clip)

    # Re-encode concat so CTA audio stream is never dropped
    _concat_reencode([main_path, cta_clip], final_path)
    final_dur = _probe_duration(final_path)
    log.info("Final scenic reel duration=%.1fs", final_dur)

    credit = f"Video: {stock['photographer']} via {stock['source'].title()}"
    return {
        "topic": f"Travel: {place}",
        "final_path": final_path,
        "source": "scenic",
        "vibe": vibe,
        "credit": credit,
        "stock": stock,
        "trend": trend,
        "place": place,
        "narration_text": narration + " " + cta_text,
    }
