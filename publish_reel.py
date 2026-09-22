import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests


GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v26.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
MANIFEST = Path(os.getenv("REELS_MANIFEST", "approved.json"))


def api(method: str, path: str, **kwargs):
    response = requests.request(method, f"{GRAPH_BASE}/{path.lstrip('/')}", timeout=60, **kwargs)
    try:
        payload = response.json()
    except ValueError:
        response.raise_for_status()
        raise RuntimeError("Meta API returned a non-JSON response")
    if not response.ok or "error" in payload:
        message = payload.get("error", {}).get("message", "Meta API request failed")
        raise RuntimeError(message)
    return payload


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def load_approved_reel():
    data = load_manifest()
    items = [item for item in data.get("reels", []) if item.get("approved") and not item.get("published")]
    if not items:
        print("No approved unpublished reel. Nothing to do.")
        sys.exit(0)
    return items[0], data


def preflight():
    token = os.environ.get("META_ACCESS_TOKEN", "").strip()
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID", "").strip()
    if not token or not ig_user_id:
        raise RuntimeError("Required GitHub secrets are missing")

    account = api(
        "GET",
        ig_user_id,
        params={"fields": "id,username,account_type", "access_token": token},
    )
    if str(account.get("id")) != ig_user_id:
        raise RuntimeError("INSTAGRAM_USER_ID does not match the connected Instagram account")

    data = load_manifest()
    reels = data.get("reels", [])
    if not reels:
        raise RuntimeError("No reel is defined in approved.json")
    reel = reels[0]
    response = requests.get(reel["video_url"], stream=True, timeout=60, allow_redirects=True)
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "video" not in content_type and "octet-stream" not in content_type:
        raise RuntimeError(f"Video URL returned unexpected content type: {content_type or 'missing'}")
    print(
        f"Preflight passed: account=@{account.get('username', 'unknown')}, "
        f"reel={reel.get('id')}, approved={reel.get('approved')}, "
        f"content_type={content_type}"
    )


def mark_published(data, reel_id, media_id):
    for item in data["reels"]:
        if item.get("id") == reel_id:
            item["published"] = True
            item["instagram_media_id"] = media_id
            item["published_at"] = datetime.now(timezone.utc).isoformat()
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    if os.getenv("PREFLIGHT_ONLY", "false").lower() == "true":
        preflight()
        return

    reel, manifest = load_approved_reel()
    token = os.environ["META_ACCESS_TOKEN"]
    ig_user_id = os.environ["INSTAGRAM_USER_ID"]

    container = api(
        "POST",
        f"{ig_user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": reel["video_url"],
            "caption": reel["caption"],
            "share_to_feed": "true",
            "access_token": token,
        },
    )["id"]

    for _ in range(30):
        status = api("GET", container, params={"fields": "status_code,status", "access_token": token})
        if status.get("status_code") == "FINISHED":
            break
        if status.get("status_code") == "ERROR":
            raise RuntimeError(status.get("status", "Meta failed to process the reel"))
        time.sleep(10)
    else:
        raise TimeoutError("Reel processing did not finish within five minutes")

    media_id = api("POST", f"{ig_user_id}/media_publish", data={"creation_id": container, "access_token": token})["id"]
    mark_published(manifest, reel["id"], media_id)
    print(f"Published approved reel: {reel['id']}")


if __name__ == "__main__":
    main()
