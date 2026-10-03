"""
Generate and publish one unique Reel every run.

Modes are PURE — never mix in one video:
  scenic  → travel stock video + BGM only (no fact narration / no AI stills)
  trend   → educational facts only (AI stills + optional motion B-roll matching the fact)
  auto    → picks one pure mode for the whole run (not half/half)
"""

import logging
import os
import shutil
import sys
import uuid

from image_gen import generate_image
from voice_gen import generate_narration
from video_assemble import build_beat_clip, build_video_beat_clip, concat_clips
from safety_gate import check_content_safe
from instagram_client import publish_reel
from media_host import upload_to_public_host, delete_public_object, cleanup_old_media
from cta import next_cta_beat
from engagement import build_growth_caption
from trend_script import generate_trend_script
from uniqueness import (
    is_duplicate_topic,
    is_duplicate_script,
    is_stock_used,
    record_post,
    record_used_topic,
)
from stock_video import find_motion_clip, download_clip

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")

WORK_DIR = os.path.join(os.path.dirname(__file__), "renders")
os.makedirs(WORK_DIR, exist_ok=True)


def _content_mode() -> str:
    """Normalize workflow input to: auto | trend | scenic."""
    raw = os.environ.get("CONTENT_MODE", "auto").strip().lower()
    # common typos
    aliases = {
        "sceinc": "scenic",
        "sceninc": "scenic",
        "scenery": "scenic",
        "travel": "scenic",
        "facts": "trend",
        "fact": "trend",
        "bank": "trend",
        "education": "trend",
        "edu": "trend",
    }
    mode = aliases.get(raw, raw)
    if mode not in ("auto", "trend", "scenic"):
        log.warning("Unknown CONTENT_MODE=%r — using auto", raw)
        mode = "auto"
    return mode


def build_caption(topic: str, source: str = "trend", extra: str = "") -> str:
    if source == "scenic":
        # Pure travel caption — no educational "did you know" growth pack
        lines = [
            topic,
            "",
            "Escape the ordinary · pure scenery · no filters on wonder",
            "Double-tap if this place is on your bucket list",
            "Follow for daily destinations",
            "",
            "#travel #wanderlust #nature #shorts #reels #landscape #explore",
        ]
        if extra:
            lines.extend(["", extra])
        caption = "\n".join(lines)
    else:
        caption = build_growth_caption(topic)
        if extra:
            caption = f"{caption}\n\n{extra}"
    log.info("Caption ready (%d chars) source=%s", len(caption), source)
    return caption


