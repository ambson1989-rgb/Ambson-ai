"""
End-of-Reel call-to-action: narration + on-screen text + image prompt.
Rotates phrase sets every N posts so it stays fresh.
"""

from __future__ import annotations

import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")

# Change CTA set every this many successful selections (posts).
ROTATE_EVERY = int(os.environ.get("CTA_ROTATE_EVERY", "4"))

CTA_SETS = [
    {
        "narration": (
            "If you loved this, hit follow and turn on notifications — "
            "fresh wonders land here every single day!"
        ),
        "caption_on_screen": "Follow for daily mind-blowing facts",
        "image_prompt": (
            "cinematic glowing portal of stars and ancient golden gears merging, "
            "uplifting bright cosmic energy, vertical composition, no people, "
            "no text, vibrant hopeful atmosphere"
        ),
    },
    {
        "narration": (
            "Stay tuned and follow us for more amazing stories like this every day — "
            "and tap like if this one made you smile!"
        ),
        "caption_on_screen": "Like + Follow for more every day",
        "image_prompt": (
            "warm sunrise over ancient ruins under a colorful sky, inspirational "
            "cinematic wide shot, golden light, vertical, no people, no text"
        ),
    },
    {
        "narration": (
            "Join our daily adventure through history and science — "
            "follow along and never miss the next discovery!"
        ),
        "caption_on_screen": "Follow the daily discovery",
        "image_prompt": (
            "open ancient map transforming into a starry galaxy path, magical "
            "educational adventure mood, vivid colors, vertical, no people, no text"
        ),
    },
    {
        "narration": (
            "Your support means everything — follow for more mind-blowing facts, "
            "and drop a like if you learned something new!"
        ),
        "caption_on_screen": "Like if you learned something new",
        "image_prompt": (
            "brilliant library of light with floating glowing books and nebula, "
            "joyful knowledge energy, cinematic vertical, no people, no text"
        ),
    },
    {
        "narration": (
            "We're just getting started — follow us so you don't miss tomorrow's "
            "story, and share this with a friend who loves science!"
        ),
        "caption_on_screen": "Follow · Share the wonder",
        "image_prompt": (
            "two comet trails crossing a deep blue night sky above mountains, "
            "hopeful epic cinematic mood, vertical, no people, no text"
        ),
    },
    {
        "narration": (
            "Thanks for watching! Follow for daily history and science drops, "
            "and hit like to keep the good energy going!"
        ),
        "caption_on_screen": "Thanks for watching — Follow us",
        "image_prompt": (
            "celebration of cosmic particles and golden sparks over a calm horizon, "
            "positive vibrant atmosphere, vertical cinematic, no people, no text"
        ),
    },
]


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def next_cta_beat() -> dict:
    """
    Return a beat dict: narration, image_prompt, and use caption_on_screen
    as the burned-in text (via narration field for drawtext — we pass
    caption_on_screen as the on-screen line).

    Rotation: post_count // ROTATE_EVERY indexes into CTA_SETS.
    """
    state = _load_state()
    post_count = int(state.get("post_count", 0))
    set_index = (post_count // max(ROTATE_EVERY, 1)) % len(CTA_SETS)
    cta = CTA_SETS[set_index]

    # Advance counter for next run
    state["post_count"] = post_count + 1
    state["last_cta_index"] = set_index
    _save_state(state)

    # On-screen text should be the short CTA line; narration is spoken.
    return {
        "narration": cta["narration"],
        "image_prompt": cta["image_prompt"],
        "on_screen_text": cta["caption_on_screen"],
        "cta_index": set_index,
    }
