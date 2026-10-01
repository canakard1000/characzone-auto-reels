import json
import os
from pathlib import Path

import requests

GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v26.0")
BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
TOKEN = os.environ["META_ACCESS_TOKEN"].strip()
USER_ID = os.environ["INSTAGRAM_USER_ID"].strip()
MEDIA_ID = Path(".verify-instagram-now").read_text(encoding="utf-8").strip()
if not MEDIA_ID.isdigit():
    raise RuntimeError("Verification marker must contain a numeric media ID")

def get(path, params):
    response = requests.get(f"{BASE}/{path}", params=params, timeout=45)
    payload = response.json()
    if not response.ok or "error" in payload:
        err = payload.get("error", {})
        raise RuntimeError(f"Meta API verification failed ({err.get('code', response.status_code)}): {err.get('message', 'unknown error')}")
    return payload

account = get(USER_ID, {"fields": "id,username", "access_token": TOKEN})
media = get(MEDIA_ID, {
    "fields": "id,media_type,media_product_type,permalink,timestamp,caption",
    "access_token": TOKEN,
})
if str(account.get("id")) != USER_ID or str(media.get("id")) != MEDIA_ID:
    raise RuntimeError("Returned Instagram account or media ID did not match the requested record")
print("Verified Instagram account: @" + str(account.get("username", "unknown")))
print("Verified media ID: " + MEDIA_ID)
print("Media type: " + str(media.get("media_type", "unknown")))
print("Published at: " + str(media.get("timestamp", "unknown")))
print("Permalink: " + str(media.get("permalink", "missing")))
caption = str(media.get("caption", ""))
print("Caption: " + caption[:500])
