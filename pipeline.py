"""
Generate and publish one unique Reel every run.
STRICT: never republish same/similar topic, place, or stock clip.
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
    is_topic_used,
    record_post,
    record_used_topic,
)
from stock_video import find_motion_clip, download_clip, is_stock_used_safe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")

WORK_DIR = os.path.join(os.path.dirname(__file__), "renders")
os.makedirs(WORK_DIR, exist_ok=True)


def build_caption(topic: str, source: str = "trend", extra: str = "") -> str:
    caption = build_growth_caption(topic)
    if extra:
        caption = f"{caption}\n\n{extra}"
    log.info("Caption ready (%d chars)", len(caption))
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


def _want_scenic() -> bool:
    mode = os.environ.get("CONTENT_MODE", "auto").strip().lower()
    if mode == "scenic":
        return True
    if mode in ("trend", "bank", "facts"):
        return False
    try:
        from cta import _load_state
        post_count = int((_load_state() or {}).get("post_count", 0))
    except Exception:
        post_count = 0
    has_stock = bool(
        os.environ.get("PEXELS_API_KEY", "").strip()
        or os.environ.get("PIXABAY_API_KEY", "").strip()
    )
    return has_stock and (post_count % 3 == 2)


def select_script() -> dict:
    mode = os.environ.get("CONTENT_MODE", "auto").strip().lower()
    log.info("CONTENT_MODE=%s (strict uniqueness ON)", mode)

    for attempt in range(5):
        try:
            script = generate_trend_script()
            if not script:
                log.warning("Trend attempt %d produced no script", attempt + 1)
                continue
            topic = script.get("topic", "")
            if is_duplicate_topic(topic):
                log.warning("STRICT reject attempt %d: %s", attempt + 1, topic)
                continue
            log.info("Accepted unique topic: %s", topic)
            return script
        except Exception as e:
            log.warning("Trend attempt %d failed: %s", attempt + 1, e)

    log.error("STRICT: could not produce unique script after 5 attempts — abort")
    notify("❌ Aborted: no unique topic (strict no-repeat)")
    sys.exit(4)


def _build_one_beat(beat: dict, run_dir: str, i: int, on_screen: str | None = None) -> tuple[str, str]:
    narration = beat["narration"]
    prompt = beat.get("image_prompt") or ""
    caption = on_screen if on_screen is not None else narration

    audio_path = os.path.join(run_dir, f"beat{i}.mp3")
    clip_path = os.path.join(run_dir, f"beat{i}.mp4")
    generate_narration(narration, audio_path)

    motion = None
    try:
        motion = find_motion_clip(prompt)
    except Exception as e:
        log.warning("Motion search error: %s", e)

    if motion:
        try:
            # skip if this exact stock file was already used in a prior post
            from uniqueness import is_stock_used

            if is_stock_used(motion.get("source", ""), motion.get("id")):
                log.info("Skip already-used motion stock id=%s", motion.get("id"))
                motion = None
            else:
                raw_vid = os.path.join(run_dir, f"beat{i}_stock.mp4")
                download_clip(motion["url"], raw_vid)
                build_video_beat_clip(raw_vid, audio_path, caption, clip_path)
                log.info("Beat %d: LIVE VIDEO (%s id=%s)", i, motion["source"], motion.get("id"))
                return clip_path, narration
        except Exception as e:
            log.warning("Motion video beat failed, still fallback: %s", e)

    img_path = os.path.join(run_dir, f"beat{i}.png")
    generate_image(prompt, img_path)
    build_beat_clip(img_path, audio_path, caption, clip_path)
    log.info("Beat %d: still + Ken Burns", i)
    return clip_path, narration


def run_scenic(run_dir: str) -> None:
    from scenic_gen import build_scenic_reel

    result = build_scenic_reel(run_dir)
    topic = result["topic"]
    place = result.get("place")
    stock = result.get("stock") or {}

    if is_duplicate_topic(topic):
        log.error("STRICT block scenic duplicate topic: %s", topic)
        sys.exit(5)

    final_path = result["final_path"]
    caption = build_caption(topic, source="scenic", extra=result.get("credit", ""))
    safe, reason = check_content_safe(caption, result.get("narration_text", topic))
    if not safe:
        log.error("Safety blocked scenic: %s", reason)
        record_post(topic, place=place)  # don't retry same blocked place
        notify(f"⚠️ Safety blocked scenic: {topic}\n{reason}")
        sys.exit(2)

    video_url = upload_to_public_host(final_path)
    media_id = publish_reel(video_url, caption, is_ai_generated=False)

    if media_id:
        log.info("Published scenic: %s", media_id)
        record_post(
            topic,
            place=place,
            stock_source=stock.get("source"),
            stock_id=stock.get("id"),
            fingerprint_parts=[result.get("narration_text", "")],
        )
        notify(f"✅ Scenic Reel: {topic}\nmedia_id={media_id}")
        try:
            delete_public_object(video_url)
            cleanup_old_media()
        except Exception as e:
            log.warning("R2 cleanup: %s", e)
    else:
        log.error("Scenic publish failed")
        notify(f"❌ Scenic publish failed: {topic}")
        sys.exit(3)


def run_facts() -> None:
    script = select_script()
    source = script.get("source", "trend")
    topic = script["topic"]

    if is_duplicate_topic(topic):
        log.error("STRICT refusing duplicate: %s", topic)
        notify(f"❌ Blocked duplicate: {topic}")
        sys.exit(5)

    log.info("Selected [%s]: %s", source, topic)

    run_id = uuid.uuid4().hex[:8]
    run_dir = os.path.join(WORK_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    clip_paths = []
    full_narration = []
    used_motion_ids = []

    try:
        beats = list(script["beats"])[:4]
        cta = next_cta_beat()
        log.info("CTA set #%s: %s", cta.get("cta_index"), cta["on_screen_text"])

        for i, beat in enumerate(beats):
            clip_path, narration = _build_one_beat(beat, run_dir, i)
            clip_paths.append(clip_path)
            full_narration.append(narration)
            log.info("Beat %d/%d done", i + 1, len(beats))

        cta_i = len(beats)
        cta_beat = {
            "narration": cta["narration"],
            "image_prompt": cta["image_prompt"],
        }
        clip_path, narration = _build_one_beat(
            cta_beat, run_dir, cta_i, on_screen=cta["on_screen_text"]
        )
        clip_paths.append(clip_path)
        full_narration.append(narration)

        final_path = os.path.join(run_dir, "final.mp4")
        concat_clips(clip_paths, final_path)

        # Final gate before upload
        if is_duplicate_topic(topic):
            log.error("STRICT final gate blocked: %s", topic)
            sys.exit(5)

        caption = build_caption(topic, source=source)
        safe, reason = check_content_safe(
            caption, " ".join(full_narration[:-1]) or " ".join(full_narration)
        )
        if not safe:
            log.error("Safety blocked: %s", reason)
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
            )
            notify(f"✅ Published [{source}]: {topic}\nmedia_id={media_id}")
            try:
                delete_public_object(video_url)
                cleanup_old_media()
            except Exception as e:
                log.warning("R2 cleanup: %s", e)
        else:
            log.error("Publish failed")
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
    if _want_scenic():
        run_id = uuid.uuid4().hex[:8]
        run_dir = os.path.join(WORK_DIR, run_id)
        os.makedirs(run_dir, exist_ok=True)
        log.info("Running SCENIC (strict unique places/stock)")
        try:
            run_scenic(run_dir)
        except Exception as e:
            log.exception("Scenic failed — facts fallback: %s", e)
            notify(f"⚠️ Scenic failed, trying facts: {e}")
            run_facts()
        finally:
            if os.environ.get("CLEANUP_RENDERS", "1") == "1":
                shutil.rmtree(run_dir, ignore_errors=True)
        return

    run_facts()


if __name__ == "__main__":
    run_once()
