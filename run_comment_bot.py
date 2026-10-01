"""
Manual comment replies. Logs clearly when nothing is found.
"""

import logging
import os

import requests

from instagram_client import _url, ACCESS_TOKEN, IG_USER_ID, _raise_for_status
from comment_bot import process_media_comments

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("comment_bot")

RECENT_MEDIA_LIMIT = int(os.environ.get("COMMENT_MEDIA_LIMIT", "10"))
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
    return data


def run_once() -> None:
    budget = MAX_REPLIES
    log.info(
        "Comment bot starting (max %d replies, scan %d media, ig_user=%s)",
        budget,
        RECENT_MEDIA_LIMIT,
        IG_USER_ID[:6] + "…" if len(IG_USER_ID) > 6 else IG_USER_ID,
    )

    try:
        media_list = get_recent_media()
    except Exception as e:
        log.error("Failed to list media: %s", e)
        raise

    if not media_list:
        log.warning(
            "No media returned. Check IG_USER_ID and that the token can read this account's posts."
        )
        return

    total = 0
    for m in media_list:
        if budget <= 0:
            break
        media_id = m["id"]
        count = process_media_comments(media_id, budget)
        budget -= count
        total += count
        if count:
            log.info("Replied to %d on %s (%d budget left)", count, media_id, budget)

    if total == 0:
        log.warning(
            "No replies sent. Possible reasons: "
            "(1) posts have no comments yet, "
            "(2) missing instagram_business_manage_comments permission, "
            "(3) comments_count is 0 on all scanned posts, "
            "(4) all comments already replied."
        )
    else:
        log.info("Comment bot finished — %d reply(ies) sent", total)


if __name__ == "__main__":
    run_once()
