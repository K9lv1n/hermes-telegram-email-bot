#!/usr/bin/env python3
"""
check_emails.py — standalone Gmail inbox checker with priority ranking.

This is the same logic the Hermes `gmail-check` skill runs, packaged as a
standalone script so you can use it WITHOUT the Hermes harness.

Requirements:
  - Python 3.10+
  - Gmail account with 2FA + an App Password (see .env.example)

Usage:
  export EMAIL_ADDRESS=you@gmail.com
  export EMAIL_PASSWORD="abcd efgh ijkl mnop"   # app password
  python check_emails.py [--limit 10] [--mark-read] [--json]

The script reads EMAIL_ADDRESS / EMAIL_PASSWORD from the environment
(or a local .env file) so credentials never live in code.

Author: K9lv1n
License: MIT
"""

import argparse
import email
import imaplib
import json
import os
import re
import sys
from email import message_from_bytes
from email.header import decode_header

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
    """Classify an email as HIGH / MEDIUM / LOW by keyword matching."""
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
    """Decode RFC 2047 encoded headers (e.g. =?utf-8?B?...?=)."""
    if not raw:
        return ""
    parts = decode_header(raw)
    out = []
    for part, charset in parts:
        if isinstance(part, bytes):
            out.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out).strip()


def get_body_preview(msg, max_chars: int = 300) -> str:
    """Extract a plain-text preview from a MIME message."""
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


def load_env(path: str = ".env") -> dict:
    """Minimal .env loader (no external deps)."""
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
    parser = argparse.ArgumentParser(description="Check Gmail inbox and rank by priority.")
    parser.add_argument("--limit", type=int, default=10, help="Max emails to fetch (default 10)")
    parser.add_argument("--mark-read", action="store_true", help="Mark fetched emails as SEEN")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of a summary")
    parser.add_argument("--env-file", default=".env", help="Path to .env file (default ./.env)")
    args = parser.parse_args()

    # Credentials: explicit env > .env file
    env = load_env(args.env_file)
    email_addr = os.getenv("EMAIL_ADDRESS") or env.get("EMAIL_ADDRESS")
    email_pass = os.getenv("EMAIL_PASSWORD") or env.get("EMAIL_PASSWORD")
    imap_host = os.getenv("EMAIL_IMAP_HOST") or env.get("EMAIL_IMAP_HOST") or "imap.gmail.com"

    if not email_addr or not email_pass:
        print("❌ Missing credentials. Set EMAIL_ADDRESS and EMAIL_PASSWORD "
              "(see .env.example).", file=sys.stderr)
        sys.exit(1)

    # Connect
    try:
        M = imaplib.IMAP4_SSL(imap_host, 993)
        M.login(email_addr, email_pass)
        M.select("INBOX")
    except imaplib.IMAP4.error as e:
        print(f"❌ IMAP login failed: {e}", file=sys.stderr)
        print("   (For Gmail: use an App Password, not your real password.)", file=sys.stderr)
        sys.exit(1)

    # Fetch unread
    status, data = M.search(None, "UNSEEN")
    ids = data[0].split() if data and data[0] else []
    recent = ids[-args.limit:] if len(ids) >= args.limit else ids

    emails = []
    for e_id in reversed(recent):
        _, msg_data = M.fetch(e_id, "(RFC822)")
        msg = message_from_bytes(msg_data[0][1])
        subject = decode_mime_header(msg["Subject"])
        body = get_body_preview(msg)
        emails.append({
            "from": msg["From"] or "",
            "subject": subject,
            "date": msg["Date"] or "",
            "preview": body[:200].replace("\n", " ").replace("\r", " "),
            "priority": classify_priority(subject, body),
        })

    # Mark read if requested
    if args.mark_read and recent:
        for e_id in recent:
            M.store(e_id, "+FLAGS", "\\Seen")

    M.logout()

    # Output
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
