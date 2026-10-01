"""
Turn a niche-trending headline into a short Reel script (under ~50s of speech).
Always unique: skips topics already used. Never falls back to repeating bank topics
when trends are available.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from google import genai
from google.genai import types

from trend_scout import fetch_niche_trends

log = logging.getLogger("trend_script")

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")

# Keep a long history of used topics so we never re-post the same angle.
USED_TOPICS_MAX = int(os.environ.get("USED_TOPICS_MAX", "500"))

_DEFAULT_MODELS = [
    os.environ.get("GEMINI_MODEL", "").strip(),
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-2.5-flash",
]
_seen: set[str] = set()
MODEL_CANDIDATES = [m for m in _DEFAULT_MODELS if m and not (m in _seen or _seen.add(m))]

SYSTEM = """You write SHORT vertical Instagram Reels (history / science / space / archaeology).

HARD LIMITS (must obey):
- Exactly 3 or 4 beats of educational content (not more).
- Each narration: ONE short sentence, max 18 words.
- Total spoken educational content must fit in under 45 seconds when read aloud.
- Hook in beat 1. No filler.
- Educational, accurate, cautious. Breaking news: use "reports say" / "scientists published".
- No medical, financial, or legal advice. No attacks on living private people.
- No celebrity gossip. No song lyrics.
- image_prompt: cinematic, no people, vertical, detailed, no text in image.

Respond with ONLY valid JSON (no markdown):
{
  "topic": "short title under 90 chars",
  "beats": [
    {"narration": "...", "image_prompt": "..."}
  ]
}
"""


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


def _normalize_topic(topic: str) -> str:
    t = re.sub(r"\s+", " ", (topic or "").lower().strip())
    t = re.sub(r"[^a-z0-9\s]", "", t)
    return t[:100]


def _used_topics() -> set[str]:
    state = _load_state()
    return {_normalize_topic(x) for x in (state.get("used_topics") or []) if x}


def record_used_topic(topic: str) -> None:
    state = _load_state()
    used = list(state.get("used_topics") or [])
    used.append(topic)
    used = used[-USED_TOPICS_MAX:]
    _save_state({"used_topics": used})


def _extract_json(text: str) -> dict | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _validate_script(data: dict) -> dict | None:
    if not isinstance(data, dict):
        return None
    topic = (data.get("topic") or "").strip()
    beats = data.get("beats")
    if not topic or not isinstance(beats, list) or len(beats) < 3:
        return None
    clean = []
    for b in beats[:4]:  # hard cap 4 educational beats
        if not isinstance(b, dict):
            continue
        n = (b.get("narration") or "").strip()
        p = (b.get("image_prompt") or "").strip()
        if not n or not p:
            continue
        # Trim runaway sentences
        words = n.split()
        if len(words) > 22:
            n = " ".join(words[:22])
        clean.append({"narration": n, "image_prompt": p})
    if len(clean) < 3:
        return None
    return {"topic": topic[:120], "beats": clean, "source": "trend"}


def generate_trend_script() -> dict[str, Any] | None:
    used = _used_topics()
    trends = fetch_niche_trends(max_items=15)
    if not trends:
        log.warning("No trends found")
        return None

    # Drop headlines that match already-used topics
    fresh = []
    for t in trends:
        norm = _normalize_topic(t["title"])
        if norm and norm not in used and not any(norm in u or u in norm for u in used if len(u) > 20):
            fresh.append(t)
    if not fresh:
        log.warning("All trend headlines already used; trying full list with Gemini uniqueness")
        fresh = trends

    lines = []
    for i, t in enumerate(fresh[:10], 1):
        lines.append(f"{i}. [{t['subreddit']}] {t['title']} (score {t['score']})")

    used_sample = list(used)[-30:]
    avoid = ""
    if used_sample:
        avoid = (
            "\n\nDo NOT reuse any of these already-posted topics (pick something different):\n"
            + "\n".join(f"- {u}" for u in used_sample[-15:])
        )

    prompt = (
        "Pick ONE fresh headline for a short educational Reel (history/science/space). "
        "Avoid politics and pure memes. Must be unique — not a repeat of past posts.\n\n"
        + "\n".join(lines)
        + avoid
        + "\n\nWrite the Reel script JSON now (3–4 short beats only)."
    )

    last_err = None
    for model in MODEL_CANDIDATES:
        try:
            log.info("Generating trend script with %s", model)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM,
                    max_output_tokens=900,
                    temperature=0.5,
                ),
            )
            raw = (response.text or "").strip()
            data = _extract_json(raw)
            script = _validate_script(data) if data else None
            if not script:
                log.warning("Invalid trend script JSON from %s: %s", model, raw[:200])
                continue
            norm = _normalize_topic(script["topic"])
            if norm in used:
                log.warning("Generated topic already used: %s — retrying other model", script["topic"])
                continue
            log.info("Trend script topic: %s (%d beats)", script["topic"], len(script["beats"]))
            return script
        except Exception as e:
            last_err = e
            log.warning("Trend script model %s failed: %s", model, e)
            continue

    log.error("Trend script generation failed: %s", last_err)
    return None
