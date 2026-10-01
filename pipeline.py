"""
Generate and publish one Reel. Scheduled twice daily via GitHub Actions.
Only gate is automated safety_gate (unless SKIP_SAFETY_GATE=1).
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


def build_caption(topic: str) -> str:
    affiliate_link = os.environ.get("AFFILIATE_LINK", "")
    cta = "\n\nLink in bio \U0001f517" if affiliate_link else ""
    return (
        f"{topic}\n.\n.\n"
        f"#history #ancientengineering #cosmicmysteries #didyouknow "
        f"#sciencefacts #ancienthistory #spacefacts{cta}"
    )


def notify(message: str) -> None:
    url = os.environ.get("NOTIFY_WEBHOOK_URL", "").strip()
    if not url:
        return
    try:
        import requests
        requests.post(url, json={"content": message[:1900]}, timeout=15)
    except Exception as e:
        log.warning("Notify webhook failed: %s", e)


def run_once() -> None:
    script = pick_script()
    log.info("Today's script: %s", script["topic"])

    run_id = uuid.uuid4().hex[:8]
    run_dir = os.path.join(WORK_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    clip_paths = []
    full_narration = []
    video_url = None

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

        caption = build_caption(script["topic"])
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
            notify(f"✅ Published Reel: {script['topic']}\nmedia_id={media_id}")
            # Instagram has already fetched the file — free R2 storage
            try:
                delete_public_object(video_url)
                cleanup_old_media()
            except Exception as e:
                log.warning("R2 cleanup warning (non-fatal): %s", e)
        else:
            log.error("Publish failed (container never reached FINISHED).")
            notify(f"❌ Publish failed for: {script['topic']}")
            # Still prune old objects so failed retries don't fill the bucket
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
