"""
Generate and publish one Reel.

CONTENT_MODE:
  bank   — curated script_bank (default; morning)
  trend  — niche-trending topic via Reddit + Gemini (evening)
  auto   — trend first, fall back to bank
"""

import logging
import os
import shutil
import sys
import uuid

from script_bank import pick_script
from image_gen import generate_image
from voice_gen import generate_narration
from video_assemble import build_beat_clip, concat_clips
from safety_gate import check_content_safe
from instagram_client import publish_reel
from media_host import upload_to_public_host, delete_public_object, cleanup_old_media

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")

WORK_DIR = os.path.join(os.path.dirname(__file__), "renders")
os.makedirs(WORK_DIR, exist_ok=True)


def build_caption(topic: str, source: str = "bank") -> str:
    affiliate_link = os.environ.get("AFFILIATE_LINK", "")
    cta = "\n\nLink in bio \U0001f517" if affiliate_link else ""
    tags = (
        "#history #ancientengineering #cosmicmysteries #didyouknow "
        "#sciencefacts #ancienthistory #spacefacts"
    )
    if source == "trend":
        tags += " #trending #science"
    return f"{topic}\n.\n.\n{tags}{cta}"


def notify(message: str) -> None:
    url = os.environ.get("NOTIFY_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        import requests
        requests.post(url, json={"content": message[:1900]}, timeout=15)
    except Exception as e:
        log.warning("Notify webhook failed: %s", e)


def select_script() -> dict:
    mode = os.environ.get("CONTENT_MODE", "bank").strip().lower()
    log.info("CONTENT_MODE=%s", mode)

    if mode in ("trend", "auto"):
        try:
            from trend_script import generate_trend_script
            script = generate_trend_script()
            if script:
                return script
            log.warning("Trend mode produced no script; falling back to script bank")
        except Exception as e:
            log.warning("Trend pipeline failed (%s); falling back to script bank", e)

    script = pick_script()
    script = dict(script)
    script["source"] = "bank"
    return script


def run_once() -> None:
    script = select_script()
    source = script.get("source", "bank")
    log.info("Selected [%s]: %s", source, script["topic"])

    run_id = uuid.uuid4().hex[:8]
    run_dir = os.path.join(WORK_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    clip_paths = []
    full_narration = []

    try:
        for i, beat in enumerate(script["beats"]):
            img_path = os.path.join(run_dir, f"beat{i}.png")
            audio_path = os.path.join(run_dir, f"beat{i}.mp3")
            clip_path = os.path.join(run_dir, f"beat{i}.mp4")

            generate_image(beat["image_prompt"], img_path)
            generate_narration(beat["narration"], audio_path)
            build_beat_clip(img_path, audio_path, beat["narration"], clip_path)

            clip_paths.append(clip_path)
            full_narration.append(beat["narration"])
            log.info("Beat %d/%d done", i + 1, len(script["beats"]))

        final_path = os.path.join(run_dir, "final.mp4")
        concat_clips(clip_paths, final_path)
        log.info("Assembled: %s", final_path)

        caption = build_caption(script["topic"], source=source)
        safe, reason = check_content_safe(caption, " ".join(full_narration))
        if not safe:
            log.error("Safety gate blocked this post: %s", reason)
            notify(f"⚠️ Safety gate blocked post: {script['topic']}\nReason: {reason}")
            sys.exit(2)

        video_url = upload_to_public_host(final_path)
        log.info("Uploaded: %s", video_url)
        media_id = publish_reel(video_url, caption, is_ai_generated=True)

        if media_id:
            log.info("Published: %s", media_id)
            notify(f"✅ Published Reel [{source}]: {script['topic']}\nmedia_id={media_id}")
            try:
                delete_public_object(video_url)
                cleanup_old_media()
            except Exception as e:
                log.warning("R2 cleanup warning (non-fatal): %s", e)
        else:
            log.error("Publish failed (container never reached FINISHED).")
            notify(f"❌ Publish failed for: {script['topic']}")
            try:
                cleanup_old_media()
            except Exception as e:
                log.warning("R2 cleanup warning: %s", e)
            sys.exit(3)
    except Exception as e:
        log.exception("Pipeline failed")
        notify(f"❌ Pipeline error: {e}")
        raise
    finally:
        if os.environ.get("CLEANUP_RENDERS", "1") == "1":
            shutil.rmtree(run_dir, ignore_errors=True)


if __name__ == "__main__":
    run_once()
