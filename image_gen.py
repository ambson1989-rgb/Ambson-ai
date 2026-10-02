"""
Image generation fallbacks (all free-tier friendly):

1. Hugging Face Inference Providers (HF_TOKEN) — preferred
2. Pollinations (POLLINATIONS_API_KEY)
3. Cloudflare Workers AI (CF_ACCOUNT_ID + CF_API_TOKEN)

HF_TOKEN must be a **fine-grained** token with preset **Inference**
(permission: "Make calls to Inference Providers").
Create one: https://huggingface.co/settings/tokens/new?preset=inference
"""

from __future__ import annotations

import base64
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

HF_MODELS = [
    m
    for m in [
        os.environ.get("HF_IMAGE_MODEL", "").strip() or None,
        "black-forest-labs/FLUX.1-schnell",
        "stabilityai/stable-diffusion-xl-base-1.0",
    ]
    if m
]

CF_MODEL = os.environ.get(
    "CF_IMAGE_MODEL", "@cf/black-forest-labs/flux-1-schnell"
)


def _save_bytes(data: bytes, out_path: str, width: int, height: int) -> str:
    if len(data) < 500:
        raise RuntimeError(f"Image payload too small ({len(data)} bytes)")
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


def _try_huggingface(prompt: str, out_path: str, width: int, height: int) -> bool:
    token = os.environ.get("HF_TOKEN", "").strip()
    if not token:
        log.info("HF_TOKEN not set — skip Hugging Face")
        return False

    # Preferred: official client (routes to Inference Providers)
    try:
        from huggingface_hub import InferenceClient

        client = InferenceClient(token=token)
        for model in HF_MODELS:
            try:
                log.info("Hugging Face InferenceClient: %s", model)
                image = client.text_to_image(
                    prompt,
                    model=model,
                )
                buf = io.BytesIO()
                image.save(buf, format="PNG")
                _save_bytes(buf.getvalue(), out_path, width, height)
                time.sleep(1)
                return True
            except Exception as e:
                msg = str(e)
                if "403" in msg or "permission" in msg.lower() or "sufficient" in msg.lower():
                    log.error(
                        "HF token lacks Inference Providers permission. "
                        "Create a fine-grained token with preset Inference: "
                        "https://huggingface.co/settings/tokens/new?preset=inference "
                        "then update GitHub secret HF_TOKEN. Error: %s",
                        msg[:200],
                    )
                    return False
                log.warning("HF model %s failed: %s", model, msg[:200])
    except ImportError:
        log.warning("huggingface_hub not installed — using raw HTTP")
    except Exception as e:
        log.warning("HF InferenceClient setup failed: %s", e)

    # Raw HTTP to router only (api-inference.huggingface.co is retired)
    headers = {"Authorization": f"Bearer {token}"}
    for model in HF_MODELS:
        url = f"https://router.huggingface.co/hf-inference/models/{model}"
        try:
            log.info("Hugging Face HTTP: %s", model)
            resp = requests.post(
                url,
                headers=headers,
                json={
                    "inputs": prompt,
                    "parameters": {
                        "width": min(width, 1024),
                        "height": min(height, 1024),
                    },
                },
                timeout=180,
            )
            if resp.status_code == 403:
                log.error(
                    "HF HTTP 403 — token needs 'Make calls to Inference Providers'. "
                    "https://huggingface.co/settings/tokens/new?preset=inference"
                )
                return False
            if resp.status_code == 503:
                time.sleep(15)
                resp = requests.post(
                    url,
                    headers=headers,
                    json={"inputs": prompt},
                    timeout=180,
                )
            if resp.status_code >= 400:
                log.warning("HF HTTP %s: %s", resp.status_code, resp.text[:180])
                continue
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                log.warning("HF JSON: %s", resp.text[:180])
                continue
            _save_bytes(resp.content, out_path, width, height)
            return True
        except requests.RequestException as e:
            log.warning("HF HTTP error: %s", e)
    return False


def _try_pollinations(prompt: str, out_path: str, width: int, height: int, seed: int) -> bool:
    key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    encoded = urllib.parse.quote(prompt)
    last = None
    for model in MODEL_CANDIDATES:
        q = f"width={width}&height={height}&seed={seed}"
        if model:
            q += f"&model={model}"
        for base in (GEN_BASE, LEGACY_BASE):
            url = f"{base}/{encoded}?{q}"
            try:
                log.info("Pollinations: %s", url[:100])
                resp = requests.get(url, headers=headers, timeout=120)
                if resp.status_code == 402:
                    log.warning("Pollinations 402 Payment Required")
                    last = "402"
                    continue
                if resp.status_code >= 400:
                    log.warning("Pollinations HTTP %s", resp.status_code)
                    last = str(resp.status_code)
                    continue
                ct = resp.headers.get("content-type", "")
                if not ct.startswith("image/") and len(resp.content) < 1000:
                    continue
                _save_bytes(resp.content, out_path, width, height)
                time.sleep(2)
                return True
            except requests.RequestException as e:
                last = e
                log.warning("Pollinations error: %s", e)
    log.warning("Pollinations exhausted (last=%s)", last)
    return False


def _try_cloudflare(prompt: str, out_path: str, width: int, height: int) -> bool:
    account = os.environ.get("CF_ACCOUNT_ID", "").strip()
    token = os.environ.get("CF_API_TOKEN", "").strip()
    if not account or not token:
        log.info("CF_ACCOUNT_ID / CF_API_TOKEN not set — skip Cloudflare Workers AI")
        return False

    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{CF_MODEL}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        log.info("Cloudflare Workers AI: %s", CF_MODEL)
        resp = requests.post(url, headers=headers, json={"prompt": prompt}, timeout=180)
        if resp.status_code >= 400:
            log.warning("CF AI HTTP %s: %s", resp.status_code, resp.text[:300])
            return False
        ct = resp.headers.get("content-type", "")
        if ct.startswith("image/"):
            _save_bytes(resp.content, out_path, width, height)
            return True
        data = resp.json()
        result = data.get("result") or data
        b64 = None
        if isinstance(result, dict):
            b64 = result.get("image") or result.get("b64_json")
        if isinstance(b64, list) and b64:
            b64 = b64[0]
        if not b64:
            log.warning("CF AI unexpected response: %s", str(data)[:200])
            return False
        _save_bytes(base64.b64decode(b64), out_path, width, height)
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
    full_prompt = f"{prompt}, vertical composition 9:16, high detail, no text, no watermark"

    if _try_huggingface(full_prompt, out_path, width, height):
        return out_path
    if _try_pollinations(full_prompt, out_path, width, height, seed_val):
        return out_path
    if _try_cloudflare(full_prompt, out_path, width, height):
        return out_path

    raise RuntimeError(
        "All image providers failed.\n"
        "Fix ONE of these (free):\n"
        "1) HF_TOKEN — create fine-grained token with Inference preset:\n"
        "   https://huggingface.co/settings/tokens/new?preset=inference\n"
        "   Update GitHub secret HF_TOKEN.\n"
        "2) Top up Pollinations Pollen at https://enter.pollinations.ai\n"
        "3) Set CF_ACCOUNT_ID + CF_API_TOKEN (Workers AI free daily quota)"
    )
