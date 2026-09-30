"""
Image generation via Pollinations.ai.

As of late 2026, Flux + nologo/private on the anonymous endpoint often returns
HTTP 402 (Payment Required / insufficient Pollen). This module:

1. Uses POLLINATIONS_API_KEY if set (recommended — free key from enter.pollinations.ai)
2. Tries cheaper/free-friendly models and endpoints
3. Waits between attempts to respect rate limits

Get a free key: https://enter.pollinations.ai
Add GitHub secret: POLLINATIONS_API_KEY
"""

import logging
import os
import time
import urllib.parse
import requests

log = logging.getLogger("image_gen")

# Prefer the unified API when a key is present; fall back to legacy URL.
GEN_BASE = "https://gen.pollinations.ai/image"
LEGACY_BASE = "https://image.pollinations.ai/prompt"

# Models ordered from preferred → more likely free/cheap on limited accounts.
MODEL_CANDIDATES = [
    os.environ.get("POLLINATIONS_MODEL", "").strip() or None,
    "flux",
    "turbo",
    None,  # no model param = server default
]


def _headers() -> dict:
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


def _build_urls(prompt: str, width: int, height: int, seed: int) -> list[str]:
    encoded = urllib.parse.quote(prompt)
    urls = []
    seen = set()

    for model in MODEL_CANDIDATES:
        # Authenticated / unified endpoint
        q = f"width={width}&height={height}&seed={seed}"
        if model:
            q += f"&model={model}"
        for base in (GEN_BASE, LEGACY_BASE):
            url = f"{base}/{encoded}?{q}"
            if url not in seen:
                seen.add(url)
                urls.append(url)

        # Legacy-style extras (may 402 without pollen — tried last per model)
        legacy_extra = (
            f"{LEGACY_BASE}/{encoded}"
            f"?width={width}&height={height}&seed={seed}"
            f"&nologo=true&safe=true"
        )
        if model:
            legacy_extra += f"&model={model}"
        if legacy_extra not in seen:
            seen.add(legacy_extra)
            urls.append(legacy_extra)

    return urls


def generate_image(
    prompt: str,
    out_path: str,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
    retries: int = 1,
) -> str:
    seed_val = seed if seed is not None else int(time.time())
    headers = _headers()
    urls = _build_urls(prompt, width, height, seed_val)
    last_error = None

    if not headers.get("Authorization"):
        log.warning(
            "POLLINATIONS_API_KEY not set — anonymous calls often hit 402. "
            "Get a free key at https://enter.pollinations.ai and add the secret."
        )

    for url in urls:
        for attempt in range(retries + 1):
            try:
                log.info("Image request attempt (model path): %s", url[:120])
                resp = requests.get(url, headers=headers, timeout=120)
                if resp.status_code == 402:
                    last_error = requests.HTTPError(
                        f"402 Payment Required for {url[:80]}...", response=resp
                    )
                    log.warning("402 from Pollinations — trying next option")
                    break  # next URL/model
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if not content_type.startswith("image/") and len(resp.content) < 1000:
                    last_error = RuntimeError(
                        f"Non-image response ({content_type}): {resp.text[:200]}"
                    )
                    break
                with open(out_path, "wb") as f:
                    f.write(resp.content)
                log.info("Image saved: %s (%d bytes)", out_path, len(resp.content))
                # Pace requests so multi-beat reels stay under rate limits
                time.sleep(3)
                return out_path
            except requests.RequestException as e:
                last_error = e
                if attempt < retries:
                    time.sleep(12)

    raise RuntimeError(
        f"Pollinations image generation failed after all fallbacks: {last_error}. "
        f"Add POLLINATIONS_API_KEY from https://enter.pollinations.ai "
        f"(free signup; top up Pollen only if the free balance runs out)."
    )
