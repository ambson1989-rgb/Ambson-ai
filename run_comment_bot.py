"""
Run this on a schedule (e.g. every 15-30 min via cron) to catch new comments
on your recent posts and reply automatically. See README for scheduling.
"""

import logging
import os
import requests

from instagram_client import _url, ACCESS_TOKEN, IG_USER_ID
from comment_bot import process_media_comments

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("comment_bot")

# How many of your most recent posts to check for new comments each run.
RECENT_MEDIA_LIMIT = 5


def get_recent_media_ids() -> list[str]:
    resp = requests.get(
        _url(f"{IG_USER_ID}/media"),
        params={"fields": "id", "limit": RECENT_MEDIA_LIMIT, "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    resp.raise_for_status()
    return [item["id"] for item in resp.json().get("data", [])]


def run_once() -> None:
    for media_id in get_recent_media_ids():
        count = process_media_comments(media_id)
        if count:
            log.info("Replied to %d new comment(s) on %s", count, media_id)


if __name__ == "__main__":
    run_once()
