#!/usr/bin/env python3
"""
should_run.py — dedupe gate for the email digest.

Problem: GitHub's native `schedule:` is best-effort and often runs *hours* late.
To get punctual delivery we trigger the workflow externally (e.g. cron-job.org)
at exactly 09:00 / 21:00 SGT. But GitHub's own late scheduled run would then
fire a second digest minutes/hours later.

Solution: define 12-hour "slots" aligned to the delivery times and skip the run
if a successful digest has already gone out in the current slot.

Slots (UTC): 01:00–13:00 and 13:00–01:00  (= 09:00–21:00 and 21:00–09:00 SGT)

Prints "yes" (run) or "no" (skip). Fails open — if the API can't be reached it
prints "yes" so a digest is never silently dropped.

Env: GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID, WORKFLOW_FILE, FORCE_RUN
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
import urllib.request

SLOT_HOURS_UTC = (1, 13)  # 01:00 & 13:00 UTC = 09:00 & 21:00 SGT


def current_slot_start(now: datetime) -> datetime:
    """Start of the current 12h delivery slot, in UTC."""
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    a = today.replace(hour=SLOT_HOURS_UTC[0])   # 01:00
    b = today.replace(hour=SLOT_HOURS_UTC[1])   # 13:00
    if now >= b:
        return b
    if now >= a:
        return a
    return b - timedelta(days=1)                # early morning → previous slot


def api(path: str, token: str) -> dict:
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "email-digest-gate",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode() or "{}")


def main() -> None:
    if (os.getenv("FORCE_RUN") or "").strip().lower() in ("1", "true", "yes"):
        print("yes")
        return

    token = os.getenv("GITHUB_TOKEN", "").strip()
    repo = os.getenv("GITHUB_REPOSITORY", "").strip()
    wf = os.getenv("WORKFLOW_FILE", "email-digest.yml")
    this_run = os.getenv("GITHUB_RUN_ID", "").strip()

    if not token or not repo:
        print("yes")  # can't check → don't lose the digest
        return

    now = datetime.now(timezone.utc)
    slot_start = current_slot_start(now)

    try:
        data = api(
            f"/repos/{repo}/actions/workflows/{wf}/runs?per_page=30&status=success",
            token,
        )
        runs = data.get("workflow_runs", [])
    except Exception as exc:  # noqa: BLE001
        print(f"gate: API error ({exc}) → running anyway", file=sys.stderr)
        print("yes")
        return

    for r in runs:
        if str(r.get("id")) == this_run:
            continue
        created = r.get("created_at")
        if not created:
            continue
        try:
            created_dt = datetime.strptime(created, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        if created_dt >= slot_start:
            print(
                f"gate: digest already sent in this slot "
                f"(run {r['id']} at {created}) → skipping",
                file=sys.stderr,
            )
            print("no")
            return

    print(f"gate: no digest yet in slot starting {slot_start} → running",
          file=sys.stderr)
    print("yes")


if __name__ == "__main__":
    main()
