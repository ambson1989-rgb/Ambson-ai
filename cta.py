"""
End-of-Reel CTA — default on EVERY reel (trend + scenic).
Stay tuned + follow, rotating wording every few posts.
"""

from __future__ import annotations

import json
import os

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")
ROTATE_EVERY = int(os.environ.get("CTA_ROTATE_EVERY", "3"))

CTA_SETS = [
    {
        "narration": (
            "Stay tuned and follow us for more like this every day — "
            "turn on notifications so you never miss the next one!"
        ),
        "caption_on_screen": "Follow · Stay tuned daily",
        "image_prompt": (
            "cinematic glowing path of light toward a bright horizon, "
            "uplifting hopeful energy, vertical, no people, no text"
        ),
    },
    {
        "narration": (
            "If this made your day, hit follow and stay with us — "
            "fresh stories and places land here every single day!"
        ),
        "caption_on_screen": "Follow for more every day",
        "image_prompt": (
            "warm sunrise over mountains under colorful sky, inspirational "
            "cinematic vertical shot, golden light, no people, no text"
        ),
    },
    {
        "narration": (
            "Stay tuned — follow us now so tomorrow's reel finds you first, "
            "and drop a like if you want more!"
        ),
        "caption_on_screen": "Like + Follow · Stay tuned",
        "image_prompt": (
            "starry night path leading forward, magical adventure mood, "
            "vivid colors, vertical, no people, no text"
        ),
    },
    {
        "narration": (
            "We're posting every day — follow along, stay tuned, "
            "and share this with someone who would love it!"
        ),
        "caption_on_screen": "Follow · Share · Stay tuned",
        "image_prompt": (
            "open glowing map transforming into a bright road, "
            "joyful travel energy, cinematic vertical, no people, no text"
        ),
    },
    {
        "narration": (
            "Don't miss what comes next — follow us, stay tuned, "
            "and turn on alerts for daily wonders!"
        ),
        "caption_on_screen": "Follow + Alerts on",
        "image_prompt": (
            "brilliant library of light with floating sparks of knowledge, "
            "joyful energy, cinematic vertical, no people, no text"
        ),
    },
]


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(updates: dict) -> None:
    state = _load_state()
    state.update(updates)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def next_cta_beat() -> dict:
    """Rotate CTA sets; always includes stay-tuned + follow language."""
    state = _load_state()
    post_count = int(state.get("post_count") or 0)
    idx = int(state.get("last_cta_index") or 0)
    # Advance set every ROTATE_EVERY posts
    set_idx = (post_count // max(1, ROTATE_EVERY)) % len(CTA_SETS)
    chosen = CTA_SETS[set_idx]
    _save_state({"last_cta_index": set_idx})
    return {
        "narration": chosen["narration"],
        "on_screen_text": chosen["caption_on_screen"],
        "image_prompt": chosen["image_prompt"],
        "set_index": set_idx,
    }
