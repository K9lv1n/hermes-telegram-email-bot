#!/usr/bin/env python3
"""Set GitHub Actions secrets for the email-digest workflow.

Usage: python set_secrets.py
Requires: PyNaCl (pip install pynacl)
Reads: GITHUB_TOKEN env var, plus the secret values via env vars.
"""

import json
import os
import sys
import urllib.request

TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
OWNER = "K9lv1n"
REPO = "hermes-telegram-email-bot"

SECRETS = {
    "EMAIL_ADDRESS": os.getenv("SECRET_EMAIL_ADDRESS", ""),
    "EMAIL_PASSWORD": os.getenv("SECRET_EMAIL_PASSWORD", ""),
    "TELEGRAM_BOT_TOKEN": os.getenv("SECRET_TELEGRAM_BOT_TOKEN", ""),
    "TELEGRAM_CHAT_ID": os.getenv("SECRET_TELEGRAM_CHAT_ID", ""),
}


def api(method: str, path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        method=method,
        headers={
            "Authorization": f"token {TOKEN}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "hermes-setup",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        print(f"❌ API {method} {path} failed: {e.code} {e.read().decode()[:200]}")
        sys.exit(1)


def main():
    if not TOKEN:
        print("❌ Set GITHUB_TOKEN env var first")
        sys.exit(1)
    if not all(SECRETS.values()):
        print("❌ Set all SECRET_* env vars first")
        sys.exit(1)

    try:
        from nacl import encoding, public
    except ImportError:
        print("❌ PyNaCl required: pip install pynacl")
        sys.exit(1)

    # Fetch repo public key for secret encryption
    key_data = api("GET", f"/repos/{OWNER}/{REPO}/actions/secrets/public-key")
    key_id = key_data["key_id"]
    pubkey = key_data["key"]

    for name, value in SECRETS.items():
        sealed = public.SealedBox(
            public.PublicKey(pubkey.encode("utf-8"), encoding.Base64Encoder())
        ).encrypt(value.encode("utf-8"))
        import base64
        encrypted = base64.b64encode(sealed).decode("utf-8")
        api("PUT", f"/repos/{OWNER}/{REPO}/actions/secrets/{name}",
            {"encrypted_value": encrypted, "key_id": key_id})
        print(f"✅ Set secret: {name}")


if __name__ == "__main__":
    main()