def notify(message: str) -> None:
    url = os.environ.get("NOTIFY_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        import requests
        requests.post(url, json={"content": message[:1900]}, timeout=15)
    except Exception as e:
        log.warning("Notify webhook failed: %s", e)


def _resolve_mode() -> str:
    """
    Decide pure mode for THIS run only.
    auto → scenic every 3rd post if stock keys exist, else always trend.
    Never returns a hybrid.
    """
    mode = _content_mode()
    if mode in ("scenic", "trend"):
        log.info("Forced pure mode: %s", mode)
        return mode

    # auto
    try:
        from cta import _load_state
        post_count = int((_load_state() or {}).get("post_count", 0))
    except Exception:
        post_count = 0
    has_stock = bool(
        os.environ.get("PEXELS_API_KEY", "").strip()
        or os.environ.get("PIXABAY_API_KEY", "").strip()
    )
    if has_stock and (post_count % 3 == 2):
        log.info("auto → pure SCENIC (post_count=%s)", post_count)
        return "scenic"
    log.info("auto → pure TREND (post_count=%s)", post_count)
    return "trend"


def select_script() -> dict:
    log.info("Selecting TREND script (strict uniqueness)")

    for attempt in range(6):
        try:
            script = generate_trend_script()
            if not script:
                log.warning("Trend attempt %d produced no script", attempt + 1)
                continue
            topic = script.get("topic", "")
            narrs = [b["narration"] for b in script.get("beats", [])]
            prompts = [b.get("image_prompt", "") for b in script.get("beats", [])]
            if is_duplicate_script(topic, narrs, prompts):
                log.warning("STRICT reject attempt %d: %s", attempt + 1, topic)
                continue
            log.info("Accepted unique topic: %s", topic)
            return script
        except Exception as e:
            log.warning("Trend attempt %d failed: %s", attempt + 1, e)

    log.error("STRICT: could not produce unique script — abort (no bank recycle)")
    notify("❌ Aborted: no unique topic")
    sys.exit(4)


def _build_one_beat(beat: dict, run_dir: str, i: int, on_screen: str | None = None) -> tuple[str, str, list[str]]:
    """Educational beat only — stills or fact-matched motion B-roll (not travel niche)."""
    narration = beat["narration"]
    prompt = beat.get("image_prompt") or ""
    caption = on_screen if on_screen is not None else narration
    stock_keys: list[str] = []

    audio_path = os.path.join(run_dir, f"beat{i}.mp3")
    clip_path = os.path.join(run_dir, f"beat{i}.mp4")
    generate_narration(narration, audio_path)

    # Motion B-roll only when the FACT prompt needs real movement (water, clouds…)
    # Never inject random travel scenery into a science topic.
    motion = None
    try:
        motion = find_motion_clip(prompt)
    except Exception as e:
        log.warning("Motion search error: %s", e)

    if motion:
        try:
            if is_stock_used(motion.get("source", ""), motion.get("id")):
                log.info("Skip already-used motion stock id=%s", motion.get("id"))
                motion = None
            else:
                raw_vid = os.path.join(run_dir, f"beat{i}_stock.mp4")
                download_clip(motion["url"], raw_vid)
                build_video_beat_clip(raw_vid, audio_path, caption, clip_path)
                key = f"{motion['source']}:{motion.get('id')}"
                stock_keys.append(key)
                log.info("Beat %d: LIVE VIDEO (%s)", i, key)
                return clip_path, narration, stock_keys
        except Exception as e:
            log.warning("Motion video beat failed, still fallback: %s", e)

    img_path = os.path.join(run_dir, f"beat{i}.png")
    generate_image(prompt, img_path)
    build_beat_clip(img_path, audio_path, caption, clip_path)
    log.info("Beat %d: still + Ken Burns", i)
    return clip_path, narration, stock_keys


def run_scenic(run_dir: str) -> None:
    """PURE scenic: one continuous travel stock clip + BGM. No fact beats."""
    from scenic_gen import build_scenic_reel

    log.info("=== PURE SCENIC MODE (no trend content) ===")
    result = build_scenic_reel(run_dir)
    topic = result["topic"]
    place = result.get("place")
    stock = result.get("stock") or {}

    if is_duplicate_topic(topic):
        log.error("STRICT block scenic duplicate: %s", topic)
        sys.exit(5)

    final_path = result["final_path"]
    if not os.path.isfile(final_path):
        raise RuntimeError(f"Scenic final missing: {final_path}")

    caption = build_caption(topic, source="scenic", extra=result.get("credit", ""))
    safe, reason = check_content_safe(caption, result.get("narration_text", topic))
    if not safe:
        record_post(topic, place=place)
        notify(f"⚠️ Safety blocked scenic: {topic}\n{reason}")
        sys.exit(2)

    video_url = upload_to_public_host(final_path)
    media_id = publish_reel(video_url, caption, is_ai_generated=False)

    if media_id:
        record_post(
            topic,
            place=place,
            stock_source=stock.get("source"),
            stock_id=stock.get("id"),
            fingerprint_parts=[result.get("narration_text", "")],
        )
        notify(f"✅ Pure SCENIC Reel: {topic}\nmedia_id={media_id}")
        try:
            delete_public_object(video_url)
            cleanup_old_media()
        except Exception as e:
            log.warning("R2 cleanup: %s", e)
    else:
        notify(f"❌ Scenic publish failed: {topic}")
        sys.exit(3)


def run_facts() -> None:
    """PURE trend/facts: educational beats only."""
    log.info("=== PURE TREND/FACTS MODE (no scenic niche) ===")
    script = select_script()
    source = script.get("source", "trend")
    topic = script["topic"]
    narrs = [b["narration"] for b in script.get("beats", [])]
    prompts = [b.get("image_prompt", "") for b in script.get("beats", [])]

    if is_duplicate_script(topic, narrs, prompts):
        log.error("STRICT refusing duplicate: %s", topic)
        notify(f"❌ Blocked duplicate: {topic}")
        sys.exit(5)

    log.info("Selected [%s]: %s", source, topic)

    run_id = uuid.uuid4().hex[:8]
    run_dir = os.path.join(WORK_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    clip_paths = []
    full_narration = []
    all_stock_ids: list[str] = []

    try:
        beats = list(script["beats"])[:4]
        cta = next_cta_beat()

        for i, beat in enumerate(beats):
            clip_path, narration, sk = _build_one_beat(beat, run_dir, i)
            clip_paths.append(clip_path)
            full_narration.append(narration)
            all_stock_ids.extend(sk)

        cta_i = len(beats)
        cta_beat = {
            "narration": cta["narration"],
            "image_prompt": cta["image_prompt"],
        }
        clip_path, narration, sk = _build_one_beat(
            cta_beat, run_dir, cta_i, on_screen=cta["on_screen_text"]
        )
        clip_paths.append(clip_path)
        full_narration.append(narration)
        all_stock_ids.extend(sk)

        final_path = os.path.join(run_dir, "final.mp4")
        concat_clips(clip_paths, final_path)

        if is_duplicate_script(topic, full_narration, prompts):
            log.error("STRICT final gate blocked: %s", topic)
            sys.exit(5)

        caption = build_caption(topic, source="trend")
        safe, reason = check_content_safe(
            caption, " ".join(full_narration[:-1]) or " ".join(full_narration)
        )
        if not safe:
            record_used_topic(topic)
            notify(f"⚠️ Safety blocked: {topic}\n{reason}")
            sys.exit(2)

        video_url = upload_to_public_host(final_path)
        media_id = publish_reel(video_url, caption, is_ai_generated=True)

        if media_id:
            log.info("Published: %s", media_id)
            record_post(
                topic,
                fingerprint_parts=full_narration[:3],
                stock_ids=all_stock_ids,
            )
            notify(f"✅ Pure TREND Reel: {topic}\nmedia_id={media_id}")
            try:
                delete_public_object(video_url)
                cleanup_old_media()
            except Exception as e:
                log.warning("R2 cleanup: %s", e)
        else:
            notify(f"❌ Publish failed: {topic}")
            sys.exit(3)
    except Exception as e:
        log.exception("Pipeline failed")
        notify(f"❌ Pipeline error: {e}")
        raise
    finally:
        if os.environ.get("CLEANUP_RENDERS", "1") == "1":
            shutil.rmtree(run_dir, ignore_errors=True)


def run_once() -> None:
    mode = _resolve_mode()
    log.info("RUN MODE (pure)=%s", mode)

    if mode == "scenic":
        run_id = uuid.uuid4().hex[:8]
        run_dir = os.path.join(WORK_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)
        try:
            run_scenic(run_dir)
        except Exception as e:
            # CRITICAL: explicit scenic must NEVER silently become a fact reel
            log.exception("Scenic failed — aborting (no facts hybrid)")
            notify(
                f"❌ SCENIC mode failed — not falling back to facts (avoids hybrid).\n{e}"
            )
            sys.exit(6)
        finally:
            if os.environ.get("CLEANUP_RENDERS", "1") == "1":
                shutil.rmtree(run_dir, ignore_errors=True)
        return

    # trend (or auto→trend)
    run_facts()


if __name__ == "__main__":
    run_once()
