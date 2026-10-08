#!/usr/bin/env python3
"""
check_emails.py — Gmail inbox checker with priority ranking.

Two selection modes:
  --since-hours N   → messages received in the last N hours (time-based,
                      independent of read/unread state). Best for scheduled
                      digests, because other IMAP clients (or Hermes's own
                      Email gateway adapter) may mark mail as read.
  (default)         → UNSEEN messages. Best for interactive "check my emails".

Requirements: Python 3.10+ and a Gmail App Password. No third-party deps.

Usage:
  export EMAIL_ADDRESS=you@gmail.com
  export EMAIL_PASSWORD="abcd efgh ijkl mnop"   # app password
  python check_emails.py --since-hours 12 --json
  python check_emails.py --limit 10 --mark-read

Author: K9lv1n
License: MIT
"""

import argparse
import email
import imaplib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.header import decode_header
from email.utils import parsedate_to_datetime

# ---------------------------------------------------------------------------
# Priority classification
# ---------------------------------------------------------------------------

HIGH_KEYWORDS = [
    "deadline", "urgent", "important", "asap", "due", "overdue",
    "payment", "invoice", "bill", "exam", "final", "warning",
]

MEDIUM_KEYWORDS = [
    "project", "assignment", "class", "meeting", "lecture", "tutorial",
    "homework", "group", "course", "quiz", "test", "lab", "report",
    "school", "work", "job",
]


def classify_priority(subject: str, body: str = "") -> str:
    text = f"{subject} {body}".lower()
    if any(k in text for k in HIGH_KEYWORDS):
        return "HIGH"
    if any(k in text for k in MEDIUM_KEYWORDS):
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# IMAP helpers
# ---------------------------------------------------------------------------

def decode_mime_header(raw: str) -> str:
    if not raw:
        return ""
    out = []
    for part, charset in decode_header(raw):
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out).strip()


def get_body_preview(msg, max_chars: int = 300) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")[:max_chars]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")[:max_chars]
    return ""


def message_datetime(msg) -> datetime | None:
    """Parse the Date header into an aware datetime (UTC), or None."""
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_env(path: str = ".env") -> dict:
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(description="Check Gmail and rank by priority.")
    p.add_argument("--limit", type=int, default=10, help="Max emails (default 10)")
    p.add_argument("--mark-read", action="store_true", help="Mark fetched emails SEEN")
    p.add_argument("--json", action="store_true", help="Emit JSON")
    p.add_argument("--since-hours", type=float, default=None,
                   help="Only include mail received in the last N hours "
                        "(time-based; ignores read/unread state)")
    p.add_argument("--env-file", default=".env", help="Path to .env")
    args = p.parse_args()

    # Credentials: env vars first, then the local .env, then the project .env.
    env = load_env(args.env_file)
    if not env:
        env = load_env(os.path.expanduser("~/hermes-telegram-email-bot/.env"))
    addr = (os.getenv("GMAIL_USER") or os.getenv("EMAIL_ADDRESS")
            or env.get("GMAIL_USER") or env.get("EMAIL_ADDRESS"))
    pw = (os.getenv("GMAIL_APP_PASSWORD") or os.getenv("EMAIL_PASSWORD")
          or env.get("GMAIL_APP_PASSWORD") or env.get("EMAIL_PASSWORD"))
    host = (os.getenv("EMAIL_IMAP_HOST") or env.get("EMAIL_IMAP_HOST")
            or "imap.gmail.com")

    if not addr or not pw:
        print("❌ Missing GMAIL_USER/GMAIL_APP_PASSWORD (or EMAIL_ADDRESS/"
              "EMAIL_PASSWORD). See .env.example.", file=sys.stderr)
        sys.exit(1)

    try:
        M = imaplib.IMAP4_SSL(host, 993)
        M.login(addr, pw)
        M.select("INBOX")
    except imaplib.IMAP4.error as e:
        print(f"❌ IMAP login failed: {e}", file=sys.stderr)
        print("   (Gmail requires an App Password + 2FA.)", file=sys.stderr)
        sys.exit(1)

    # ---- Choose candidate messages -------------------------------------
    cutoff = None
    if args.since_hours is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=args.since_hours)
        # IMAP SINCE is date-granular; search a wider window then filter locally.
        search_since = (cutoff - timedelta(days=1)).strftime("%d-%b-%Y")
        status, data = M.search(None, "SINCE", search_since)
    else:
        status, data = M.search(None, "UNSEEN")

    ids = data[0].split() if (status == "OK" and data and data[0]) else []
    candidates = ids[-args.limit:] if len(ids) >= args.limit else ids

    emails = []
    for e_id in reversed(candidates):
        _, msg_data = M.fetch(e_id, "(BODY.PEEK[])")  # PEEK: don't set \Seen
        if not msg_data or not msg_data[0]:
            continue
        raw = msg_data[0][1]
        if isinstance(raw, tuple):
            raw = raw[0]
        msg = message_from_bytes(raw)

        sent = message_datetime(msg)
        if cutoff and (sent is None or sent < cutoff):
            continue  # outside the requested window

        subject = decode_mime_header(msg["Subject"])
        body = get_body_preview(msg)
        emails.append({
            "from": msg["From"] or "",
            "subject": subject,
            "date": msg["Date"] or "",
            "preview": body[:200].replace("\n", " ").replace("\r", " "),
            "priority": classify_priority(subject, body),
        })

    # Oldest-first reads more naturally in a digest
    emails.reverse()

    if args.mark_read and candidates:
        for e_id in candidates:
            M.store(e_id, "+FLAGS", "\\Seen")

    M.logout()

    if args.json:
        print(json.dumps(emails, indent=2, ensure_ascii=False))
        return

    if not emails:
        print("📬 No new emails! Inbox is caught up.")
        return

    groups = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for e in emails:
        groups[e["priority"]].append(e)

    print("📬 Inbox Check")
    print("━━━━━━━━━━━━━━━")
    for level, icon in (("HIGH", "🔴"), ("MEDIUM", "🟡"), ("LOW", "🔵")):
        items = groups[level]
        print(f"\n{icon} {level} ({len(items)})")
        for i, e in enumerate(items, 1):
            print(f"{i}. [{e['from']}] — {e['subject']}")
            print(f"   📅 {e['date']} | 👁️ {e['preview'][:80]}...")


if __name__ == "__main__":
    main()
