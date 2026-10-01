"""
Reply to a limited number of new comments, slowly.
"""

import json
import logging
import os
import random
import time

from google import genai
from google.genai import types
from instagram_client import get_recent_comments, reply_to_comment, IG_USER_ID

log = logging.getLogger("comment_bot")
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
STATE_FILE = os.path.join(os.path.dirname(__file__), "replied_comments.json")

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MIN_DELAY = int(os.environ.get("COMMENT_MIN_DELAY_SEC", "30"))
MAX_DELAY = int(os.environ.get("COMMENT_MAX_DELAY_SEC", "90"))

SYSTEM_PROMPT = """You reply to Instagram comments on a history/science fact account.
Keep replies short (one sentence), warm, and human.
Rules:
- One short sentence.
- Thank-you or light reaction is enough.
- If asked if you're a bot/AI, answer briefly and honestly.
- Spam/hate: short neutral thanks only.
- Output ONLY the reply text."""


def _load_replied_ids() -> set:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return set(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def _save_replied_ids(ids: set) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(list(ids), f)


def generate_reply(comment_text: str) -> str:
    response = client.models.generate_content(
        model=GEMINI_MODEL or "gemini-3.5-flash-lite",
        contents=f"Comment: {comment_text}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=60,
            temperature=0.7,
        ),
    )
    text = (response.text or "").strip()
    if len(text) > 140:
        text = text[:137] + "..."
    return text


def process_media_comments(media_id: str, budget: int) -> int:
    if budget <= 0:
        return 0

    replied_ids = _load_replied_ids()
    try:
        comments = get_recent_comments(media_id)
    except Exception as e:
        log.error("Failed to fetch comments for %s: %s", media_id, e)
        return 0

    log.info("Media %s: %d comment(s) from API", media_id, len(comments))
    count = 0

    for comment in comments:
        if count >= budget:
            break
        cid = comment.get("id")
        text = (comment.get("text") or "").strip()
        username = comment.get("username") or ""
        if not cid:
            continue
        if cid in replied_ids:
            log.info("  skip already-replied %s", cid)
            continue
        if not text:
            continue
        # Don't reply to our own comments
        # (username may not always match; still try)

        try:
            reply_text = generate_reply(text)
            if not reply_text:
                log.warning("  empty Gemini reply for %s", cid)
                continue
            reply_id = reply_to_comment(cid, reply_text)
            replied_ids.add(cid)
            count += 1
            log.info(
                "  Replied to @%s (%s) -> %r (reply_id=%s)",
                username,
                cid,
                reply_text[:80],
                reply_id,
            )
            if count < budget:
                delay = random.randint(MIN_DELAY, MAX_DELAY)
                log.info("  Sleeping %ss before next reply", delay)
                time.sleep(delay)
        except Exception as e:
            log.error("  Reply failed for %s: %s", cid, e)
            break

    _save_replied_ids(replied_ids)
    return count
