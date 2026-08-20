---
name: gmail-check
description: "Use Python's built-in imaplib to check Gmail, fetch recent unread emails, and summarize by priority. No external CLI tools needed. Triggered when user asks 'check my emails', 'inbox', 'what's in my inbox', 'email summary', 'any new emails', 'read my emails', 'show my inbox'."
version: 1.1.0
author: Hermes Agent
tags: [email, gmail, imap, inbox]
---

# Gmail Check

⚠️ IMPORTANT: Do NOT use the `himalaya` CLI or `himalaya` skill. This skill uses Python's built-in `imaplib` — no external tools needed.

## Trigger phrases
"check my emails", "inbox", "email summary", "what's in my inbox", "any new emails", "read my emails", "show my inbox", "gmail"

## Steps

1. Connect to Gmail via IMAP using Python's built-in `imaplib`:
   - Host: `imap.gmail.com:993` (SSL)
   - Login: from `.env` (`EMAIL_ADDRESS` / `EMAIL_PASSWORD` — the Gmail app password)

2. Fetch the last 10 UNSEEN emails from INBOX
3. For each email extract: From, Subject, Date, and a short body preview (~150 chars)

4. Categorize by priority:
   - 🔴 **HIGH**: urgent (deadline, urgent, important, ASAP, due, overdue, payment, invoice, bill, exam, final)
   - 🟡 **MEDIUM**: school/work (project, assignment, class, meeting, lecture, tutorial, homework, group, course, quiz, test, lab, report)
   - 🔵 **LOW**: newsletters, promotions, social media, notifications, ads, everything else

5. Mark those 10 emails as SEEN after reading
6. Format the output nicely with emojis

## Python code template (use this, NOT himalaya CLI)

```python
import imaplib, email, json, os
from email.header import decode_header

# Credentials come from environment / .env — never hardcode
EMAIL = os.getenv("EMAIL_ADDRESS")
PASS  = os.getenv("EMAIL_PASSWORD")

M = imaplib.IMAP4_SSL('imap.gmail.com', 993)
M.login(EMAIL, PASS)
M.select('INBOX')

status, data = M.search(None, 'UNSEEN')
ids = data[0].split()
recent = ids[-10:] if len(ids) >= 10 else ids

emails = []
for e_id in reversed(recent):
    status, msg_data = M.fetch(e_id, '(RFC822)')
    msg = email.message_from_bytes(msg_data[0][1])

    # decode subject (handles =?utf-8?B?...?= encoded headers)
    subject = ''
    for part, charset in decode_header(msg['Subject'] or ''):
        if isinstance(part, bytes):
            subject += part.decode(charset or 'utf-8', errors='replace')
        else:
            subject += part

    # extract body preview
    body = ''
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == 'text/plain':
                body = part.get_payload(decode=True).decode('utf-8', errors='replace')[:300]
                break
    else:
        body = msg.get_payload(decode=True).decode('utf-8', errors='replace')[:300]

    emails.append({
        'from': msg['From'] or '',
        'subject': subject.strip(),
        'date': msg['Date'] or '',
        'preview': body[:200].replace('\n', ' ').replace('\r', ' ')
    })

# mark as SEEN so next check only sees new mail
for e_id in recent:
    M.store(e_id, '+FLAGS', '\\Seen')

M.logout()
print(json.dumps(emails, indent=2, ensure_ascii=False))
```

## Output format
```
📬 Inbox Check
━━━━━━━━━━━━━━━
🔴 HIGH (0)
🟡 MEDIUM (0)
🔵 LOW (N)
1. [From] — Subject | 📅 Date
```

If nothing new: "📬 No new emails! Inbox is caught up."
