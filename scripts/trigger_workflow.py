#!/usr/bin/env python3
"""Trigger the email-digest workflow and print its status."""
import json
import os
import sys
import time
import urllib.request

TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
OWNER, REPO, WORKFLOW = "K9lv1n", "hermes-telegram-email-bot", "email-digest.yml"


def api(method: str, path: str, body: dict | None = None):
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
        print(f"❌ API {method} {path}: {e.code} {e.read().decode()[:300]}")
        sys.exit(1)


def main():
    # Trigger a manual run
    api("POST", f"/repos/{OWNER}/{REPO}/actions/workflows/{WORKFLOW}/dispatches",
        {"ref": "main"})
    print("🚀 Workflow triggered!")

    # Poll for the run status
    for _ in range(12):
        time.sleep(5)
        runs = api("GET", f"/repos/{OWNER}/{REPO}/actions/runs?per_page=3")["workflow_runs"]
        if runs:
            r = runs[0]
            print(f"Run: {r['name']} | Status: {r['status']} | Conclusion: {r.get('conclusion')}")
            print(f"URL: {r['html_url']}")
            if r["status"] == "completed":
                print("✅ Workflow completed!")
                return
    print("⏳ Still running — check the Actions tab.")


if __name__ == "__main__":
    main()
