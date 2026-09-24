"""Refresh Threads credentials and persist only authenticated ciphertext."""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from publish_threads import Threads, PublishError
from threads_token_store import TokenStore

def refresh(token, request=requests.get):
    if not token:
        raise PublishError("Missing THREADS_ACCESS_TOKEN")
    # Meta's official collection sets addTokenTo=queryParams for this OAuth endpoint.
    try:
        response = request("https://graph.threads.net/refresh_access_token",
                           params={"grant_type": "th_refresh_token", "access_token": token},
                           timeout=(10, 60))
        data = response.json()
    except (requests.RequestException, ValueError):
        raise PublishError("Threads refresh transport failure; no credentials logged") from None
    if not response.ok or "error" in data:
        code = data.get("error", {}).get("code")
        code = code if isinstance(code, int) else "unknown"
        raise PublishError(f"Threads renewal rejected (HTTP {response.status_code}, code {code})")
    renewed = data.get("access_token")
    lifetime = data.get("expires_in")
    if not isinstance(renewed, str) or not renewed or type(lifetime) is not int or lifetime <= 0:
        raise PublishError("Invalid renewal response; no success recorded")
    return renewed, lifetime


def renew(store, validate, request_refresh=refresh, now=None):
    now = now or datetime.now(timezone.utc)
    state = store.read()
    active = state.get("active")
    pending = state.get("pending")
    if not pending:
        if active:
            renewed_at = datetime.fromisoformat(active["refreshed_at"])
            expires_at = datetime.fromisoformat(active["expires_at"])
            age = now - renewed_at
            # Daily retries, but never refresh a credential younger than 24 hours.
            if age < timedelta(days=1) or (age < timedelta(days=7) and expires_at - now > timedelta(days=14)):
                validate(active["access_token"])
                return "checked", active
        token = active["access_token"] if active else store.root_secret
        validate(token)
        token, lifetime = request_refresh(token)
        pending = {"access_token": token, "refreshed_at": now.isoformat(),
                   "expires_at": (now + timedelta(seconds=lifetime)).isoformat()}
        state["pending"] = pending
        # Persist before validation: a transient API outage cannot lose a rotated token.
        store.save(state)
    validate(pending["access_token"])
    state["active"] = pending
    state.pop("pending", None)
    store.save(state)
    return "renewed", pending


def main():
    root = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
    store = TokenStore(os.getenv("THREADS_TOKEN_STATE_DIR", ".threads-token-state"), root)
    user_id = os.getenv("THREADS_USER_ID", "").strip()
    status, active = renew(store, lambda token: Threads(token, user_id).preflight())
    message = (f"Threads token {status} for @gacha_m2026.\n"
               f"Estimated expiry (UTC): {active['expires_at']}\n"
               "Latest credential is encrypted and available to the publisher. No content posted.\n")
    print(message)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(message)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("::error::" + (str(exc) if isinstance(exc, PublishError) else "Threads renewal failed; credentials not logged"))
        sys.exit(1)
