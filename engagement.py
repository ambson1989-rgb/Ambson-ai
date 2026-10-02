"""
Engagement captions + rotating hashtag packs for growth.

- Caption ends with a clear question / save / tag ask (rotated).
- Hashtag packs cycle by niche cluster so posts don't look identical.
"""

from __future__ import annotations

import json
import os
import re

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")

# Rotate engagement prompt every N posts
ENGAGE_ROTATE_EVERY = int(os.environ.get("ENGAGE_ROTATE_EVERY", "1"))

ENGAGEMENT_LINES = [
    "Would you have believed this? Comment YES or NO ❓",
    "Save this for later — which fact should we cover next? ⭐",
    "Tag someone who needs to see this ὄ9",
    "Did this blow your mind? Drop a ❤️ if it did",
    "Follow for a new mind-blowing fact every day Ὠ0",
    "What surprised you most? Tell us in the comments Ὂc",
    "Double-tap if you learned something new today ✅",
    "Share this with a friend who loves science ἰc",
]

HASHTAG_PACKS = {
    "space": (
        "#spacefacts #astronomy #cosmos #universe #nasa "
        "#didyouknow #sciencefacts #mindblown #reels #explore"
    ),
    "history": (
        "#historyfacts #ancienthistory #archaeology #didyouknow "
        "#historytok #ancientcivilizations #sciencefacts #reels #explore"
    ),
    "nature": (
        "#naturefacts #wildlife #biology #didyouknow #amazingnature "
        "#sciencefacts #mindblown #reels #explorepage"
    ),
    "tech": (
        "#sciencefacts #physics #engineering #innovation #didyouknow "
        "#techfacts #mindblown #reels #explore"
    ),
    "default": (
        "#didyouknow #sciencefacts #historyfacts #mindblown "
        "#interestingfacts #dailyfacts #reels #explore #viral"
    ),
}

_SPACE = re.compile(
    r"\b(space|nasa|mars|moon|star|galaxy|cosmos|orbit|planet|asteroid|"
    r"nebula|black hole|pulsar|magnetar|helium|quantum|iss|astronaut)\b",
    re.I,
)
_HISTORY = re.compile(
    r"\b(ancient|history|roman|greek|egypt|pyramid|tomb|civilization|"
    r"archaeolog|manuscript|medieval|empire|pharaoh|artifact)\b",
    re.I,
)
_NATURE = re.compile(
    r"\b(insect|animal|bird|ocean|tree|forest|species|biology|dna|"
    r"whale|shark|plant|fossil|evolution)\b",
    re.I,
)
_TECH = re.compile(
    r"\b(computer|engine|machine|electric|battery|robot|ai|chip|"
    r"quantum|superfluid|invention|tesla|radio)\b",
    re.I,
)


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


def detect_niche(topic: str) -> str:
    t = topic or ""
    scores = {
        "space": 1 if _SPACE.search(t) else 0,
        "history": 1 if _HISTORY.search(t) else 0,
        "nature": 1 if _NATURE.search(t) else 0,
        "tech": 1 if _TECH.search(t) else 0,
    }
    best = max(scores, key=scores.get)
    return best if scores[best] else "default"


def next_engagement_line() -> str:
    state = _load_state()
    idx = int(state.get("engage_index", 0))
    line = ENGAGEMENT_LINES[idx % len(ENGAGEMENT_LINES)]
    state["engage_index"] = idx + max(ENGAGE_ROTATE_EVERY, 1)
    _save_state({"engage_index": state["engage_index"]})
    return line


def hashtags_for(topic: str) -> str:
    niche = detect_niche(topic)
    return HASHTAG_PACKS.get(niche, HASHTAG_PACKS["default"])


def build_growth_caption(topic: str) -> str:
    """Topic + engagement ask + niche hashtags + optional link-in-bio."""
    engage = next_engagement_line()
    tags = hashtags_for(topic)
    affiliate = os.environ.get("AFFILIATE_LINK", "").strip()
    link_line = "\n\nLink in bio \U0001f517" if affiliate else ""
    return f"{topic}\n\n{engage}\n.\n.\n{tags}{link_line}"
