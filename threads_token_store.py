"""Encrypted Threads token state. The bootstrap Secret remains the stable root key."""
import base64
import json
import os
import subprocess
from pathlib import Path

CONTEXT = b"canakard1000/characzone-auto-reels/threads-token-state/v1"


def seal(state, secret):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, nonce = os.urandom(32), os.urandom(12)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=CONTEXT).derive(secret.encode())
    encrypted = AESGCM(key).encrypt(nonce, json.dumps(state).encode(), CONTEXT)
    return {"version": 1, **{k: base64.b64encode(v).decode() for k, v in
                            (("salt", salt), ("nonce", nonce), ("ciphertext", encrypted))}}


def unseal(envelope, secret):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if envelope["version"] != 1:
        raise ValueError("Unsupported credential state")
    salt, nonce, ciphertext = [base64.b64decode(envelope[k], validate=True)
                               for k in ("salt", "nonce", "ciphertext")]
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=CONTEXT).derive(secret.encode())
    return json.loads(AESGCM(key).decrypt(nonce, ciphertext, CONTEXT))


class TokenStore:
    def __init__(self, directory, root_secret):
        if not root_secret:
            raise ValueError("Missing Threads root Secret")
        self.directory = Path(directory)
        self.path = self.directory / "threads-token.enc.json"
        self.root_secret = root_secret

    def read(self):
        # A missing checkout is an error, not a reason to use an obsolete token.
        if not self.directory.is_dir():
            raise ValueError("Missing Threads token state checkout")
        if not self.path.exists():
            return {}
        return unseal(json.loads(self.path.read_text()), self.root_secret)

    def save(self, state):
        def git(*args):
            return subprocess.run(["git", "-C", str(self.directory), *args],
                                  check=True, capture_output=True, text=True).stdout.strip()
        if git("branch", "--show-current") != "threads-token-state":
            raise ValueError("Refusing credential write outside threads-token-state")
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(seal(state, self.root_secret)) + "\n")
        temporary.replace(self.path)
        git("config", "user.name", "github-actions[bot]")
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
        git("add", "--", self.path.name)
        git("commit", "-m", "Update encrypted Threads credential state")
        git("push", "origin", "HEAD:threads-token-state")


def current_token(directory, root_secret):
    state = TokenStore(directory, root_secret).read()
    if state.get("pending"):
        raise ValueError("Threads credential validation pending; rerun refresh workflow")
    active = state.get("active")
    if not active:
        return root_secret
    token = active["access_token"]
    if not isinstance(token, str) or not token:
        raise ValueError("Invalid active Threads credential")
    return token
