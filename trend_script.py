"""
Unique short Reel scripts from niche trends.
Hard-hook openings for retention. Gemini → DeepSeek fallback.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from trend_scout import fetch_niche_trends
from llm_client import generate_text

log = logging.getLogger("trend_script")

STATE_FILE = os.path.join(os.path.dirname(__file__), "script_state.json")
USED_TOPICS_MAX = int(os.environ.get("USED_TOPICS_MAX", "500"))

SYSTEM = """You write SHORT vertical Instagram Reels (history / science / space / archaeology).
Goal: stop the scroll, teach one surprising fact, drive follows.

HARD LIMITS:
- Exactly 3 or 4 educational beats (then a separate CTA is added by the app).
- Each narration: ONE short sentence, max 18 words.
- Under ~45 seconds of speech total for educational beats.
- Accurate, cautious. Breaking news: "reports say" / "scientists published".
- No medical/financial/legal advice. No attacks on living private people.
- image_prompt: cinematic, no people, vertical, no text in image.

HOOK RULES (critical for views):
- Beat 1 MUST be a scroll-stopping HOOK — not a soft intro.
- Good hooks: a shocking claim, a paradox, a "scientists were wrong" angle,
  or a direct question the viewer wants answered.
- Bad hooks: "Today we talk about…", "Let's learn about…", "In this video…".
- Beat 2–3 deliver the fact clearly.
- Last educational beat can set up wonder ("and that's not even the wildest part" is OK once).

Avoid repeating Tesla Wardenclyffe, Antikythera, pigeon CMB, or any topic on the avoid list.

Respond with ONLY valid JSON:
{"topic": "short title under 90 chars", "beats": [{"narration": "...", "image_prompt": "..."}]}
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


def _topic_keys(topic: str) -> set[str]:
    norm = _normalize_topic(topic)
    keys = {norm}
    for phrase in (
        "wardenclyffe", "tesla", "antikythera", "pigeon", "cosmic microwave",
        "baghdad battery", "voynich", "great pyramid", "otzi", "iceman",
        "alexandria", "pulsar", "tunguska", "roman concrete", "pioneer anomaly",
        "gobekli", "greek fire", "stick insect", "magnetar", "helium",
        "superfluid", "quantum",
    ):
        if phrase in norm:
            keys.add(phrase)
    return keys


def _used_topics() -> set[str]:
    state = _load_state()
    used: set[str] = set()
    for x in state.get("used_topics") or []:
        used |= _topic_keys(str(x))
    return used


def is_topic_used(topic: str) -> bool:
    keys = _topic_keys(topic)
    used = _used_topics()
    if not keys:
        return False
    if keys & used:
        return True
    norm = _normalize_topic(topic)
    for u in used:
        if len(u) > 12 and (norm in u or u in norm):
            return True
    return False


def record_used_topic(topic: str) -> None:
    state = _load_state()
    used = list(state.get("used_topics") or [])
    if topic not in used:
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
    for b in beats[:4]:
        if not isinstance(b, dict):
            continue
        n = (b.get("narration") or "").strip()
        p = (b.get("image_prompt") or "").strip()
        if not n or not p:
            continue
        words = n.split()
        if len(words) > 22:
            n = " ".join(words[:22])
        clean.append({"narration": n, "image_prompt": p})
    if len(clean) < 3:
        return None
    return {"topic": topic[:120], "beats": clean, "source": "trend"}


def _generate_from_prompt(prompt: str) -> dict[str, Any] | None:
    try:
        raw = generate_text(SYSTEM, prompt, max_tokens=900, temperature=0.7)
    except Exception as e:
        log.error("Script LLM failed: %s", e)
        return None
    data = _extract_json(raw)
    script = _validate_script(data) if data else None
    if not script:
        log.warning("Invalid script JSON: %s", (raw or "")[:180])
        return None
    if is_topic_used(script["topic"]):
        log.warning("Topic already used (rejected): %s", script["topic"])
        return None
    log.info("Script topic: %s (%d beats)", script["topic"], len(script["beats"]))
    return script


def generate_trend_script() -> dict[str, Any] | None:
    used = list(_load_state().get("used_topics") or [])
    avoid = ""
    if used:
        avoid = (
            "\n\nDo NOT reuse ANY of these already-posted topics (or close variants):\n"
            + "\n".join(f"- {u}" for u in used[-40:])
        )

    trends = fetch_niche_trends(max_items=15)
    if trends:
        fresh = [t for t in trends if not is_topic_used(t["title"])]
        if not fresh:
            fresh = trends
        lines = [f"{i}. [{t['subreddit']}] {t['title']}" for i, t in enumerate(fresh[:10], 1)]
        prompt = (
            "Pick ONE fresh headline for a short educational Reel (history/science/space). "
            "Avoid politics and memes. Must be unique — never a repeat.\n"
            "Write a HARD HOOK in beat 1 (shock, paradox, or question — no soft intros).\n\n"
            + "\n".join(lines)
            + avoid
            + "\n\nWrite the Reel script JSON (3–4 short beats)."
        )
        script = _generate_from_prompt(prompt)
        if script:
            return script

    log.warning("Asking LLM to invent a unique educational topic")
    invent = (
        "Invent ONE unique educational Reel topic in history, archaeology, space, or hard science. "
        "Prefer surprising well-established facts.\n"
        "Beat 1 must be a scroll-stopping hook.\n"
        + avoid
        + "\n\nWrite the Reel script JSON (3–4 short beats). Topic must be clearly different from the avoid list."
    )
    return _generate_from_prompt(invent)
