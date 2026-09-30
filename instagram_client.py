"""
Instagram API with Instagram Login (graph.instagram.com):
  1. POST /{ig_user_id}/media  (REELS + video_url)
  2. Poll container status_code until FINISHED
  3. POST /{ig_user_id}/media_publish
"""

import logging
import os
import time
import requests

log = logging.getLogger("instagram_client")

HOST = os.environ.get("IG_GRAPH_HOST", "https://graph.instagram.com")
VERSION = os.environ.get("IG_API_VERSION", "v23.0")
IG_USER_ID = os.environ["IG_USER_ID"]
ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]


def _url(path: str) -> str:
    return f"{HOST}/{VERSION}/{path}"


def _raise_for_status(resp: requests.Response) -> None:
    if resp.ok:
        return
    try:
        body = resp.json()
    except Exception:
        body = resp.text[:1000]
    log.error("Instagram API %s %s -> %s %s", resp.request.method, resp.url.split("?")[0], resp.status_code, body)
    raise requests.HTTPError(
        f"{resp.status_code} Client Error: {body}",
        response=resp,
    )


def verify_public_video(video_url: str) -> None:
    """Ensure Instagram can fetch the file (public HTTPS, video content-type)."""
    log.info("Verifying public video URL is fetchable...")
    try:
        head = requests.head(video_url, timeout=30, allow_redirects=True)
        # Some hosts block HEAD — fall back to ranged GET
        if head.status_code >= 400:
            head = requests.get(video_url, headers={"Range": "bytes=0-1023"}, timeout=30)
        ct = head.headers.get("Content-Type", "")
        log.info("Public URL check: status=%s content-type=%s", head.status_code, ct)
        if head.status_code >= 400:
            raise RuntimeError(
                f"Video URL not publicly readable (HTTP {head.status_code}): {video_url}. "
                f"Enable R2 Public Development URL (r2.dev) or a custom public domain."
            )
    except requests.RequestException as e:
        raise RuntimeError(f"Cannot reach video URL {video_url}: {e}") from e


def create_reel_container(video_url: str, caption: str, is_ai_generated: bool = True) -> str:
    """Start processing a video as a Reel. Returns the container ID."""
    # Form body (not query string) — matches Meta examples; safer for long captions.
    data = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": ACCESS_TOKEN,
    }
    if is_ai_generated:
        data["is_ai_generated"] = "true"

    resp = requests.post(_url(f"{IG_USER_ID}/media"), data=data, timeout=60)
    if not resp.ok and is_ai_generated:
        # Retry once without AI flag if the parameter is rejected
        log.warning("Create container failed with is_ai_generated; retrying without it: %s", resp.text[:300])
        data.pop("is_ai_generated", None)
        resp = requests.post(_url(f"{IG_USER_ID}/media"), data=data, timeout=60)

    _raise_for_status(resp)
    payload = resp.json()
    container_id = payload.get("id")
    if not container_id:
        raise RuntimeError(f"No container id in response: {payload}")
    log.info("Created media container: %s", container_id)
    return container_id


def wait_for_container(container_id: str, timeout_s: int = 300, poll_every_s: int = 10) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = requests.get(
            _url(container_id),
            params={
                "fields": "status_code,status",
                "access_token": ACCESS_TOKEN,
            },
            timeout=15,
        )
        _raise_for_status(resp)
        body = resp.json()
        status = body.get("status_code")
        log.info("Container %s status_code=%s status=%s", container_id, status, body.get("status"))
        if status == "FINISHED":
            return True
        if status == "ERROR":
            log.error("Container processing ERROR: %s", body)
            return False
        time.sleep(poll_every_s)
    log.error("Container %s timed out waiting for FINISHED", container_id)
    return False


def publish_container(container_id: str) -> str:
    resp = requests.post(
        _url(f"{IG_USER_ID}/media_publish"),
        data={"creation_id": container_id, "access_token": ACCESS_TOKEN},
        timeout=60,
    )
    _raise_for_status(resp)
    media_id = resp.json().get("id")
    if not media_id:
        raise RuntimeError(f"No media id in publish response: {resp.text}")
    return media_id


def publish_reel(video_url: str, caption: str, is_ai_generated: bool = True) -> str | None:
    verify_public_video(video_url)
    container_id = create_reel_container(video_url, caption, is_ai_generated)
    if not wait_for_container(container_id):
        return None
    return publish_container(container_id)


def get_recent_comments(media_id: str) -> list[dict]:
    resp = requests.get(
        _url(f"{media_id}/comments"),
        params={"fields": "id,text,username,timestamp", "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    _raise_for_status(resp)
    return resp.json().get("data", [])


def reply_to_comment(comment_id: str, message: str) -> str:
    resp = requests.post(
        _url(f"{comment_id}/replies"),
        data={"message": message, "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    _raise_for_status(resp)
    return resp.json()["id"]
