"""
Reply to a small number of new comments, slowly.

Aggressive auto-replying triggers Instagram integrity checks
("confirm you're human", forced re-login). Keep limits low.
"""

import json
import logging
import os
import random
import time

from google import genai
from google.genai import types
from instagram_client import get_recent_comments, reply_to_comment

log = logging.getLogger("comment_bot")
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
STATE_FILE = os.path.join(os.path.dirname(__file__), "replied_comments.json")

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
MAX_REPLIES = int(os.environ.get("COMMENT_MAX_REPLIES", "2"))
MIN_DELAY = int(os.environ.get("COMMENT_MIN_DELAY_SEC", "45"))
MAX_DELAY = int(os.environ.get("COMMENT_MAX_DELAY_SEC", "120"))

SYSTEM_PROMPT = """You reply to Instagram comments on a history/science fact account.
Keep replies short (one sentence), warm, and human — like a creator tapping a reply
between posts. Never sarcastic or argumentative.

Rules:
- One short sentence is best.
- Don't lecture. A thank-you or light reaction is enough.
- If asked if you're a bot/AI, answer briefly and honestly.
- Skip engaging with spam, hate, or scams: reply with a simple thanks only.
- Output ONLY the reply text."""


def _load_replied_ids() -> set:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return set()


def _save_replied_ids(ids: set) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(list(ids), f)


def generate_reply(comment_text: str) -> str:
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"Comment: {comment_text}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=60,
            temperature=0.7,
        ),
    )
    text = (response.text or "").strip()
    # Hard cap length so replies look casual
    if len(text) > 140:
        text = text[:137] + "..."
    return text


def process_media_comments(media_id: str, budget: int) -> int:
    """Reply to up to `budget` new comments on this media."""
    if budget <= 0:
        return 0

    replied_ids = _load_replied_ids()
    comments = get_recent_comments(media_id)
    count = 0

    for comment in comments:
        if count >= budget:
            break
        cid = comment.get("id")
        text = (comment.get("text") or "").strip()
        if not cid or cid in replied_ids:
            continue
        # Skip empty / emoji-only noise optionally still reply to simple ones
        if not text:
            continue

        try:
            reply_text = generate_reply(text)
            if not reply_text:
                continue
            reply_to_comment(cid, reply_text)
            replied_ids.add(cid)
            count += 1
            log.info("Replied on %s: %s", media_id, reply_text[:80])
            if count < budget:
                delay = random.randint(MIN_DELAY, MAX_DELAY)
                log.info("Sleeping %ss before next reply (anti-spam)", delay)
                time.sleep(delay)
        except Exception as e:
            log.warning("Reply failed for %s: %s", cid, e)
            # Don't burn the budget on repeated API blocks
            break

    _save_replied_ids(replied_ids)
    return count
