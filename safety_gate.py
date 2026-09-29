"""
Since posting is fully automatic with no human review, this is the one
cheap safeguard standing between "trending idea" and "live on your account":
an automated check, via Gemini, that flags anything risky before it publishes.

This does not replace judgment -- it catches the obvious failure modes
(copyright risk, factual overreach, policy-violating content) automatically
so a bad generation doesn't go live untouched.

Uses Gemini's free tier (gemini-2.5-flash) rather than a paid API -- fine for
this volume (one check a day), but worth knowing: free-tier prompts/outputs
may be used by Google to improve their products, unlike the paid tier. Low
stakes for a caption + video description, but worth knowing.
"""

import json
import os
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

SYSTEM_PROMPT = """You are a pre-publish safety check for an Instagram account that \
posts short-form video daily. You will be given a caption and a description of a \
video. Decide if it's safe to auto-publish with zero human review.

Flag as unsafe if the content:
- Makes a specific factual/statistical claim that isn't clearly common knowledge
- Could plausibly infringe someone else's copyright (mimics a specific existing \
  creator's format/audio/likeness too closely, rather than being a generic take \
  on a trend)
- Touches health, medical, financial, legal, or safety advice
- Could be read as mocking, targeting, or making claims about a real, named person
- Contains anything that could violate a platform's community guidelines

Respond with ONLY a JSON object: {"safe": true or false, "reason": "one sentence"}"""


def check_content_safe(caption: str, video_description: str) -> tuple[bool, str]:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=f"Caption: {caption}\n\nVideo description: {video_description}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=200,
        ),
    )
    text = (response.text or "").strip()
    try:
        result = json.loads(text)
        return bool(result["safe"]), result.get("reason", "")
    except (json.JSONDecodeError, KeyError):
        # Fail closed: if the check itself breaks, don't publish.
        return False, f"Safety check returned an unparseable response: {text[:200]}"
