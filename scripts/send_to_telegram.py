#!/usr/bin/env python3
"""
send_to_telegram.py — deliver an inbox summary to Telegram.

Reads JSON from stdin (output of check_emails.py --json).

If DEEPSEEK_API_KEY is set, the email list is sent to DeepSeek to produce a
readable, narrative summary (the same style the Hermes agent produces).
Otherwise it falls back to a clean static format.

Env vars:
  TELEGRAM_BOT_TOKEN   — bot token from @BotFather
  TELEGRAM_CHAT_ID     — numeric chat/user ID
  DEEPSEEK_API_KEY     — optional; enables the readable narrative summary
  DEEPSEEK_BASE_URL    — optional; defaults to https://api.deepseek.com
"""

import json
import os
import sys
import urllib.request
import urllib.parse


# ---------------------------------------------------------------------------
# Static fallback formatter
# ---------------------------------------------------------------------------

def build_static_message(emails: list) -> str:
    if not emails:
        return "📬 No new emails! Inbox is caught up."

    groups = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for e in emails:
        groups.setdefault(e.get("priority", "LOW"), []).append(e)

    lines = [f"📬 **Inbox Check** — {len(emails)} new email(s)", ""]
    for level, icon in (("HIGH", "🔴"), ("MEDIUM", "🟡"), ("LOW", "🔵")):
        items = groups[level]
        lines.append(f"{icon} **{level} ({len(items)})**")
        if not items:
            lines.append("  (none)")
        for i, e in enumerate(items[:10], 1):
            sender = e.get("from", "").split("<")[0].strip().strip('"')[:35]
            lines.append(f"{i}. **{sender}** — {e.get('subject', '')[:70]}")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------------------------------------------------------
# DeepSeek narrative summary
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a concise email assistant writing a Telegram inbox digest.

Format your reply EXACTLY like this:
- First line: `📬 **Inbox Check** — N new emails, all marked as read`
- A short assessment paragraph (1-3 sentences): is anything urgent/actionable? \
If the only "urgent" hits are clearly promos or notifications, say so plainly.
- Then sections in this order, only including non-empty ones:
  `🔴 **HIGH (n)**` / `🟡 **MEDIUM (n)**` / `🔵 **LOW (n)**
  Each item numbered as `N. **Sender** — Subject` on one line, optionally \
followed by a short indented note on the next line when useful.
- End with a `Net:` line summarising whether anything needs attention.

Rules:
- No markdown tables, no code blocks, no headings (#).
- Keep it under 350 words. Be genuinely useful, not padded.
- If nothing needs attention, say that clearly up front."""


def summarize_with_deepseek(emails: list, api_key: str, base_url: str) -> str:
    """Ask DeepSeek for a readable narrative summary. Raises on failure."""
    lines = []
    for e in emails:
        lines.append(
            f"From: {e.get('from','')}\n"
            f"Subject: {e.get('subject','')}\n"
            f"Date: {e.get('date','')}\n"
            f"Keyword-priority: {e.get('priority','LOW')}\n"
            f"Preview: {e.get('preview','')[:180]}\n"
        )
    user_content = (
        f"Summarize these {len(emails)} inbox emails for my Telegram digest.\n\n"
        + "\n---\n".join(lines)
    )

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.3,
        "max_tokens": 900,
    }

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        body = json.loads(resp.read().decode())
    return body["choices"][0]["message"]["content"].strip()


# ---------------------------------------------------------------------------
# Telegram delivery
# ---------------------------------------------------------------------------

def send_message(token: str, chat_id: str, text: str) -> None:
    """Send via Bot API, falling back to plain text if Markdown parsing fails."""
    for parse_mode in ("Markdown", None):
        data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
        if parse_mode:
            data["parse_mode"] = parse_mode
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=urllib.parse.urlencode(data).encode(),
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
            if result.get("ok"):
                return
        except urllib.error.HTTPError as e:
            if parse_mode and e.code == 400:
                continue  # Markdown parse error → retry as plain text
            raise
    raise RuntimeError("Telegram delivery failed")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    if not token or not chat_id:
        print("❌ Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID", file=sys.stderr)
        sys.exit(1)

    emails = json.load(sys.stdin)

    if not emails:
        print("No new emails — nothing to send.")
        return

    message = build_static_message(emails)
    if deepseek_key:
        try:
            message = summarize_with_deepseek(emails, deepseek_key, base_url)
            print("Summarized with DeepSeek")
        except Exception as exc:  # noqa: BLE001 — fall back to static format
            print(f"⚠️ DeepSeek summary failed ({exc}); using static format", file=sys.stderr)

    send_message(token, chat_id, message)
    print(f"✅ Sent summary of {len(emails)} emails to chat {chat_id}")


if __name__ == "__main__":
    main()
