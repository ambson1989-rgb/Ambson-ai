"""
Manual comment engagement (workflow_dispatch only).

Rules:
  - Like appreciative comments (love, wow, 🔥, etc.)
  - Reply to questions and meaningful comments (max per run)
  - Short, warm, human one-liners via Gemini
  - Never re-reply the same comment id
  - Slow delays between actions to reduce IG integrity checks
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time

from google import genai
from google.genai import types
from instagram_client import get_recent_comments, reply_to_comment, like_comment

log = logging.getLogger("comment_bot")
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
STATE_FILE = os.path.join(os.path.dirname(__file__), "replied_comments.json")
LIKED_STATE_FILE = os.path.join(os.path.dirname(__file__), "liked_comments.json")

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "") or "gemini-3.5-flash-lite"
MIN_DELAY = int(os.environ.get("COMMENT_MIN_DELAY_SEC", "30"))
MAX_DELAY = int(os.environ.get("COMMENT_MAX_DELAY_SEC", "90"))

APPRECIATIVE = re.compile(
    r"(\b(love|loved|amazing|awesome|great|wow|cool|nice|beautiful|brilliant|"
    r"fascinating|interesting|mind.?blown|incredible|fantastic|super|thanks|"
    r"thank you|good one|well done|respect|fire|lit|omg|true|facts)\b)|"
    r"([❤🧡💛💚💙💜💕💖💗💘💝♥🔥👏🙌😍🤩😊👍✨⭐🌟💯🎉])",
    re.I,
)

QUESTION = re.compile(
    r"(\?|\b(what|why|how|when|where|who|which|is it|are you|can you|did|does|"
    r"do you|really|true|source|explain|mean)\b)",
    re.I,
)

SPAM = re.compile(
    r"\b(follow me|check (my|out)|dm me|onlyfans|crypto|giveaway|click (here|link)|"
    r"subscribe|promo code)\b",
    re.I,
)

SYSTEM_PROMPT = """You reply to Instagram comments on a history/science fact Reel account.
Keep replies short (ONE sentence), warm, and human — like a creator tapping reply between posts.

Rules:
- One short sentence only. No hashtags. No links.
- Questions: answer helpfully in plain words if you can; if unsure, invite them to stay for more facts.
- Praise/thanks: brief warm acknowledgment.
- If asked if you're a bot/AI: answer briefly and honestly.
- Spam/hate: do not engage substantively — output exactly: Thanks for watching!
- Output ONLY the reply text."""


def _load_ids(path: str) -> set:
    if os.path.exists(path):
        try:
            with open(path) as f:
                data = json.load(f)
            if isinstance(data, list):
                return set(data)
        except (json.JSONDecodeError, OSError):
            pass
    return set()


def _save_ids(path: str, ids: set) -> None:
    with open(path, "w") as f:
        json.dump(sorted(ids), f, indent=2)


def is_appreciative(text: str) -> bool:
    return bool(APPRECIATIVE.search(text or ""))


def is_question(text: str) -> bool:
    return bool(QUESTION.search(text or ""))


def is_spam(text: str) -> bool:
    return bool(SPAM.search(text or ""))


def needs_reply(text: str) -> bool:
    """True if this comment should get a text reply."""
    t = (text or "").strip()
    if not t or len(t) < 2:
        return False
    if is_spam(t):
        return False
    # Prefer questions and real engagement; still thank pure praise
    if is_question(t) or is_appreciative(t):
        return True
    # Longer thoughtful comments without spam
    if len(t) >= 12:
        return True
    return False


def priority(text: str) -> int:
    """Lower = handle first."""
    if is_question(text):
        return 0
    if is_appreciative(text):
        return 1
    return 2


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
    if len(text) > 140:
        text = text[:137] + "..."
    return text


def process_media_comments(media_id: str, budget: int) -> int:
    if budget <= 0:
        return 0

    replied_ids = _load_ids(STATE_FILE)
    liked_ids = _load_ids(LIKED_STATE_FILE)

    try:
        comments = get_recent_comments(media_id)
    except Exception as e:
        log.error("Failed to fetch comments for %s: %s", media_id, e)
        return 0

    log.info("Media %s: %d comment(s) from API", media_id, len(comments))

    # Sort: questions first, then appreciative, then other
    pending = []
    for comment in comments:
        cid = comment.get("id")
        text = (comment.get("text") or "").strip()
        username = comment.get("username") or ""
        if not cid or not text:
            continue
        pending.append((priority(text), comment))
    pending.sort(key=lambda x: x[0])

    count = 0
    for _, comment in pending:
        if count >= budget:
            break
        cid = comment["id"]
        text = (comment.get("text") or "").strip()
        username = comment.get("username") or ""

        # Like appreciative (even if already replied)
        if is_appreciative(text) and cid not in liked_ids:
            try:
                if like_comment(cid):
                    liked_ids.add(cid)
                    log.info("  Liked @%s: %r", username, text[:60])
                    time.sleep(random.randint(5, 15))
            except Exception as e:
                log.warning("  Like failed for %s: %s", cid, e)

        if cid in replied_ids:
            log.info("  skip already-replied %s", cid)
            continue

        if not needs_reply(text):
            log.info("  skip (no reply needed): @%s %r", username, text[:40])
            continue

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

    _save_ids(STATE_FILE, replied_ids)
    _save_ids(LIKED_STATE_FILE, liked_ids)
    return count
