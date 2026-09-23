"""Isolated TikTok publisher via Buffer. Instagram/Threads state is never written."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from publish_threads import PublishError, approved_reels, now

CHANNEL_ID = "6ab41d16ea19ca0bdec9454b"
USERNAME = "jinwoo.jang5"
POST_FIELDS = "id channelId text status schedulingType externalLink sentAt error { message }"


def validate(reel):
    url = urlparse(reel["video_url"])
    if (url.scheme != "https" or url.netloc != "raw.githubusercontent.com"
            or not url.path.startswith("/canakard1000/characzone-auto-reels/")
            or not url.path.endswith(".mp4") or url.query or url.fragment):
        raise PublishError("Video must be an MP4 in this repository's public raw URLs")
    caption = reel.get("caption")
    if not isinstance(caption, str) or not 1 <= len(caption) <= 2200:
        raise PublishError("TikTok caption must contain 1 to 2200 characters")
    if len(re.findall(r"(?<!\w)#[^\s#]+", caption)) > 5:
        raise PublishError("TikTok accepts at most five hashtags; caption was not truncated")
    if "tiktok_is_ai_generated" in reel and type(reel["tiktok_is_ai_generated"]) is not bool:
        raise PublishError("tiktok_is_ai_generated must be a boolean")


def post_input(reel):
    result = {"channelId": CHANNEL_ID, "text": reel["caption"],
              "schedulingType": "automatic", "mode": "shareNow", "needsApproval": False,
              "saveToDraft": False, "assets": [{"video": {"url": reel["video_url"]}}]}
    if "tiktok_is_ai_generated" in reel:
        result["metadata"] = {"tiktok": {"isAiGenerated": reel["tiktok_is_ai_generated"]}}
    return result


def fingerprint(reel):
    return hashlib.sha256(json.dumps(post_input(reel), sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Buffer:
    def __init__(self, token):
        self.token = token
        self.organization_id = None

    def safe(self, text):
        text = str(text).replace(self.token, "[REDACTED]")
        return re.sub(r"https?://\S+|[A-Za-z0-9_\-]{50,}", "[REDACTED]", text)[:500]

    def api(self, query, variables):
        try:
            response = requests.post("https://api.buffer.com", timeout=(10, 120),
                                     headers={"Authorization": f"Bearer {self.token}"},
                                     json={"query": query, "variables": variables})
            payload = response.json()
        except (requests.RequestException, ValueError):
            raise PublishError("Buffer transport/JSON failure; reconcile saved phase before retry") from None
        if not response.ok or payload.get("errors"):
            errors = "; ".join(str(e.get("message", "API error")) for e in payload.get("errors", []))
            raise PublishError(f"Buffer HTTP {response.status_code}: {self.safe(errors)}")
        if not isinstance(payload.get("data"), dict):
            raise PublishError("Buffer response has no data")
        return payload["data"]

    def preflight(self):
        channel = self.api('''query($input: ChannelInput!) { channel(input:$input) {
          id name service organizationId externalLink isDisconnected isLocked
          metadata { ... on TiktokMetadata { defaultToReminders } }
        }}''', {"input": {"id": CHANNEL_ID}})["channel"]
        if (channel.get("id") != CHANNEL_ID or channel.get("service") != "tiktok"
                or channel.get("name", "").lstrip("@") != USERNAME
                or channel.get("isDisconnected") is not False or channel.get("isLocked") is not False):
            raise PublishError("Buffer channel is not the connected, unlocked TikTok @jinwoo.jang5")
        if channel.get("metadata", {}).get("defaultToReminders") is not False:
            raise PublishError("TikTok automatic publishing is not confirmed; reminders are not automatic posts")
        self.organization_id = channel["organizationId"]
        print(f"Verified Buffer TikTok channel @{USERNAME}; automatic publishing enabled")
        # Also exercise posts:read before any write.
        self.list_posts(first=1)

    def list_posts(self, first=50, after=None):
        return self.api('''query($input: PostsInput!, $first:Int, $after:String) {
          posts(input:$input,first:$first,after:$after) {
            edges { node { id text assets { source } } }
            pageInfo { hasNextPage endCursor }
          }}''', {"input": {"organizationId": self.organization_id,
                              "filter": {"channelIds": [CHANNEL_ID]}},
                  "first": first, "after": after})["posts"]

    def check_duplicate(self, reel):
        cursor = None
        for _ in range(10):
            page = self.list_posts(after=cursor)
            for edge in page.get("edges") or []:
                post = edge["node"]
                same_source = any(a.get("source") == reel["video_url"] for a in post.get("assets", []))
                # Initial migration: also recognize a manually submitted reel05.
                same_initial_caption = reel["id"] == "characzone-reel-05" and post.get("text") == reel["caption"]
                if same_source or same_initial_caption:
                    raise PublishError(f"Possible existing TikTok post {post['id']}; reconcile before creating another")
            info = page["pageInfo"]
            if not info["hasNextPage"]:
                return
            cursor = info.get("endCursor")
            if not cursor:
                break
        raise PublishError("Could not finish duplicate check; no post created")

    def create(self, reel):
        result = self.api('''mutation($input: CreatePostInput!) {
          createPost(input:$input) { __typename
            ... on PostActionSuccess { post { id } }
            ... on MutationError { message }
          }}''', {"input": post_input(reel)})["createPost"]
        if not result.get("post", {}).get("id"):
            raise PublishError("Buffer rejected createPost: " + self.safe(result.get("message", result.get("__typename"))))
        return str(result["post"]["id"])

    def post(self, post_id):
        return self.api('query($input: PostInput!) { post(input:$input) { ' + POST_FIELDS + ' }}',
                        {"input": {"id": post_id}})["post"]


class GitLedger:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        if self.git("branch", "--show-current") != "tiktok-publish-state":
            raise PublishError("TikTok ledger must use tiktok-publish-state, never main")
        self.path = self.directory / "tiktok-state.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {"reels": {}}

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.directory), *args], capture_output=True, text=True)
        if result.returncode:
            raise PublishError("TikTok state persistence failed; publication stopped")
        return result.stdout.strip()

    def get(self, reel_id):
        return self.data["reels"].get(reel_id, {}).copy()

    def save(self, reel_id, entry):
        self.data["reels"][reel_id] = {**entry, "updated_at": now()}
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n")
        self.git("add", "tiktok-state.json")
        self.git("-c", "user.name=characzone-social-bot", "-c",
                 "user.email=actions@users.noreply.github.com", "commit", "-m", "Save TikTok publication phase")
        self.git("push", "origin", "HEAD:tiktok-publish-state")


def publish_one(reel, client, ledger, check_approval=lambda: None, sleep=time.sleep, polls=18):
    validate(reel)
    entry = ledger.get(reel["id"])
    if entry.get("phase") == "published":
        return "already_published"
    if entry and entry.get("fingerprint") != fingerprint(reel):
        raise PublishError("Reel changed after submission; reconcile before retry")
    if entry.get("phase") in {"creating", "failed", "needs_review"}:
        raise PublishError("Previous uncertain/failed attempt needs review; no duplicate upload")
    if not entry:
        client.check_duplicate(reel)
        check_approval()
        entry = {"phase": "creating", "fingerprint": fingerprint(reel), "channel_id": CHANNEL_ID}
        ledger.save(reel["id"], entry)  # Durable write BEFORE non-idempotent mutation.
        post_id = client.create(reel)
        entry = {**entry, "phase": "submitted", "buffer_post_id": post_id}
        ledger.save(reel["id"], entry)
    post_id = entry["buffer_post_id"]
    for attempt in range(polls):
        post = client.post(post_id)
        if post.get("channelId") != CHANNEL_ID or post.get("text") != reel["caption"]:
            raise PublishError("Saved Buffer post target/content mismatch")
        if post.get("schedulingType") != "automatic":
            ledger.save(reel["id"], {**entry, "phase": "needs_review"})
            raise PublishError("Buffer used notification publishing; no automatic success recorded")
        status = post.get("status")
        if status == "sent":
            ledger.save(reel["id"], {**entry, "phase": "published", "published_at": post.get("sentAt") or now(),
                                     "external_link": post.get("externalLink")})
            print(f"TikTok published: {post.get('externalLink') or post_id}")
            return "published"
        if status not in {"scheduled", "sending"}:
            ledger.save(reel["id"], {**entry, "phase": "failed", "status": status})
            raise PublishError("Buffer publication stopped: " + client.safe((post.get("error") or {}).get("message", status)))
        if attempt < polls - 1:
            sleep(10)
    print(f"Buffer post {post_id} still processing; next run only checks the same post")
    return "submitted"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--manifest", default="approved.json")
    parser.add_argument("--state-dir", default=".tiktok-state")
    args = parser.parse_args()
    manifest = Path(args.manifest)
    reels = approved_reels(json.loads(manifest.read_text()))
    for reel in reels:
        validate(reel)
    token = os.getenv("BUFFER_API_KEY", "").strip()
    if not token:
        raise PublishError("Missing BUFFER_API_KEY; no post sent")
    client = Buffer(token)
    client.preflight()
    print(f"Approved and due TikTok reels: {len(reels)}")
    if not args.publish:
        print("Read-only preflight passed; no post created")
        return
    ledger = GitLedger(args.state_dir)
    for reel in reels:
        if ledger.get(reel["id"]).get("phase") == "published":
            continue
        def check_approval():
            if reel not in approved_reels(json.loads(manifest.read_text())):
                raise PublishError("Approval/content changed before TikTok submission")
        print(f"TikTok result: {reel['id']}: {publish_one(reel, client, ledger, check_approval)}")
        return
    print("All approved and due reels already published to TikTok")


if __name__ == "__main__":
    try:
        main()
    except (PublishError, KeyError, ValueError, OSError) as exc:
        print(f"::error::{exc if isinstance(exc, PublishError) else 'Invalid configuration or state'}")
        sys.exit(1)
