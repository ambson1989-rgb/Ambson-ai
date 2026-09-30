"""
Free image generation via Pollinations.ai -- no API key required.

The anonymous tier is rate-limited to roughly one request per 15 seconds and
may be less consistent than a paid API (occasional slow or failed requests).
Fine for this project's volume -- a handful of images once a day -- but not
something to lean on for anything time-critical. Registering a free account
at auth.pollinations.ai removes the rate limit and watermark if this ever
becomes a bottleneck; not needed at this volume.
"""

import os
import time
import urllib.parse
import requests

BASE_URL = "https://image.pollinations.ai/prompt"


def generate_image(
    prompt: str,
    out_path: str,
    width: int = 1080,
    height: int = 1920,
    seed: int | None = None,
    retries: int = 2,
) -> str:
    encoded = urllib.parse.quote(prompt)
    seed_val = seed if seed is not None else int(time.time())
    url = (
        f"{BASE_URL}/{encoded}"
        f"?width={width}&height={height}&seed={seed_val}"
        f"&nologo=true&model=flux&safe=true&private=true"
    )

    last_error = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, timeout=90)
            resp.raise_for_status()
            with open(out_path, "wb") as f:
                f.write(resp.content)
            return out_path
        except requests.RequestException as e:
            last_error = e
            if attempt < retries:
                time.sleep(16)  # respect the ~1 request/15s anonymous rate limit

    raise RuntimeError(f"Pollinations image generation failed after retries: {last_error}")
