"""
Automated pre-publish safety check via Gemini.

On persistent 503/high-demand after retries, allows publish for our curated
script_bank content (fail-open) so infrastructure can be tested. Set
SKIP_SAFETY_GATE=1 to skip entirely (testing only).
"""

import json
import logging
import os
import re
import time
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

log = logging.getLogger("safety_gate")
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Prefer flash-lite first (often less congested), then flash.
_DEFAULT_MODELS = [
    os.environ.get("GEMINI_MODEL", "").strip(),
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-2.5-flash",
]
MODEL_CANDIDATES = [m for m in _DEFAULT_MODELS if m]
# de-dupe preserve order
_seen = set()
MODEL_CANDIDATES = [m for m in MODEL_CANDIDATES if not (m in _seen or _seen.add(m))]

SYSTEM_PROMPT = """You are a pre-publish safety check for an Instagram account that
posts short educational history/science videos. You will be given a caption and
a video narration. Decide if it's safe to auto-publish.

Flag as unsafe ONLY if the content:
- Makes a specific medical, financial, or legal claim as advice
- Clearly targets or harasses a real named living person
- Is obvious spam, scams, or sexual content involving minors
- Is a near-copy of a specific known creator's proprietary format

Do NOT flag normal educational history, archaeology, astronomy, or engineering
facts that are widely published. Those are safe.

Respond with ONLY a single-line JSON object, no markdown, no extra text:
{"safe": true, "reason": "ok"}
or
{"safe": false, "reason": "short reason"}
"""


def _extract_json(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    low = text.lower()
    if '"safe"' in low:
        if re.search(r'"safe"\s*:\s*true', low):
            return {"safe": True, "reason": "recovered from partial response"}
        if re.search(r'"safe"\s*:\s*false', low):
            return {"safe": False, "reason": "recovered from partial response"}
    return None


def _is_capacity_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        x in msg
        for x in ("503", "unavailable", "high demand", "resource_exhausted", "429")
    )


def check_content_safe(caption: str, video_description: str) -> tuple[bool, str]:
    if os.environ.get("SKIP_SAFETY_GATE", "").strip() in ("1", "true", "yes"):
        log.warning("SKIP_SAFETY_GATE set — allowing post without Gemini check")
        return True, "skipped by SKIP_SAFETY_GATE"

    last_raw = ""
    capacity_failures = 0

    for model in MODEL_CANDIDATES:
        for attempt in range(3):
            try:
                log.info("Safety check model=%s attempt=%d", model, attempt + 1)
                response = client.models.generate_content(
                    model=model,
                    contents=f"Caption: {caption}\n\nVideo description: {video_description}",
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        max_output_tokens=256,
                        temperature=0.1,
                    ),
                )
                last_raw = (response.text or "").strip()
                result = _extract_json(last_raw)
                if result is not None and "safe" in result:
                    return bool(result["safe"]), str(result.get("reason", ""))
                log.warning("Unparseable response: %s", last_raw[:120])
            except Exception as e:
                if _is_capacity_error(e):
                    capacity_failures += 1
                    wait = 4 * (attempt + 1)
                    log.warning("Gemini capacity error on %s: %s; sleep %ss", model, str(e)[:100], wait)
                    time.sleep(wait)
                    continue
                log.warning("Safety API error on %s: %s", model, e)
                if attempt < 2:
                    time.sleep(2)
                    continue
            time.sleep(1)

    # Content comes from our fixed script_bank — allow through if Gemini is down.
    if capacity_failures > 0:
        log.warning(
            "Gemini unavailable after retries (%d capacity errors). "
            "Fail-open for curated script_bank content.",
            capacity_failures,
        )
        return True, "gemini unavailable — fail-open for curated scripts"

    return False, f"Safety check returned an unparseable response: {last_raw[:200]}"
