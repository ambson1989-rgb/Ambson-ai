"""
Automated pre-publish safety check via Gemini.
Fails closed if the model response cannot be parsed.
"""

import json
import os
import re
from google import genai
from google.genai import types

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
    # Strip markdown fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # First {...} block
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # Truncated {"safe": true ... recovery
    low = text.lower()
    if '"safe"' in low:
        if re.search(r'"safe"\s*:\s*true', low):
            return {"safe": True, "reason": "recovered from partial response"}
        if re.search(r'"safe"\s*:\s*false', low):
            return {"safe": False, "reason": "recovered from partial response"}
    return None


def check_content_safe(caption: str, video_description: str) -> tuple[bool, str]:
    last_raw = ""
    for attempt in range(2):
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

    return False, f"Safety check returned an unparseable response: {last_raw[:200]}"
