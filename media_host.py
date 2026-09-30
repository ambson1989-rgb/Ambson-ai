"""
Upload rendered Reels to S3-compatible storage so Instagram can fetch them
via a public HTTPS URL.

Works with:
  - Cloudflare R2  (recommended — free egress)
  - AWS S3
  - Backblaze B2 (S3-compatible mode)
  - Any other S3-compatible provider

Required env vars:
  PUBLIC_MEDIA_BUCKET       bucket name
  PUBLIC_MEDIA_ACCESS_KEY   access key id
  PUBLIC_MEDIA_SECRET_KEY   secret access key
  PUBLIC_MEDIA_BASE_URL     public base URL that serves objects
                            e.g. https://pub-xxxxx.r2.dev  or  https://cdn.example.com

Optional:
  PUBLIC_MEDIA_ENDPOINT     S3 endpoint (required for R2/B2)
                            e.g. https://<ACCOUNT_ID>.r2.cloudflarestorage.com
  PUBLIC_MEDIA_REGION       defaults to "auto"
  PUBLIC_MEDIA_PREFIX       key prefix, default "reels/"
"""

import logging
import mimetypes
import os
from pathlib import Path

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


def upload_to_public_host(local_path: str) -> str:
    """Upload a local file and return its public HTTPS URL."""
    bucket = os.environ["PUBLIC_MEDIA_BUCKET"]
    base_url = os.environ["PUBLIC_MEDIA_BASE_URL"].rstrip("/")
    prefix = os.environ.get("PUBLIC_MEDIA_PREFIX", "reels/").lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    filename = Path(local_path).name
    key = f"{prefix}{filename}"
    content_type = mimetypes.guess_type(local_path)[0] or "video/mp4"

    client = _client()
    log.info("Uploading %s -> s3://%s/%s", local_path, bucket, key)

    extra = {"ContentType": content_type}
    # ACL only works on providers that support it (AWS S3). R2 uses bucket-level public access.
    if not os.environ.get("PUBLIC_MEDIA_ENDPOINT"):
        extra["ACL"] = "public-read"

    client.upload_file(
        local_path,
        bucket,
        key,
        ExtraArgs=extra,
    )

    public_url = f"{base_url}/{key}"
    log.info("Public URL: %s", public_url)
    return public_url
