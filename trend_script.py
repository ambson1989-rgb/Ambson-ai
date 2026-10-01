"""
Turn a niche-trending headline into a fact-careful Reel script (beats).
Uses Gemini. Falls back to None if generation fails → pipeline uses script bank.
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

SYSTEM = """You write short vertical-video scripts for an Instagram account about
history, archaeology, space, physics, and science discoveries.

Rules:
- Educational, accurate, cautious. Prefer well-established facts.
- If the headline is breaking news, phrase carefully ("reports say", "scientists published").
- No medical, financial, or legal advice. No attacks on living private individuals.
- No copyrighted song/lyric references. No celebrity gossip.
- Hook in the first narration line. 4 or 5 beats. Each narration 1–2 short sentences.
- image_prompt: cinematic, no people, vertical-friendly, detailed, no text in image.

Respond with ONLY valid JSON (no markdown):
{
  "topic": "short title under 90 chars",
  "beats": [
    {"narration": "...", "image_prompt": "..."},
    ...
  ]
}
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
    for b in beats[:6]:
        if not isinstance(b, dict):
            continue
        n = (b.get("narration") or "").strip()
        p = (b.get("image_prompt") or "").strip()
        if n and p:
            clean.append({"narration": n, "image_prompt": p})
    if len(clean) < 3:
        return None
    return {"topic": topic[:120], "beats": clean, "source": "trend"}


def generate_trend_script() -> dict[str, Any] | None:
    trends = fetch_niche_trends(max_items=10)
    if not trends:
        log.warning("No trends found")
        return None

    lines = []
    for i, t in enumerate(trends[:8], 1):
        lines.append(f"{i}. [{t['subreddit']}] {t['title']} (score {t['score']})")
    prompt = (
        "Pick the single best headline for a short educational Reel in our niche "
        "(history / science / space / archaeology). Avoid politics and pure memes.\n\n"
        + "\n".join(lines)
        + "\n\nWrite the Reel script JSON now."
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
                    max_output_tokens=1200,
                    temperature=0.4,
                ),
            )
            raw = (response.text or "").strip()
            data = _extract_json(raw)
            script = _validate_script(data) if data else None
            if script:
                log.info("Trend script topic: %s", script["topic"])
                return script
            log.warning("Invalid trend script JSON from %s: %s", model, raw[:200])
        except Exception as e:
            last_err = e
            log.warning("Trend script model %s failed: %s", model, e)
            continue

    log.error("Trend script generation failed: %s", last_err)
    return None
