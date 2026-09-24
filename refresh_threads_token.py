"""Renew the existing Threads long-lived token without printing credentials."""
import hmac
import base64
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from publish_threads import Threads, PublishError


RECOVERY_PUBLIC_KEY = 'LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQm9qQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FZOEFNSUlCaWdLQ0FZRUFyczdCY0lLNy9yUnJVQVNDWFZQWgoxQ08xQ3E3MVVNSTM4R1NOcmVaM3prZU4xNnJ4UElMeldUNWNlTVZPNWVJQUJidkY5SUdZMkk3VG0wYjR0a3FOCldQY09KU21ucERSQVY3V1ljME0xQlQ2eEFJdVVQb0FEbFhBZU9xdWtOM3M2My9rY2ZiM2pYUmh4RHBaVGRqME8KREY3Y25ZSWozWVViZUhjN2swU1lKdURJOG5yQ0Foa0VRRnZZR29PMklKYmRoQlR3WUN3TnBsdHZIUmZHYS94NQp5QjB0SFlSNTg0MmRaU1lPR05HOU9lbFcxL2p1d0JDOUlTMmxPSjlaaGt3bGVSZ0YyM2lVbHJ1QVlIZ0R1ODFzCjZTR0xERGR0b1daU0VSNHY5WGFaaGl0SDF3RkdSZXliNU9pNWpjRkJRNEdZbW45VnJiN0pjTFNDOXZESjVRR1IKODR2dXFMMFpXbktoM1FLN1JISHpBL3hUM082aThJdlRoRWpBNU5rSk5YMSttYk10Ukd2UEEzc2ZuNWJPTGtFVgphdHo4ekgxOEpBV0I1WDBoVndxbEZsZ0o4TXVsbE51OW1kSDZ4eENvNzR5QWs0dnBXYkRtWEF5aWJHOW90anBTCiszUGlSU2hNTUh5WWJuRncvYmxsWXJYYis4ODJzNGhSVEM3bzZVdE02WkJOQWdNQkFBRT0KLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0tCg=='


def seal(payload, public_key):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
    public = serialization.load_pem_public_key(base64.b64decode(public_key))
    wrapped = public.encrypt(key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    encrypted = AESGCM(key).encrypt(nonce, json.dumps(payload).encode(), b"threads-refresh")
    return base64.b64encode(json.dumps([base64.b64encode(v).decode() for v in (wrapped, nonce, encrypted)]).encode()).decode()


def refresh(token, request=requests.get, recovery_public_key=None):
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
        detail = str(data.get("error", {}).get("message", "")).replace(token, "[REDACTED]")
        detail = re.sub(r"https?://\S+|[A-Za-z0-9_\-]{30,}", "[REDACTED]", detail)[:300]
        raise PublishError(f"Threads renewal rejected (HTTP {response.status_code}, code {code}): {detail}")
    renewed = data.get("access_token")
    lifetime = data.get("expires_in")
    if not isinstance(renewed, str) or not renewed or type(lifetime) is not int or lifetime <= 0:
        raise PublishError("Invalid renewal response; no success recorded")
    # Never silently discard a rotated credential or claim Secrets were updated.
    if not hmac.compare_digest(renewed, token):
        if recovery_public_key:
            Threads(renewed, "").preflight()
            envelope = seal({"access_token": renewed, "expires_in": lifetime, "refreshed_at": datetime.now(timezone.utc).isoformat()}, recovery_public_key)
            print("ENCRYPTED_THREADS_REFRESH=" + envelope)
            raise PublishError("Token renewed and verified; encrypted handoff ready. GitHub Secret replacement remains pending")
        raise PublishError("Threads returned a different token; secure Secret replacement is required. No token was logged or saved")
    return lifetime


def main():
    token = os.environ.get("THREADS_ACCESS_TOKEN", "").strip()
    if not token:
        raise PublishError("Missing THREADS_ACCESS_TOKEN")
    client = Threads(token, os.environ.get("THREADS_USER_ID", "").strip())
    client.preflight()
    lifetime = refresh(token, recovery_public_key=RECOVERY_PUBLIC_KEY)
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
