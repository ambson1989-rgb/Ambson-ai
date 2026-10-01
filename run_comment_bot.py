"""
Manual comment replies only (schedule is off by default).

Limits per run (env):
  COMMENT_MEDIA_LIMIT   — how many recent posts to scan (default 2)
  COMMENT_MAX_REPLIES   — max replies total this run (default 2)
  COMMENT_MIN/MAX_DELAY_SEC — pause between replies
"""

import logging
import os

import requests

from instagram_client import _url, ACCESS_TOKEN, IG_USER_ID
from comment_bot import process_media_comments

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("comment_bot")

RECENT_MEDIA_LIMIT = int(os.environ.get("COMMENT_MEDIA_LIMIT", "2"))
MAX_REPLIES = int(os.environ.get("COMMENT_MAX_REPLIES", "2"))


def get_recent_media_ids() -> list[str]:
    resp = requests.get(
        _url(f"{IG_USER_ID}/media"),
        params={"fields": "id", "limit": RECENT_MEDIA_LIMIT, "access_token": ACCESS_TOKEN},
        timeout=15,
    )
    resp.raise_for_status()
    return [item["id"] for item in resp.json().get("data", [])]


def run_once() -> None:
    budget = MAX_REPLIES
    log.info("Comment bot starting (max %d replies, %d media)", budget, RECENT_MEDIA_LIMIT)
    for media_id in get_recent_media_ids():
        if budget <= 0:
            break
        count = process_media_comments(media_id, budget)
        budget -= count
        if count:
            log.info("Replied to %d on %s (%d budget left)", count, media_id, budget)
    log.info("Comment bot finished")


if __name__ == "__main__":
    run_once()
