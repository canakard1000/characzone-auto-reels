"""Publish approved reels to Threads; never modify the Instagram manifest."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE = "https://graph.threads.net/v1.0"
EXPECTED_USERNAME = "gacha_m2026"


class PublishError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def fingerprint(reel):
    value = json.dumps([reel["video_url"], reel["caption"]], ensure_ascii=False)
    return hashlib.sha256(value.encode()).hexdigest()


def approved_reels(manifest):
    items = manifest.get("reels", [])
    ids = [item.get("id") for item in items]
    if any(not isinstance(i, str) or not i for i in ids) or len(ids) != len(set(ids)):
        raise PublishError("Manifest has missing or duplicate reel IDs")
    # published / published_at belong exclusively to Instagram.
    eligible = []
    for item in items:
        if item.get("approved") is not True or item.get("rejected") is True:
            continue
        if item.get("scheduled_for"):
            scheduled = datetime.fromisoformat(item["scheduled_for"].replace("Z", "+00:00"))
            if scheduled.tzinfo is None:
                raise PublishError("Scheduled time must include a timezone")
            if scheduled > datetime.now(timezone.utc):
                continue
        eligible.append(item)
    return eligible


def validate(reel):
    url = urlparse(reel["video_url"])
    if (url.scheme != "https" or url.netloc != "raw.githubusercontent.com"
            or not url.path.startswith("/canakard1000/characzone-auto-reels/")
            or url.query or url.fragment):
        raise PublishError("Video must use this repository's public HTTPS raw URL")
    if not isinstance(reel.get("caption"), str) or not 1 <= len(reel["caption"]) <= 500:
        raise PublishError("Threads caption must contain 1 to 500 characters; no silent truncation")


class Threads:
    def __init__(self, token, user_id):
        self.token, self.user_id = token, user_id

    def api(self, method, path, **data):
        kwargs = {"params" if method == "GET" else "data": data}
        try:
            response = requests.request(method, f"{BASE}/{path}", timeout=(10, 60),
                                        headers={"Authorization": f"Bearer {self.token}"}, **kwargs)
            payload = response.json()
        except (requests.RequestException, ValueError):
            # Never log request URLs, bearer tokens, or raw API responses.
            raise PublishError("Threads transport/JSON failure; inspect saved phase before retry") from None
        if not response.ok or "error" in payload:
            code = payload.get("error", {}).get("code", "unknown")
            detail = str(payload.get("error", {}).get("message", "")).replace(self.token, "[REDACTED]")
            detail = re.sub(r"https?://\S+|[A-Za-z0-9_\-]{50,}", "[REDACTED]", detail)[:350]
            raise PublishError(f"Threads API failed at {path}: HTTP {response.status_code}, code {code}: {detail}")
        return payload

    def preflight(self):
        account = self.api("GET", "me", fields="id,username")
        if (not account.get("id") or account.get("username") != EXPECTED_USERNAME
                or (self.user_id and str(account["id"]) != self.user_id)):
            raise PublishError("Connected Threads account does not match gacha_m2026 and THREADS_USER_ID")
        self.user_id = str(account["id"])
        # Threads has no /me/permissions edge. This documented read-only edge
        # requires both threads_basic and threads_content_publish.
        limits = self.api("GET", "me/threads_publishing_limit", fields="quota_usage,config").get("data", [])
        if not limits or not isinstance(limits[0].get("quota_usage"), int):
            raise PublishError("Threads publishing permission/quota could not be verified")
        quota = limits[0]
        total = quota.get("config", {}).get("quota_total")
        if total is not None and quota["quota_usage"] >= total:
            raise PublishError("Threads publishing quota exhausted")
        print(f"Threads account and permissions verified: @{EXPECTED_USERNAME}")

    def create(self, reel):
        return self.api("POST", f"{self.user_id}/threads", media_type="VIDEO",
                        video_url=reel["video_url"], text=reel["caption"])["id"]

    def status(self, container_id):
        return self.api("GET", container_id, fields="id,status").get("status")

    def publish(self, container_id):
        return self.api("POST", f"{self.user_id}/threads_publish", creation_id=container_id)["id"]


class GitLedger:
    """Persist BEFORE external side effects. A failed push stops the operation."""
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        if self.git("branch", "--show-current") != "social-publish-state":
            raise PublishError("Ledger must be checked out on social-publish-state, never main")
        self.path = self.directory / "threads-state.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"reels": {}}

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.directory), *args],
                                capture_output=True, text=True)
        if result.returncode:
            raise PublishError("State persistence failed; publication stopped")
        return result.stdout.strip()

    def get(self, reel_id):
        return self.data["reels"].get(reel_id, {}).copy()

    def save(self, reel_id, entry):
        self.data["reels"][reel_id] = {**entry, "updated_at": now()}
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n")
        self.git("add", "threads-state.json")
        self.git("-c", "user.name=characzone-social-bot", "-c",
                 "user.email=actions@users.noreply.github.com", "commit", "-m", "Save Threads publication phase")
        self.git("push", "origin", "HEAD:social-publish-state")


def publish_one(reel, client, ledger, sleep=time.sleep, check_approval=lambda: None):
    validate(reel)
    entry = ledger.get(reel["id"])
    if entry.get("phase") == "published":
        return "already_published"
    if entry and entry.get("fingerprint") != fingerprint(reel):
        raise PublishError("Reel changed after upload began; reconcile it before retry")
    phase = entry.get("phase")
    if phase in {"creating", "needs_review", "failed"}:
        raise PublishError("Uncertain/failed previous attempt requires reconciliation; no duplicate upload")
    if not entry:
        entry = {"phase": "creating", "fingerprint": fingerprint(reel)}
        ledger.save(reel["id"], entry)
        container = client.create(reel)
        entry = {**entry, "phase": "processing", "container_id": str(container)}
        ledger.save(reel["id"], entry)
    container = entry["container_id"]
    # If the process died after sending publish, reconcile but never resend.
    if entry["phase"] == "publishing":
        if client.status(container) == "PUBLISHED":
            ledger.save(reel["id"], {**entry, "phase": "published", "published_at": now()})
            return "published_reconciled"
        raise PublishError("Publish acknowledgement unknown; check Threads before any manual retry")
    for _ in range(30):
        status = client.status(container)
        if status == "PUBLISHED":
            ledger.save(reel["id"], {**entry, "phase": "published", "published_at": now()})
            return "published_reconciled"
        if status == "FINISHED":
            break
        if status in {"ERROR", "EXPIRED"}:
            ledger.save(reel["id"], {**entry, "phase": "failed", "status": status})
            raise PublishError("Threads container failed/expired; no automatic re-upload")
        if status != "IN_PROGRESS":
            raise PublishError("Unexpected container status; no publication attempted")
        sleep(10)
    else:
        return "processing"  # Resume the SAME container on the next run.
    check_approval()
    entry = {**entry, "phase": "publishing"}
    ledger.save(reel["id"], entry)
    media_id = str(client.publish(container))
    ledger.save(reel["id"], {**entry, "phase": "published", "media_id": media_id, "published_at": now()})
    return "published"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true", help="Default is read-only preflight")
    parser.add_argument("--manifest", default="approved.json")
    parser.add_argument("--state-dir", default=".social-state")
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    reels = approved_reels(json.loads(manifest_path.read_text()))
    print(f"Approved reels eligible for Threads: {len(reels)}")
    for reel in reels:
        validate(reel)
    token = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("THREADS_USER_ID", "").strip()
    if not token:
        raise PublishError("Missing THREADS_ACCESS_TOKEN; no post sent")
    token_directory = os.getenv("THREADS_TOKEN_STATE_DIR")
    if token_directory:
        from threads_token_store import current_token
        token = current_token(token_directory, token)
    client = Threads(token, user_id)
    client.preflight()
    if not args.publish:
        print("Read-only preflight passed; no container created and no post sent")
        return
    ledger = GitLedger(args.state_dir)
    for reel in reels:
        if ledger.get(reel["id"]).get("phase") == "published":
            continue
        latest = approved_reels(json.loads(manifest_path.read_text()))
        if reel not in latest:
            raise PublishError("Approval/content changed before upload")
        def check_approval():
            current = approved_reels(json.loads(manifest_path.read_text()))
            if reel not in current:
                raise PublishError("Approval/content changed before publication")
        print(f"Threads result: {reel['id']}: {publish_one(reel, client, ledger, check_approval=check_approval)}")
        return  # At most one approved reel per scheduled run.
    print("All approved reels already published to Threads")


if __name__ == "__main__":
    try:
        main()
    except (PublishError, KeyError, ValueError, OSError) as exc:
        print(f"::error::{exc if isinstance(exc, PublishError) else 'Invalid configuration or state'}")
        sys.exit(1)
