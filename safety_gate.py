"""
Pre-publish safety check via Gemini, with DeepSeek fallback.
"""

import json
import logging
import os
import re

from llm_client import generate_text

log = logging.getLogger("safety_gate")

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


def _parse_result(raw: str) -> tuple[bool, str] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict) or "safe" not in data:
        return None
    return bool(data["safe"]), str(data.get("reason") or "")


def check_content_safe(caption: str, narration: str) -> tuple[bool, str]:
    if os.environ.get("SKIP_SAFETY_GATE", "").strip() in ("1", "true", "yes"):
        log.warning("SKIP_SAFETY_GATE set — allowing publish")
        return True, "skipped"

    user = f"Caption:\n{caption}\n\nNarration:\n{narration}"
    try:
        raw = generate_text(SYSTEM_PROMPT, user, max_tokens=120, temperature=0.1)
        parsed = _parse_result(raw)
        if parsed is None:
            log.warning("Safety gate unparseable response — fail-open: %s", raw[:160])
            return True, "unparseable-fail-open"
        safe, reason = parsed
        log.info("Safety gate: safe=%s reason=%s", safe, reason)
        return safe, reason
    except Exception as e:
        log.warning("Safety gate LLM failed — fail-open: %s", e)
        return True, f"llm-error-fail-open: {e}"
