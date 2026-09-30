"""
Refresh the Instagram long-lived User access token.

A long-lived token lasts ~60 days. It can be refreshed for another 60 days
as long as it is at least 24 hours old and has not already expired.

  GET https://graph.instagram.com/refresh_access_token
      ?grant_type=ig_refresh_token
      &access_token=<current long-lived token>

On GitHub Actions the refreshed token is written to stdout so you can
update the IG_ACCESS_TOKEN secret. If a GH_PAT secret is present (with
repo + secrets scope), this script can also push the new value into the
repo secret automatically.

Run weekly (or at the start of the daily pipeline) so the token never dies.
"""

import logging
import os
import sys

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("token_refresh")

HOST = os.environ.get("IG_GRAPH_HOST", "https://graph.instagram.com")


def refresh_long_lived_token(current_token: str) -> dict:
    """Returns {access_token, token_type, expires_in}. Raises on failure."""
    resp = requests.get(
        f"{HOST}/refresh_access_token",
        params={
            "grant_type": "ig_refresh_token",
            "access_token": current_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if "access_token" not in data:
        raise RuntimeError(f"Unexpected refresh response: {data}")
    return data


def try_update_github_secret(new_token: str) -> bool:
    """If GH_PAT + GITHUB_REPOSITORY are set, update the IG_ACCESS_TOKEN secret."""
    pat = os.environ.get("GH_PAT", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()  # owner/repo
    if not pat or not repo:
        return False

    # GitHub Secrets API requires the secret value to be libsodium-sealed.
    # Use the gh CLI when available (installed on GitHub-hosted runners).
    import subprocess

    try:
        subprocess.run(
            ["gh", "secret", "set", "IG_ACCESS_TOKEN", "--body", new_token, "--repo", repo],
            check=True,
            env={**os.environ, "GH_TOKEN": pat},
            capture_output=True,
            text=True,
        )
        log.info("Updated GitHub secret IG_ACCESS_TOKEN via gh CLI")
        return True
    except FileNotFoundError:
        log.warning("gh CLI not found — cannot auto-update secret")
    except subprocess.CalledProcessError as e:
        log.warning("Failed to update GitHub secret: %s", e.stderr or e)
    return False


def run_once() -> None:
    current = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not current:
        log.error("IG_ACCESS_TOKEN is not set")
        sys.exit(1)

    try:
        data = refresh_long_lived_token(current)
    except requests.HTTPError as e:
        body = e.response.text if e.response is not None else ""
        log.error("Token refresh failed (%s): %s", e, body)
        # Common causes: token < 24h old, or already expired.
        sys.exit(1)

    new_token = data["access_token"]
    expires_in = data.get("expires_in", "?")
    log.info("Token refreshed. New expires_in=%s seconds (~%.0f days)", expires_in, int(expires_in) / 86400 if str(expires_in).isdigit() else -1)

    updated = try_update_github_secret(new_token)
    if not updated:
        # Print so the Actions log (or local run) shows the value to copy into Secrets.
        print("\n===== NEW IG_ACCESS_TOKEN (copy into repo Secrets) =====")
        print(new_token)
        print("===== END =====\n")
        log.warning(
            "Secret was NOT auto-updated. Add a GH_PAT secret (repo + secrets scope) "
            "for automatic updates, or paste the token above into Settings → Secrets → IG_ACCESS_TOKEN."
        )


if __name__ == "__main__":
    run_once()
