#!/usr/bin/env python3
"""
send_to_telegram.py — send a formatted inbox summary to Telegram via Bot API.

Reads JSON from stdin (output of check_emails.py --json) and posts a
priority-grouped message to the configured chat.

Env vars required:
  TELEGRAM_BOT_TOKEN   — bot token from @BotFather
  TELEGRAM_CHAT_ID     — numeric chat/user ID to deliver to
"""

import json
import os
import sys
import urllib.request
import urllib.parse


def build_message(emails: list) -> str:
    """Format the email list into a Telegram-friendly message."""
    if not emails:
        return "📬 No new emails! Inbox is caught up."

    groups = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for e in emails:
        groups.get(e.get("priority", "LOW"), groups["LOW"]).append(e)

    lines = ["📬 Inbox Check", "━━━━━━━━━━━━━━━"]
    for level, icon in (("HIGH", "🔴"), ("MEDIUM", "🟡"), ("LOW", "🔵")):
        items = groups[level]
        lines.append("")
        lines.append(f"{icon} {level} ({len(items)})")
        if not items:
            lines.append("  (none)")
        for i, e in enumerate(items[:10], 1):
            subj = e.get("subject", "")[:60]
            sender = e.get("from", "").split("<")[0].strip()[:30]
            lines.append(f"{i}. {subj}")
            lines.append(f"   📨 {sender}")

    return "\n".join(lines)


def send_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
        if not result.get("ok"):
            raise RuntimeError(f"Telegram API error: {result}")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("❌ Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID", file=sys.stderr)
        sys.exit(1)

    emails = json.load(sys.stdin)
    message = build_message(emails)
    send_message(token, chat_id, message)
    print(f"✅ Sent {len(emails)} email summary to chat {chat_id}")


if __name__ == "__main__":
    main()
