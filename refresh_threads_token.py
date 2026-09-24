"""Renew the existing Threads long-lived token without printing credentials."""
import hmac
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from publish_threads import Threads, PublishError


def refresh(token, request=requests.get):
    if not token:
        raise PublishError("Missing THREADS_ACCESS_TOKEN")
    # The official Meta Postman collection uses bearer auth on this endpoint.
    try:
        response = request("https://graph.threads.net/refresh_access_token",
                           headers={"Authorization": f"Bearer {token}"},
                           params={"grant_type": "th_refresh_token"},
                           timeout=(10, 60))
        data = response.json()
    except (requests.RequestException, ValueError):
        raise PublishError("Threads refresh transport failure; no credentials logged") from None
    if not response.ok or "error" in data:
        code = data.get("error", {}).get("code")
        code = code if isinstance(code, int) else "unknown"
        raise PublishError(f"Threads renewal rejected (HTTP {response.status_code}, code {code}); token may be too new or expired")
    renewed = data.get("access_token")
    lifetime = data.get("expires_in")
    if not isinstance(renewed, str) or not renewed or type(lifetime) is not int or lifetime <= 0:
        raise PublishError("Invalid renewal response; no success recorded")
    # Never silently discard a rotated credential or claim Secrets were updated.
    if not hmac.compare_digest(renewed, token):
        raise PublishError("Threads returned a different token; secure Secret replacement is required. No token was logged or saved")
    return lifetime


def main():
    token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    if not token:
        raise PublishError("Missing THREADS_ACCESS_TOKEN")
    client = Threads(token, os.environ.get("THREADS_USER_ID", "").strip())
    client.preflight()
    lifetime = refresh(token)
    client.preflight()
    expiry = datetime.now(timezone.utc) + timedelta(seconds=lifetime)
    message = ("Threads token renewal succeeded for @gacha_m2026.\n"
               "Existing GitHub Secret matches the renewed token; no replacement needed.\n"
               f"API returned expires_in={lifetime} seconds.\n"
               f"Estimated expiry (UTC): {expiry.isoformat()}\n"
               f"Estimated expiry (KST): {expiry.astimezone(timezone(timedelta(hours=9))).isoformat()}\n"
               "Account and publishing permission verified after renewal. No content posted.\n")
    print(message)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text("## Threads token renewal\n\n" + message.replace("\n", "\n\n"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Unexpected errors must not expose a requests URL/header or response.
        print("::error::" + (str(exc) if isinstance(exc, PublishError) else "Threads renewal failed; credentials not logged"))
        sys.exit(1)
