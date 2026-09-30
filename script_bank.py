"""
Fact-checked scripts, broken into beats -- each beat is one narration line
plus a matching image prompt. pick_script() rotates through SCRIPTS, one per
calendar day, same pattern as the old trend_research.py.

Ask for a refill once you're through these three -- new batches get the same
fact-check pass these did (sources checked against the original claims made
in chat before they were encoded here).
"""

import json
import os
from datetime import date

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")

SCRIPTS = [
    {
        "topic": "The Antikythera mechanism — the 2,000-year-old Greek analog computer",
        "beats": [
            {
                "narration": "This 2,000-year-old machine shouldn't exist.",
                "image_prompt": (
                    "cinematic photo of a corroded ancient bronze mechanical device "
                    "with intricate gears, museum lighting, dark background, "
                    "mysterious atmosphere, highly detailed, no people"
                ),
            },
            {
                "narration": (
                    "In 1901, sponge divers found a corroded block of bronze "
                    "off the Greek island of Antikythera."
                ),
                "image_prompt": (
                    "cinematic underwater scene, ancient shipwreck on Mediterranean "
                    "seabed, sunlight rays through water, bronze artifact fragment, "
                    "no people, moody atmospheric lighting"
                ),
            },
            {
                "narration": (
                    "Inside were more than 30 hand-driven bronze gears, modeling "
                    "the cycles of the Moon, Sun, and known planets."
                ),
                "image_prompt": (
                    "extreme close-up of intricate ancient bronze gear mechanism, "
                    "cosmic diagram of sun moon and planets etched into metal, "
                    "warm golden light, highly detailed engineering, no people"
                ),
            },
            {
                "narration": (
                    "Nothing this mechanically complex is known from before "
                    "the fourteenth century."
                ),
                "image_prompt": (
                    "dramatic split composition, ancient bronze clockwork gears "
                    "contrasted with a medieval European clock tower, mysterious "
                    "dark cinematic lighting, no people"
                ),
            },
            {
                "narration": "Who built it is still unconfirmed.",
                "image_prompt": (
                    "ancient Greek ruins silhouette at dusk under a starry night "
                    "sky, contemplative and mysterious mood, wide cinematic shot, "
                    "no people"
                ),
            },
        ],
    },
    {
        "topic": "Tesla's Wardenclyffe Tower and why J.P. Morgan pulled funding",
        "beats": [
            {
                "narration": "Tesla's tower was meant to talk across the Atlantic.",
                "image_prompt": (
                    "cinematic photo of a tall early 1900s wooden and steel "
                    "wireless transmission tower against a dramatic sky, sepia "
                    "toned, atmospheric lighting, no people"
                ),
            },
            {
                "narration": (
                    "In 1901, J.P. Morgan invested $150,000 in it — the aim was "
                    "sending messages across the ocean without cables."
                ),
                "image_prompt": (
                    "vintage early 20th century laboratory with wireless "
                    "transmission equipment, glowing electrical coils, dramatic "
                    "sepia cinematic lighting, no people"
                ),
            },
            {
                "narration": (
                    "When Tesla wanted to expand toward wireless power, Morgan "
                    "refused more funding — the project was abandoned in 1906, "
                    "and the tower was demolished for scrap in 1917."
                ),
                "image_prompt": (
                    "abandoned decaying wooden transmission tower at dusk, "
                    "overgrown lot, melancholic cinematic lighting, no people"
                ),
            },
            {
                "narration": (
                    "The popular 'free energy for the world' story is disputed "
                    "— one historian says Tesla never planned free energy."
                ),
                "image_prompt": (
                    "old sepia toned newspaper clippings and blueprint sketches "
                    "of an electrical tower scattered on a wooden desk, dramatic "
                    "side lighting, no people"
                ),
            },
        ],
    },
    {
        "topic": "The pigeon-droppings discovery of the cosmic microwave background",
        "beats": [
            {
                "narration": "They cleaned pigeon droppings... and heard the Big Bang.",
                "image_prompt": (
                    "cinematic photo of a large 1960s horn-shaped radio antenna "
                    "against a starry night sky, dramatic wide shot, no people"
                ),
            },
            {
                "narration": (
                    "In 1964, Bell Labs researchers picked up a steady hiss "
                    "from every part of the sky."
                ),
                "image_prompt": (
                    "vintage 1960s scientific laboratory control room with "
                    "analog dials and oscilloscope screens, warm dramatic "
                    "lighting, no people"
                ),
            },
            {
                "narration": (
                    "They checked for city interference and cleaned out "
                    "nesting pigeons, but the noise stayed."
                ),
                "image_prompt": (
                    "close-up of a large metal horn antenna structure, birds "
                    "flying away, moody documentary style lighting, no people"
                ),
            },
            {
                "narration": (
                    "It was leftover radiation from the universe's early days "
                    "— a discovery that earned the 1978 Nobel Prize in Physics."
                ),
                "image_prompt": (
                    "epic cosmic scene of the early universe, glowing radiation "
                    "background, stars and nebula, deep space cinematic wide shot"
                ),
            },
        ],
    },
]


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"last_index": -1, "last_run_date": None}


def _save_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def pick_script() -> dict:
    """Rotates through SCRIPTS, one per calendar day, wrapping around."""
    state = _load_state()
    today = date.today().isoformat()

    if state["last_run_date"] == today:
        return SCRIPTS[state["last_index"] % len(SCRIPTS)]

    next_index = (state["last_index"] + 1) % len(SCRIPTS)
    _save_state({"last_index": next_index, "last_run_date": today})
    return SCRIPTS[next_index]
