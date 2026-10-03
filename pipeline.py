"""
Generate and publish one unique Reel every run.
Modes: educational facts (default) or scenic places (licensed stock + BGM).
"""

import logging
import os
import shutil
import sys
import uuid

from image_gen import generate_image
from voice_gen import generate_narration
from video_assemble import build_beat_clip, concat_clips
from safety_gate import check_content_safe
from instagram_client import publish_reel
from media_host import upload_to_public_host, delete_public_object, cleanup_old_media
from cta import next_cta_beat
from engagement import build_growth_caption
from trend_script import generate_trend_script, record_used_topic, is_topic_used

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
    # auto: roughly every 3rd post is scenic (if keys present)
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
    log.info("CONTENT_MODE=%s", mode)

    for attempt in range(3):
        try:
            script = generate_trend_script()
            if not script:
                log.warning("Trend attempt %d produced no script", attempt + 1)
                continue
            topic = script.get("topic", "")
            if is_topic_used(topic):
                log.warning("Rejected already-used topic: %s", topic)
                continue
            log.info("Accepted unique topic: %s", topic)
            return script
        except Exception as e:
            log.warning("Trend attempt %d failed: %s", attempt + 1, e)

    log.error("Could not produce a unique script after 3 attempts — aborting")
    notify("❌ Pipeline aborted: could not generate a unique topic")
    sys.exit(4)


def run_scenic(run_dir: str) -> None:
    from scenic_gen import build_scenic_reel

    result = build_scenic_reel(run_dir)
    topic = result["topic"]
    final_path = result["final_path"]

    if is_topic_used(topic):
        # Slightly uniquify with stock id
        topic = f"{topic} · {result['stock'].get('id')}"

    caption = build_caption(
        topic,
        source="scenic",
        extra=result.get("credit", ""),
    )
    safe, reason = check_content_safe(caption, result.get("narration_text", topic))
    if not safe:
        log.error("Safety gate blocked scenic: %s", reason)
        try:
            record_used_topic(topic)
        except Exception:
            pass
        notify(f"⚠️ Safety blocked scenic: {topic}\n{reason}")
        sys.exit(2)

    video_url = upload_to_public_host(final_path)
    log.info("Uploaded scenic: %s", video_url)
    media_id = publish_reel(video_url, caption, is_ai_generated=False)

    if media_id:
        log.info("Published scenic: %s", media_id)
        try:
            record_used_topic(topic)
        except Exception as e:
            log.warning("record topic: %s", e)
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

    if is_topic_used(topic):
        log.error("Refusing duplicate: %s", topic)
        notify(f"❌ Blocked duplicate: {topic}")
        sys.exit(5)

    log.info("Selected [%s]: %s", source, topic)

    run_id = uuid.uuid4().hex[:8]
    run_dir = os.path.join(WORK_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    clip_paths = []
    full_narration = []

    try:
        beats = list(script["beats"])[:4]
        cta = next_cta_beat()
        log.info("CTA set #%s: %s", cta.get("cta_index"), cta["on_screen_text"])

        for i, beat in enumerate(beats):
            img_path = os.path.join(run_dir, f"beat{i}.png")
            audio_path = os.path.join(run_dir, f"beat{i}.mp3")
            clip_path = os.path.join(run_dir, f"beat{i}.mp4")

            generate_image(beat["image_prompt"], img_path)
            generate_narration(beat["narration"], audio_path)
            build_beat_clip(img_path, audio_path, beat["narration"], clip_path)

            clip_paths.append(clip_path)
            full_narration.append(beat["narration"])
            log.info("Beat %d/%d done", i + 1, len(beats))

        cta_i = len(beats)
        img_path = os.path.join(run_dir, f"beat{cta_i}.png")
        audio_path = os.path.join(run_dir, f"beat{cta_i}.mp3")
        clip_path = os.path.join(run_dir, f"beat{cta_i}.mp4")
        generate_image(cta["image_prompt"], img_path)
        generate_narration(cta["narration"], audio_path)
        build_beat_clip(img_path, audio_path, cta["on_screen_text"], clip_path)
        clip_paths.append(clip_path)
        full_narration.append(cta["narration"])
        log.info("CTA beat done")

        final_path = os.path.join(run_dir, "final.mp4")
        concat_clips(clip_paths, final_path)
        log.info("Assembled: %s", final_path)

        caption = build_caption(topic, source=source)
        safe, reason = check_content_safe(
            caption, " ".join(full_narration[:-1]) or " ".join(full_narration)
        )
        if not safe:
            log.error("Safety gate blocked: %s", reason)
            try:
                record_used_topic(topic)
            except Exception:
                pass
            notify(f"⚠️ Safety blocked: {topic}\n{reason}")
            sys.exit(2)

        video_url = upload_to_public_host(final_path)
        log.info("Uploaded: %s", video_url)
        media_id = publish_reel(video_url, caption, is_ai_generated=True)

        if media_id:
            log.info("Published: %s", media_id)
            try:
                record_used_topic(topic)
            except Exception as e:
                log.warning("record topic: %s", e)
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
        log.info("Running SCENIC niche")
        try:
            run_scenic(run_dir)
        except Exception as e:
            log.exception("Scenic failed — falling back to facts: %s", e)
            notify(f"⚠️ Scenic failed, trying facts: {e}")
            run_facts()
        finally:
            if os.environ.get("CLEANUP_RENDERS", "1") == "1":
                shutil.rmtree(run_dir, ignore_errors=True)
        return

    run_facts()


if __name__ == "__main__":
    run_once()
