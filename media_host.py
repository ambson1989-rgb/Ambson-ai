"""
Upload rendered Reels to S3-compatible storage so Instagram can fetch them
via a public HTTPS URL. Also prune old objects to stay on free-tier storage.

Works with Cloudflare R2, AWS S3, Backblaze B2 (S3 mode).
"""

import logging
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.client import Config

log = logging.getLogger("media_host")


def _client():
    kwargs = {
        "service_name": "s3",
        "aws_access_key_id": os.environ["PUBLIC_MEDIA_ACCESS_KEY"],
        "aws_secret_access_key": os.environ["PUBLIC_MEDIA_SECRET_KEY"],
        "region_name": os.environ.get("PUBLIC_MEDIA_REGION", "auto"),
        "config": Config(signature_version="s3v4"),
    }
    endpoint = os.environ.get("PUBLIC_MEDIA_ENDPOINT", "").strip()
    if endpoint:
        kwargs["endpoint_url"] = endpoint
    return boto3.client(**kwargs)


def _prefix() -> str:
    prefix = os.environ.get("PUBLIC_MEDIA_PREFIX", "reels/").lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    return prefix


def upload_to_public_host(local_path: str) -> str:
    """Upload a local file and return its public HTTPS URL."""
    bucket = os.environ["PUBLIC_MEDIA_BUCKET"]
    base_url = os.environ["PUBLIC_MEDIA_BASE_URL"].rstrip("/")
    prefix = _prefix()

    filename = Path(local_path).name
    key = f"{prefix}{filename}"
    content_type = mimetypes.guess_type(local_path)[0] or "video/mp4"

    client = _client()
    log.info("Uploading %s -> s3://%s/%s", local_path, bucket, key)

    extra = {"ContentType": content_type}
    if not os.environ.get("PUBLIC_MEDIA_ENDPOINT"):
        extra["ACL"] = "public-read"

    client.upload_file(local_path, bucket, key, ExtraArgs=extra)

    public_url = f"{base_url}/{key}"
    log.info("Public URL: %s", public_url)
    return public_url


def _key_from_public_url(public_url: str) -> str | None:
    """Best-effort extract object key from public URL."""
    base = os.environ.get("PUBLIC_MEDIA_BASE_URL", "").rstrip("/")
    if base and public_url.startswith(base + "/"):
        return public_url[len(base) + 1 :]
    path = urlparse(public_url).path.lstrip("/")
    return path or None


def delete_public_object(public_url: str) -> None:
    """Delete one object after Instagram has finished fetching it."""
    key = _key_from_public_url(public_url)
    if not key:
        log.warning("Could not derive R2 key from URL: %s", public_url)
        return
    bucket = os.environ["PUBLIC_MEDIA_BUCKET"]
    try:
        _client().delete_object(Bucket=bucket, Key=key)
        log.info("Deleted from R2: %s", key)
    except Exception as e:
        log.warning("Failed to delete %s: %s", key, e)


def cleanup_old_media(keep: int | None = None) -> int:
    """
    Keep only the newest `keep` objects under PUBLIC_MEDIA_PREFIX.
    Default keep = R2_KEEP_OBJECTS env or 4 (2 posts/day × 2 days buffer).
    Returns number of objects deleted.
    """
    if keep is None:
        keep = int(os.environ.get("R2_KEEP_OBJECTS", "4"))

    bucket = os.environ["PUBLIC_MEDIA_BUCKET"]
    prefix = _prefix()
    client = _client()

    objects = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            objects.append(obj)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")

    if len(objects) <= keep:
        log.info("R2 cleanup: %d object(s) under %s (keep=%d) — nothing to delete", len(objects), prefix, keep)
        return 0

    objects.sort(key=lambda o: o["LastModified"], reverse=True)
    to_delete = objects[keep:]
    deleted = 0
    for obj in to_delete:
        key = obj["Key"]
        try:
            client.delete_object(Bucket=bucket, Key=key)
            log.info("R2 cleanup deleted: %s", key)
            deleted += 1
        except Exception as e:
            log.warning("R2 cleanup failed for %s: %s", key, e)

    log.info("R2 cleanup done: deleted %d, kept %d", deleted, keep)
    return deleted
