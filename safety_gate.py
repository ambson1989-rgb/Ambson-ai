"""
Automated pre-publish safety check via Gemini.
Fails closed if the model response cannot be parsed after retries.
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
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

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


def check_content_safe(caption: str, video_description: str) -> tuple[bool, str]:
    last_raw = ""
    last_err = None

    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
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
            log.warning("Unparseable safety response (attempt %d): %s", attempt + 1, last_raw[:120])
        except (genai_errors.ServerError, genai_errors.ClientError, Exception) as e:
            last_err = e
            msg = str(e)
            # 503 high demand / transient — wait and retry
            if "503" in msg or "UNAVAILABLE" in msg or "high demand" in msg.lower():
                wait = 5 * (attempt + 1)
                log.warning("Gemini busy (%s); retry in %ss", msg[:80], wait)
                time.sleep(wait)
                continue
            # Other API errors: retry a couple times then fail closed
            if attempt < 2:
                time.sleep(3)
                continue
            return False, f"Safety check API error: {msg[:200]}"

        if attempt < 4:
            time.sleep(2)

    if last_err:
        return False, f"Safety check failed after retries: {str(last_err)[:200]}"
    return False, f"Safety check returned an unparseable response: {last_raw[:200]}"
