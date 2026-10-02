"""
Shared text LLM helper: Gemini first, DeepSeek as fallback.

DeepSeek is OpenAI-compatible (text only — not image generation).
Set DEEPSEEK_API_KEY in GitHub secrets for backup when Gemini is down/rate-limited.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests

log = logging.getLogger("llm_client")

DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip() or "deepseek-chat"


def _gemini_models() -> list[str]:
    models = [
        os.environ.get("GEMINI_MODEL", "").strip(),
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
        "gemini-2.5-flash-lite",
        "gemini-3.8-flash",
        "gemini-2.5-flash",
    ]
    seen: set[str] = set()
    return [m for m in models if m and not (m in seen or seen.add(m))]


def _generate_gemini(system: str, user: str, max_tokens: int, temperature: float) -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        log.warning("GEMINI_API_KEY not set")
        return None
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        last_err = None
        for model in _gemini_models():
            try:
                log.info("LLM Gemini: %s", model)
                response = client.models.generate_content(
                    model=model,
                    contents=user,
                    config=types.GenerateContentConfig(
                        system_instruction=system or None,
                        max_output_tokens=max_tokens,
                        temperature=temperature,
                    ),
                )
                text = (response.text or "").strip()
                if text:
                    return text
            except Exception as e:
                last_err = e
                log.warning("Gemini %s failed: %s", model, e)
        if last_err:
            log.warning("All Gemini models failed: %s", last_err)
    except Exception as e:
        log.warning("Gemini client error: %s", e)
    return None


def _generate_deepseek(system: str, user: str, max_tokens: int, temperature: float) -> str | None:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        log.info("DEEPSEEK_API_KEY not set — skip DeepSeek fallback")
        return None

    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    url = f"{DEEPSEEK_BASE}/v1/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    try:
        log.info("LLM DeepSeek: %s", DEEPSEEK_MODEL)
        resp = requests.post(url, headers=headers, json=payload, timeout=90)
        if resp.status_code >= 400:
            log.warning("DeepSeek HTTP %s: %s", resp.status_code, resp.text[:250])
            return None
        data = resp.json()
        text = (
            ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        ).strip()
        if text:
            return text
        log.warning("DeepSeek empty response: %s", str(data)[:200])
    except Exception as e:
        log.warning("DeepSeek error: %s", e)
    return None


def generate_text(
    system: str,
    user: str,
    *,
    max_tokens: int = 900,
    temperature: float = 0.6,
) -> str:
    """Try Gemini, then DeepSeek. Raises if both fail."""
    text = _generate_gemini(system, user, max_tokens, temperature)
    if text:
        return text
    text = _generate_deepseek(system, user, max_tokens, temperature)
    if text:
        return text
    raise RuntimeError(
        "All text LLMs failed (Gemini + DeepSeek). "
        "Check GEMINI_API_KEY and/or DEEPSEEK_API_KEY."
    )
