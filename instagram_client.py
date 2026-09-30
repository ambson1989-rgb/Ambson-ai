"""
Thin wrapper around the Instagram API with Instagram Login
(https://graph.instagram.com) for publishing Reels and replying to comments.

Written against the documented flow as of mid-2026:
  1. POST /{ig_user_id}/media           -> create a container (async video processing)
  2. GET  /{container_id}?fields=status_code   -> poll until FINISHED
  3. POST /{ig_user_id}/media_publish   -> publish the finished container
  4. GET  /{media_id}/comments          -> list comments
  5. POST /{comment_id}/replies         -> reply to a comment

This has NOT been run against a live account (no network access to
graph.instagram.com from this environment) — treat it as a solid starting
point, not a tested integration. Sanity-check against the current docs at
developers.facebook.com/docs/instagram-platform before relying on it.
"""

import os
import time
import requests

HOST = os.environ.get("IG_GRAPH_HOST", "https://graph.instagram.com")
VERSION = os.environ.get("IG_API_VERSION", "v23.0")
IG_USER_ID = os.environ["IG_USER_ID"]
ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]


def _url(path: str) -> str:
    return f"{HOST}/{VERSION}/{path}"


def create_reel_container(video_url: str, caption: str, is_ai_generated: bool = True) -> str:
    """Start processing a video as a Reel. Returns the container ID."""
    resp = requests.post(
        _url(f"{IG_USER_ID}/media"),
        params={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "is_ai_generated": str(is_ai_generated).lower(),
            "access_token": ACCESS_TOKEN,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def wait_for_container(container_id: str, timeout_s: int = 300, poll_every_s: int = 10) -> bool:
    """Poll a container until Instagram finishes transcoding. Returns True if ready to publish."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = requests.get(
            _url(container_id),
            params={"fields": "status_code", "access_token": ACCESS_TOKEN},
            timeout=15,
        )
        resp.raise_for_status()
        status = resp.json().get("status_code")
        if status == "FINISHED":
            return True
        if status == "ERROR":
            return False
        time.sleep(poll_every_s)
    return False


def publish_container(container_id: str) -> str:
    """Publish a finished container. Returns the resulting media ID."""
    resp = requests.post(
        _url(f"{IG_USER_ID}/media_publish"),
        params={"creation_id": container_id, "access_token": ACCESS_TOKEN},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def publish_reel(video_url: str, caption: str, is_ai_generated: bool = True) -> str | None:
    """Full publish flow. Returns media ID, or None if processing failed."""
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
    resp.raise_for_status()
    return resp.json().get("data", [])


def reply_to_comment(comment_id: str, message: str) -> str:
    resp = requests.post(
        _url(f"{comment_id}/replies"),
        params={"message": message, "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["id"]
