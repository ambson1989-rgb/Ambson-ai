"""Unique short Reel scripts. Strict no-repeat via uniqueness module."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from trend_scout import fetch_niche_trends
from llm_client import generate_text
from uniqueness import is_duplicate_topic, is_duplicate_script, _load

log = logging.getLogger("trend_script")

SYSTEM = """You write SHORT vertical Instagram Reels (history / science / space / archaeology / nature / physics).
Goal: stop the scroll, teach one surprising fact, drive follows.

HARD LIMITS:
- Exactly 3 or 4 educational beats (then a separate CTA is added by the app).
- Each narration: ONE short sentence, max 18 words.
- Under ~45 seconds of speech total for educational beats.
- Accurate, cautious. Breaking news: "reports say" / "scientists published".
- image_prompt: cinematic, no people, vertical, no text in image.

FORBIDDEN TOPICS (never write about these or close variants):
- Nikola Tesla, Wardenclyffe Tower, wireless power towers, J.P. Morgan funding Tesla
- Medical advice, diseases, treatments, genes-as-therapy, mental health disorders
- Alzheimer's, cancer, diabetes, vaccines, clinical trials
- ANY topic on the avoid list below
Prefer: space, archaeology, ancient tech (NOT Tesla), physics curiosities, animals, geology, classic science history.

HOOK RULES:
- Beat 1 MUST be a scroll-stopping HOOK — not a soft intro.

Respond with ONLY valid JSON:
{"topic": "short title under 90 chars", "beats": [{"narration": "...", "image_prompt": "..."}]}
"""


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
        raw = generate_text(SYSTEM, prompt, max_tokens=900, temperature=0.8)
    except Exception as e:
        log.error("Script LLM failed: %s", e)
        return None
    data = _extract_json(raw)
    script = _validate_script(data) if data else None
    if not script:
        log.warning("Invalid script JSON: %s", (raw or "")[:180])
        return None
    narrs = [b["narration"] for b in script["beats"]]
    prompts = [b["image_prompt"] for b in script["beats"]]
    if is_duplicate_script(script["topic"], narrs, prompts):
        log.warning("STRICT reject used/similar script: %s", script["topic"])
        return None
    log.info("Script topic: %s (%d beats)", script["topic"], len(script["beats"]))
    return script


def generate_trend_script() -> dict[str, Any] | None:
    used = list((_load().get("used_topics") or []))
    avoid = (
        "\n\nSTRICT AVOID — never reuse these or close variants:\n"
        "- Nikola Tesla / Wardenclyffe / wireless power tower\n"
        + ("\n".join(f"- {u}" for u in used[-60:]) if used else "")
        + "\nInvent a clearly DIFFERENT subject."
    )

    trends = fetch_niche_trends(max_items=20)
    if trends:
        fresh = [t for t in trends if not is_duplicate_topic(t["title"])]
        if fresh:
            lines = [
                f"{i}. [{t['subreddit']}] {t['title']}"
                for i, t in enumerate(fresh[:12], 1)
            ]
            prompt = (
                "Pick ONE fresh headline for a short educational Reel "
                "(space, archaeology, physics, nature, ancient tech — NOT Tesla, NOT medical). "
                "Must be unique.\nHard HOOK in beat 1.\n\n"
                + "\n".join(lines)
                + avoid
                + "\n\nWrite the Reel script JSON (3–4 short beats)."
            )
            script = _generate_from_prompt(prompt)
            if script:
                return script

    log.warning("Inventing a unique educational topic (no Tesla)")
    invent = (
        "Invent ONE unique educational Reel topic in space, archaeology, physics, "
        "nature, or classic science history — NOT Tesla, NOT medical.\n"
        "Beat 1 must be a scroll-stopping hook.\n"
        + avoid
        + "\n\nWrite the Reel script JSON (3–4 short beats)."
    )
    return _generate_from_prompt(invent)
