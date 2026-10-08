#!/usr/bin/env python3
"""
trigger_digest.py — punctual trigger for the email-digest workflow.

Why this exists: GitHub's native `schedule:` is best-effort and routinely runs
hours late. A local trigger fires at exactly 09:00 / 21:00 SGT and tells GitHub
to run the workflow *now* (dispatches execute immediately).

Used as a Hermes cron job (no_agent mode) — silent on success, prints only on
failure so the user is alerted when something breaks.

Token resolution (first hit wins):
  1. GITHUB_TOKEN environment variable
  2. ~/AppData/Local/hermes/.env      (Windows Hermes home)
  3. ~/.hermes/.env                   (POSIX Hermes home)
  4. ~/hermes-telegram-email-bot/.env (project local env)

Needs a token with Actions: write on the repo.
"""

import json
import os
import sys
import urllib.error
import urllib.request

OWNER = os.getenv("DIGEST_REPO_OWNER", "K9lv1n")
REPO = os.getenv("DIGEST_REPO_NAME", "hermes-telegram-email-bot")
WORKFLOW = os.getenv("DIGEST_WORKFLOW", "email-digest.yml")

ENV_CANDIDATES = [
    os.path.expanduser("~/AppData/Local/hermes/.env"),
    os.path.expanduser("~/.hermes/.env"),
    os.path.expanduser("~/hermes-telegram-email-bot/.env"),
]


def token_from_files() -> str:
    for path in ENV_CANDIDATES:
        if not os.path.exists(path):
            continue
        try:
            for line in open(path, encoding="utf-8"):
                line = line.strip()
                if line.startswith("GITHUB_TOKEN="):
                    return line.partition("=")[2].strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def main() -> None:
    token = (os.getenv("GITHUB_TOKEN") or "").strip() or token_from_files()
    if not token:
        print("⚠️ Email digest trigger failed: no GitHub token found "
              "(set GITHUB_TOKEN in the Hermes env file)")
        return

    url = (f"https://api.github.com/repos/{OWNER}/{REPO}"
           f"/actions/workflows/{WORKFLOW}/dispatches")
    req = urllib.request.Request(
        url,
        data=json.dumps({"ref": "main"}).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "hermes-digest-trigger",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
        if status not in (200, 204):
            print(f"⚠️ Email digest trigger: unexpected HTTP {status}")
        # success → print nothing (the cron job stays silent)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:200]
        print(f"⚠️ Email digest trigger failed: HTTP {exc.code} {detail}")
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️ Email digest trigger failed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
