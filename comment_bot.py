"""
Polls recent media for new comments and replies automatically.

Design notes on the "don't expose the workflow" requirement:
- The system prompt below keeps replies focused on being warm/helpful --
  it never narrates internal steps ("I analyzed your comment and...") in
  the reply itself, which is just normal UX, not deception.
- It does NOT instruct the model to deny being automated if someone directly
  and sincerely asks. Posing as a human when asked outright crosses from
  "clean UX" into deception, and Instagram's own AI-content-label push this
  year points the other way -- so if asked, it gives a brief, honest answer
  and moves on rather than lying about it.
"""

import json
import os
from google import genai
from google.genai import types
from instagram_client import get_recent_comments, reply_to_comment

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
STATE_FILE = os.path.join(os.path.dirname(__file__), "replied_comments.json")

SYSTEM_PROMPT = """You reply to Instagram comments on behalf of a personal content \
account. Every reply must be either genuinely grateful/kind, or purely informational \
and factual. Never sarcastic, never dismissive, never argumentative, never abusive.

Rules:
- Keep it short -- one or two sentences, like a real comment reply.
- Never state or imply a specific fact you're not confident is true. If you don't \
  know something, say so warmly rather than guessing.
- Don't narrate your own process or reasoning in the reply.
- If someone sincerely and directly asks whether this account/replies are \
  automated or AI-run, answer briefly and honestly -- don't deny it.
- If a comment is hostile, spam, or off-topic, reply with a short, neutral, \
  kind non-engagement (e.g. thanking them for stopping by) rather than \
  arguing or ignoring it silently.
- Output ONLY the reply text, nothing else."""


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
        model="gemini-2.5-flash",
        contents=f"Comment: {comment_text}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=150,
        ),
    )
    return (response.text or "").strip()


def process_media_comments(media_id: str) -> int:
    """Replies to any new comments on a given media ID. Returns count replied."""
    replied_ids = _load_replied_ids()
    comments = get_recent_comments(media_id)
    count = 0

    for comment in comments:
        if comment["id"] in replied_ids:
            continue
        reply_text = generate_reply(comment["text"])
        reply_to_comment(comment["id"], reply_text)
        replied_ids.add(comment["id"])
        count += 1

    _save_replied_ids(replied_ids)
    return count
