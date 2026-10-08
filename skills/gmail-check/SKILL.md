---
name: gmail-check
description: "Use Python's built-in imaplib to check Gmail, fetch recent emails, and summarize by priority. No external CLI tools needed. Triggered when user asks 'check my emails', 'inbox', 'what's in my inbox', 'email summary', 'any new emails', 'read my emails', 'show my inbox'."
version: 1.2.0
author: Hermes Agent
tags: [email, gmail, imap, inbox]
---

# Gmail Check

⚠️ IMPORTANT: Do NOT use the `himalaya` CLI or `himalaya` skill. This skill uses Python's built-in `imaplib` — no external tools needed.

## Trigger phrases
"check my emails", "inbox", "email summary", "what's in my inbox", "any new emails", "read my emails", "show my inbox", "gmail"

## Credentials

Resolve in this order (first hit wins):
1. `GMAIL_USER` / `GMAIL_APP_PASSWORD` environment variables
2. `EMAIL_ADDRESS` / `EMAIL_PASSWORD` environment variables
3. The project's local env file: `~/hermes-telegram-email-bot/.env` (git-ignored)

⚠️ Use the `GMAIL_*` names, not `EMAIL_*`, in the gateway environment. Setting
`EMAIL_ADDRESS` makes Hermes auto-connect the **Email gateway adapter**, which
relays mail into the agent and marks it read (setting Gmail's `\Seen` flag).
`GMAIL_*` provides the same credentials without enabling that adapter.

If no credentials are found, say so and stop — do not guess.

## Steps

1. Connect to Gmail over IMAP SSL (`imap.gmail.com:993`) with `imaplib`.
2. **Select by arrival time, not unread state.** Default window: the last 24 hours.
   Rationale: fetching a message body implicitly sets Gmail's `\Seen` flag, and other
   IMAP clients (the phone mail app, webmail, Hermes's own Email adapter) mark mail read
   as soon as they fetch it — so an "unread-only" query returns nothing.
3. Fetch at most 15 messages with `BODY.PEEK[]` so reading never mutates read state.
4. For each: From, Subject, Date, short body preview (~150 chars).
5. Categorize by priority:
   - 🔴 **HIGH**: urgent (deadline, urgent, important, ASAP, due, overdue, payment, invoice, bill, exam, final, warning)
   - 🟡 **MEDIUM**: school/work (project, assignment, class, meeting, lecture, tutorial, homework, group, course, quiz, test, lab, report, job)
   - 🔵 **LOW**: newsletters, promotions, social media, notifications, ads, everything else
6. Summarize in readable prose: a one-line count, a short assessment of whether anything
   needs action, then the grouped items, then a closing `Net:` line.

## ⚠️ Pitfall: IMAP `\Seen` side-effects

`fetch(id, '(RFC822)')` marks the message **read** as a side effect — it is not a
read-only operation. Always use `BODY.PEEK[]` to inspect without marking read.
If mail is consistently "missing" from results, the cause is almost always another
IMAP client having already marked it read — switch to a time-window query.

## Python code template

```python
import imaplib, json, os
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from email.header import decode_header
from email.utils import parsedate_to_datetime


def load_env(path):
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


# --- credentials: env vars, then the repo's local .env ---
repo_env = load_env(os.path.expanduser("~/hermes-telegram-email-bot/.env"))
EMAIL = (os.getenv("GMAIL_USER") or os.getenv("EMAIL_ADDRESS")
         or repo_env.get("GMAIL_USER") or repo_env.get("EMAIL_ADDRESS"))
PASS = (os.getenv("GMAIL_APP_PASSWORD") or os.getenv("EMAIL_PASSWORD")
        or repo_env.get("GMAIL_APP_PASSWORD") or repo_env.get("EMAIL_PASSWORD"))
if not EMAIL or not PASS:
    raise SystemExit("Missing GMAIL_USER / GMAIL_APP_PASSWORD")

HOURS = 24  # time window

M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
M.login(EMAIL, PASS)
M.select("INBOX")

cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS)
status, data = M.search(None, "SINCE", (cutoff - timedelta(days=1)).strftime("%d-%b-%Y"))
ids = data[0].split() if data and data[0] else []

emails = []
for e_id in reversed(ids[-15:]):
    _, md = M.fetch(e_id, "(BODY.PEEK[])")   # PEEK — do not set \Seen
    if not md or not md[0]:
        continue
    raw = md[0][1]
    if isinstance(raw, tuple):
        raw = raw[0]
    msg = message_from_bytes(raw)

    # filter by actual arrival time (IMAP SINCE is date-granular)
    try:
        sent = parsedate_to_datetime(msg["Date"])
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
        if sent.astimezone(timezone.utc) < cutoff:
            continue
    except Exception:
        continue

    subject = ""
    for part, charset in decode_header(msg["Subject"] or ""):
        subject += (part.decode(charset or "utf-8", errors="replace")
                    if isinstance(part, bytes) else part)

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode("utf-8", errors="replace")[:300]
                break
    else:
        body = (msg.get_payload(decode=True) or b"").decode("utf-8", errors="replace")[:300]

    emails.append({
        "from": msg["From"] or "",
        "subject": subject.strip(),
        "date": msg["Date"] or "",
        "preview": body[:200].replace("\n", " ").replace("\r", " "),
    })

emails.reverse()  # oldest first
M.logout()
print(json.dumps(emails, indent=2, ensure_ascii=False))
```

## Output format
```
📬 **Inbox Check** — N emails in the last 24h

<1-3 sentence assessment of whether anything needs action>

🔴 **HIGH (n)**
1. **Sender** — Subject
   <short note if useful>
...
Net: <what needs attention>
```

If the window is empty: "📬 No new emails in the last 24 hours."
