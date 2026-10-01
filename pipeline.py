"""
Generate and publish one unique Reel every run.

Always prefers fresh niche trends (CONTENT_MODE=auto by default).
Never intentionally re-posts the same topic. Videos stay under ~60 seconds.
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
from trend_script import generate_trend_script, record_used_topic

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pipeline")

WORK_DIR = os.path.join(os.path.dirname(__file__), "renders")
os.makedirs(WORK_DIR, exist_ok=True)


def build_caption(topic: str, source: str = "trend") -> str:
    affiliate_link = os.environ.get("AFFILIATE_LINK", "")
    cta = "\n\nLink in bio \U0001f517" if affiliate_link else ""
    tags = (
        "#history #sciencefacts #didyouknow #spacefacts "
        "#ancienthistory #cosmicmysteries #trending"
    )
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
    """Always auto: unique trend script. Bank only as last-resort emergency."""
    mode = os.environ.get("CONTENT_MODE", "auto").strip().lower()
    log.info("CONTENT_MODE=%s", mode)

    # Always try trend first (even if mode is bank — user wants unique always)
    for attempt in range(2):
        try:
            script = generate_trend_script()
            if script:
                return script
            log.warning("Trend attempt %d produced no script", attempt + 1)
        except Exception as e:
            log.warning("Trend attempt %d failed: %s", attempt + 1, e)

    # Emergency fallback only — still advances bank so we don't hard-crash
    log.warning("Falling back to script bank (emergency only)")
    from script_bank import pick_script
    script = dict(pick_script())
    script["source"] = "bank"
    return script


def run_once() -> None:
    script = select_script()
    source = script.get("source", "trend")
    log.info("Selected [%s]: %s", source, script["topic"])

    run_id = uuid.uuid4().hex[:8]
    run_dir = os.path.join(WORK_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    clip_paths = []
    full_narration = []

    try:
        beats = list(script["beats"])[:4]  # hard cap educational beats
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

        # Final CTA beat
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

        caption = build_caption(script["topic"], source=source)
        safe, reason = check_content_safe(
            caption, " ".join(full_narration[:-1]) or " ".join(full_narration)
        )
        if not safe:
            log.error("Safety gate blocked this post: %s", reason)
            notify(f"⚠️ Safety gate blocked post: {script['topic']}\nReason: {reason}")
            sys.exit(2)

        video_url = upload_to_public_host(final_path)
        log.info("Uploaded: %s", video_url)
        media_id = publish_reel(video_url, caption, is_ai_generated=True)

        if media_id:
            log.info("Published: %s", media_id)
            # Mark topic used only after successful publish
            try:
                record_used_topic(script["topic"])
            except Exception as e:
                log.warning("Could not record used topic: %s", e)
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
