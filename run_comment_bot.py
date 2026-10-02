"""
Manual-only comment bot entrypoint.
Scans recent posts, finds unreplied comments, replies by rules, likes praise.
"""

import logging
import os

import requests

from instagram_client import _url, ACCESS_TOKEN, IG_USER_ID, _raise_for_status
from comment_bot import process_media_comments

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("comment_bot")

# Scan more posts so "all that need reply" are covered when you run manually
RECENT_MEDIA_LIMIT = int(os.environ.get("COMMENT_MEDIA_LIMIT", "25"))
MAX_REPLIES = int(os.environ.get("COMMENT_MAX_REPLIES", "10"))


def get_recent_media() -> list[dict]:
    resp = requests.get(
        _url(f"{IG_USER_ID}/media"),
        params={
            "fields": "id,caption,timestamp,comments_count,media_type,media_product_type",
            "limit": RECENT_MEDIA_LIMIT,
            "access_token": ACCESS_TOKEN,
        },
        timeout=30,
    )
    _raise_for_status(resp)
    data = resp.json().get("data", [])
    log.info("Found %d recent media item(s)", len(data))
    for m in data:
        cap = (m.get("caption") or "")[:60].replace("\n", " ")
        log.info(
            "  media=%s type=%s product=%s comments_count=%s caption=%r",
            m.get("id"),
            m.get("media_type"),
            m.get("media_product_type"),
            m.get("comments_count"),
            cap,
        )
    # Prefer posts that already have comments
    data.sort(key=lambda m: int(m.get("comments_count") or 0), reverse=True)
    return data


def run_once() -> None:
    budget = MAX_REPLIES
    log.info(
        "Comment bot MANUAL run (max %d replies, scan up to %d media)",
        budget,
        RECENT_MEDIA_LIMIT,
    )

    try:
        media_list = get_recent_media()
    except Exception as e:
        log.error("Failed to list media: %s", e)
        raise

    if not media_list:
        log.warning("No media returned. Check IG_USER_ID / token permissions.")
        return

    total = 0
    for m in media_list:
        if budget <= 0:
            break
        # Skip empty threads to save API calls
        if int(m.get("comments_count") or 0) == 0:
            log.info("  skip media %s (comments_count=0)", m["id"])
            continue
        media_id = m["id"]
        count = process_media_comments(media_id, budget)
        budget -= count
        total += count
        if count:
            log.info("Replied to %d on %s (%d budget left)", count, media_id, budget)

    if total == 0:
        log.warning(
            "No replies sent. Check: comments exist, manage_comments permission, "
            "or all eligible comments already replied."
        )
    else:
        log.info("Comment bot finished — %d reply(ies) sent", total)


if __name__ == "__main__":
    run_once()
