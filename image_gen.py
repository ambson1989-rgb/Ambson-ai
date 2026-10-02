"""
Image generation with free-friendly fallbacks:

1. Pollinations (POLLINATIONS_API_KEY) — primary
2. Hugging Face Inference (HF_TOKEN) — free community token
3. Cloudflare Workers AI (CF_ACCOUNT_ID + CF_API_TOKEN) — free daily neurons

Setup (pick at least one free option):
  Pollinations: https://enter.pollinations.ai
  Hugging Face: https://huggingface.co/settings/tokens  (read token is enough)
  Cloudflare:   Dashboard → Workers AI → use account API token with Workers AI permission
"""

from __future__ import annotations

import io
import logging
import os
import time
import urllib.parse

import requests

log = logging.getLogger("image_gen")

GEN_BASE = "https://gen.pollinations.ai/image"
LEGACY_BASE = "https://image.pollinations.ai/prompt"

MODEL_CANDIDATES = [
    os.environ.get("POLLINATIONS_MODEL", "").strip() or None,
    "flux",
    "turbo",
    None,
]

# Hugging Face models that often work on free inference
HF_MODELS = [
    os.environ.get("HF_IMAGE_MODEL", "").strip() or None,
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
    "ByteDance/SDXL-Lightning",
]

# Cloudflare Workers AI model
CF_MODEL = os.environ.get(
    "CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell"
)


def _pollinations_headers() -> dict:
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    if key:
        return {"Authorization": f"Bearer {key}"}
    return {}


def _build_pollinations_urls(prompt: str, width: int, height: int, seed: int) -> list[str]:
    encoded = urllib.parse.quote(prompt)
    urls = []
    seen = set()
    for model in MODEL_CANDIDATES:
        q = f"width={width}&height={height}&seed={seed}"
        if model:
            q += f"&model={model}"
        for base in (GEN_BASE, LEGACY_BASE):
            url = f"{base}/{encoded}?{q}"
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def _save_bytes(data: bytes, out_path: str, width: int, height: int) -> str:
    if len(data) < 500:
        raise RuntimeError(f"Image payload too small ({len(data)} bytes)")
    # Optional resize to exact Reel size if Pillow available
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data)).convert("RGB")
        img = img.resize((width, height), Image.Resampling.LANCZOS)
        img.save(out_path, format="PNG", optimize=True)
    except Exception:
        with open(out_path, "wb") as f:
            f.write(data)
    log.info("Image saved: %s (%d bytes)", out_path, os.path.getsize(out_path))
    return out_path


def _try_pollinations(prompt: str, out_path: str, width: int, height: int, seed: int) -> bool:
    headers = _pollinations_headers()
    if not headers.get("Authorization"):
        log.warning("POLLINATIONS_API_KEY not set or empty")
    last_error = None
    for url in _build_pollinations_urls(prompt, width, height, seed):
        try:
            log.info("Pollinations: %s", url[:100])
            resp = requests.get(url, headers=headers, timeout=120)
            if resp.status_code == 402:
                log.warning("Pollinations 402 Payment Required")
                last_error = "402"
                continue
            if resp.status_code >= 400:
                log.warning("Pollinations HTTP %s", resp.status_code)
                last_error = str(resp.status_code)
                continue
            ct = resp.headers.get("content-type", "")
            if not ct.startswith("image/") and len(resp.content) < 1000:
                continue
            _save_bytes(resp.content, out_path, width, height)
            time.sleep(2)
            return True
        except requests.RequestException as e:
            last_error = e
            log.warning("Pollinations error: %s", e)
    log.warning("Pollinations exhausted (last=%s)", last_error)
    return False


def _try_huggingface(prompt: str, out_path: str, width: int, height: int) -> bool:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        log.info("HF_TOKEN not set — skip Hugging Face")
        return False

    models = [m for m in HF_MODELS if m]
    headers = {"Authorization": f"Bearer {token}"}

    for model in models:
        # Newer router + classic inference endpoints
        endpoints = [
            f"https://router.huggingface.co/hf-inference/models/{model}",
            f"https://api-inference.huggingface.co/models/{model}",
        ]
        payload = {
            "inputs": prompt,
            "parameters": {
                "width": min(width, 1024),
                "height": min(height, 1024),
            },
        }
        for url in endpoints:
            try:
                log.info("Hugging Face: %s", model)
                resp = requests.post(url, headers=headers, json=payload, timeout=180)
                if resp.status_code == 503:
                    # Model loading
                    log.warning("HF model loading, waiting 20s…")
                    time.sleep(20)
                    resp = requests.post(url, headers=headers, json=payload, timeout=180)
                if resp.status_code >= 400:
                    log.warning("HF HTTP %s: %s", resp.status_code, resp.text[:200])
                    continue
                ct = resp.headers.get("content-type", "")
                if "json" in ct:
                    log.warning("HF JSON response: %s", resp.text[:200])
                    continue
                _save_bytes(resp.content, out_path, width, height)
                time.sleep(2)
                return True
            except requests.RequestException as e:
                log.warning("HF error: %s", e)
    return False


def _try_cloudflare(prompt: str, out_path: str, width: int, height: int) -> bool:
    account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not account or not token:
        log.info("CF_ACCOUNT_ID / CF_API_TOKEN not set — skip Cloudflare Workers AI")
        return False

    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CF_MODEL}"
    headers = {"Authorization": f"Bearer {token}"}
    # FLUX schnell on CF often uses prompt only; steps optional
    payload = {"prompt": prompt}

    try:
        log.info("Cloudflare Workers AI: %s", CF_MODEL)
        resp = requests.post(url, headers=headers, json=payload, timeout=180)
        if resp.status_code >= 400:
            log.warning("CF AI HTTP %s: %s", resp.status_code, resp.text[:300])
            return False
        ct = resp.headers.get("content-type", "")
        if ct.startswith("image/"):
            _save_bytes(resp.content, out_path, width, height)
            return True
        # JSON with base64 image
        data = resp.json()
        result = data.get("result") or data
        import base64

        b64 = None
        if isinstance(result, dict):
            b64 = result.get("image") or result.get("b64_json")
        if isinstance(b64, list) and b64:
            b64 = b64[0]
        if not b64:
            log.warning("CF AI unexpected response keys: %s", list(data.keys())[:10])
            return False
        raw = base64.b64decode(b64)
        _save_bytes(raw, out_path, width, height)
        time.sleep(1)
        return True
    except Exception as e:
        log.warning("Cloudflare AI error: %s", e)
        return False


def generate_image(
    prompt: str,
    out_path: str,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
    retries: int = 1,
) -> str:
    seed_val = seed if seed is not None else int(time.time())
    # Slightly strengthen prompt for vertical cinematic stills
    full_prompt = f"{prompt}, vertical composition 9:16, high detail, no text, no watermark"

    if _try_pollinations(full_prompt, out_path, width, height, seed_val):
        return out_path
    if _try_huggingface(full_prompt, out_path, width, height):
        return out_path
    if _try_cloudflare(full_prompt, out_path, width, height):
        return out_path

    raise RuntimeError(
        "All image providers failed. Set at least one free option:\n"
        "  • POLLINATIONS_API_KEY — https://enter.pollinations.ai (top up free Pollen if 402)\n"
        "  • HF_TOKEN — https://huggingface.co/settings/tokens (free)\n"
        "  • CF_ACCOUNT_ID + CF_API_TOKEN — Cloudflare Workers AI free daily quota"
    )
