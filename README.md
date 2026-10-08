# 🤖 Hermes Telegram Email Bot

[![Email Digest](https://github.com/K9lv1n/hermes-telegram-email-bot/actions/workflows/email-digest.yml/badge.svg)](https://github.com/K9lv1n/hermes-telegram-email-bot/actions/workflows/email-digest.yml)

A personal email assistant that **reads my Gmail, ranks messages by priority, and delivers a readable summary to my Telegram** — twice a day, on time, without needing my laptop switched on.

Built as a learning project to understand agent harnesses, messaging gateways, LLM tool-calling, and email automation end to end.

---

## 📌 Current Setup At A Glance

Everything below is the **live configuration**. Start here if you're trying to remember how this works.

| Thing | Value |
|---|---|
| **Repo** | `K9lv1n/hermes-telegram-email-bot` (public) |
| **Telegram bot** | `@dih67bot` ("Deepseek hermes") |
| **Allowed Telegram user** | `5724965598` (me) |
| **Gmail account read** | `kalvinchin2@gmail.com` (app password, IMAP) |
| **LLM** | DeepSeek (`deepseek-chat`) |
| **Digest times** | **09:00 & 21:00 SGT** (Asia/Singapore) |
| **Punctual trigger** | **cron-job.org** → GitHub dispatch API |
| **Fallback trigger** | GitHub's own schedule (`30 1,13 * * *` UTC = 09:30 / 21:30 SGT) |
| **Digest window** | Mail from the **last 12 hours** |
| **Read state** | **Never modified** — the digest does not mark mail as read |
| **Duplicate protection** | `scripts/should_run.py` (12-hour slot gate) |
| **Local Hermes trigger** | ⏸️ **paused** (spare, see *Operational Status*) |
| **Interactive bot** | Runs on my PC via the Hermes gateway |

### Repo secrets (Settings → Secrets → Actions)
`EMAIL_ADDRESS` · `EMAIL_PASSWORD` · `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` · `DEEPSEEK_API_KEY`

---

## ✨ What It Does

| Capability | How |
|---|---|
| 🕘 **Scheduled digest** | cron-job.org triggers a GitHub Actions job at 09:00 / 21:00 SGT → it reads Gmail, hands the mail to DeepSeek, and posts a readable summary to Telegram |
| 📬 **On-demand check** | Message `@dih67bot` *"check my emails"* → the Hermes bot on my PC runs the same logic and replies in chat |
| 🔴🟡🔵 **Priority ranking** | Keyword rules tag each mail **HIGH** (deadlines, payments, exams), **MEDIUM** (school/work), **LOW** (promos, newsletters) |
| 🧠 **Readable output** | DeepSeek writes a short assessment, the grouped list with a note per item, and a closing `Net:` line — not just a bare list |
| 🔐 **Only me** | The bot is locked to my Telegram user ID |
| 💤 **Laptop-independent** | The scheduled digest runs entirely in the cloud — my machine can be off |

---

## 🏗️ How It Works

There are **two independent paths**. They share the same email-reading logic but never run at the same time.

```
                    ┌────────────────────────────────────────────────┐
   SCHEDULED PATH   │                                                │
                    │   ┌──────────────┐   09:00 / 21:00 SGT        │
                    │   │ cron-job.org │ ──POST dispatch──┐         │
                    │   └──────────────┘                  │         │
                    │                                     ▼         │
                    │              ┌──────────────────────────────┐ │
                    │              │      GitHub Actions          │ │
                    │              │  (email-digest.yml)          │ │
                    │              │  1. should_run.py — dedupe   │ │
                    │              │  2. check_emails.py — Gmail  │ │
                    │              │  3. send_to_telegram.py      │ │
                    │              └───────┬──────────────┬───────┘ │
                    └──────────────────────┼──────────────┼─────────┘
                                           │              │
                      IMAP :993            │              │  Bot API
                                           ▼              ▼
                                    ┌───────────┐   ┌──────────────┐
                                    │  Gmail    │   │  Telegram    │
                                    └───────────┘   │  @dih67bot   │
                                           ▲        └──────────────┘
                                           │              ▲
                      IMAP :993            │              │  Bot API
         ┌─────────────────────────────────┴──────────────┴─────────┐
         │                    MY PC (Hermes gateway)                 │
         │  "check my emails" → gmail-check skill → reply in chat    │
         └──────────────────────────────────────────────────────────┘
                      INTERACTIVE PATH
```

### The scheduled digest (the main event)

1. **cron-job.org** fires at exactly 09:00 / 21:00 SGT and POSTs to GitHub's dispatch API
2. GitHub starts the workflow **immediately** (dispatched runs skip the scheduling queue)
3. `should_run.py` asks: *has a digest already gone out in this 12-hour slot?* If yes → stop here
4. `check_emails.py` connects to Gmail over IMAP and pulls mail from the **last 12 hours**
5. `send_to_telegram.py` sends that mail to **DeepSeek**, which writes the readable summary
6. The summary is posted to my Telegram

### The interactive path

Message the bot *"check my emails"* and the Hermes gateway on my PC loads the `gmail-check` skill, runs the same IMAP read (last 24h), and replies in chat.

---

## 🧩 Design Problems I Hit (And How They Were Solved)

This project's real value was debugging. Three non-obvious problems, all diagnosed from evidence:

### 1. Two schedulers were sending duplicate digests

I had a local Hermes cron job **and** a GitHub Actions schedule both firing twice a day. They produced two differently-formatted messages at overlapping times.

**Fix:** pick one sender. GitHub Actions became the single source of truth; the local cron was paused.

### 2. The digest "found no emails" even though mail was arriving

**Root cause:** any IMAP client that fetches a message **body** implicitly sets Gmail's `\Seen` flag — `fetch(id, '(RFC822)')` is *not* a read-only operation. Hermes's own Email gateway adapter was doing exactly that on every poll (every ~15s), so new mail was marked read before the digest looked. The inbox was fully consumed: **0 unread out of 15,162**.

```
$ grep -n "Mark all existing messages as seen" plugins/platforms/email/adapter.py
588:  # Mark all existing messages as seen so we only process new ones
672:  status, msg_data = imap.uid("fetch", uid, "(RFC822)")   # ← sets \Seen
```

**Fixes:**
- Select mail by **arrival time** (`--since-hours 12`), which is independent of read state
- Read bodies with **`BODY.PEEK[]`** so the digest never mutates read state either
- **Disable the Email gateway adapter** (it was also silently marking my mail read in Gmail) by removing `EMAIL_ADDRESS` from the gateway environment — credentials moved to `GMAIL_USER` / `GMAIL_APP_PASSWORD`, which don't trigger the adapter

### 3. GitHub's cron ran the digest 6 hours late

GitHub's free `schedule:` is explicitly *best-effort*. Actual observed runs:

| Scheduled (UTC) | Actually ran | Delay |
|---|---|---|
| 01:00 (9am SGT) | 06:45 | **5h 45m late** |
| 10:00 (6pm SGT) | 16:25 | **6h 25m late** |
| 13:00 (9pm SGT) | 19:07 | **6h 07m late** |

**Fix:** trigger the workflow from outside GitHub. `cron-job.org` (free) POSTs to the dispatch API at exactly 09:00 / 21:00 SGT — dispatched runs start immediately. GitHub's own schedule was moved to 09:30 / 21:30 SGT as a **fallback** (same 12h slot, so the dedupe gate suppresses it whenever the punctual trigger already fired).

---

## 🧩 Components

| Component | Role |
|---|---|
| **cron-job.org** | External free scheduler — the punctual trigger |
| **GitHub Actions** | Runs the digest in the cloud; 2,000 free minutes/month on public repos (a run uses ~1 min) |
| **Hermes Agent** | Agent harness: gateway, skill system, tool-calling loop, local cron |
| **Telegram Bot** | Delivery channel (@BotFather token, allowlisted to my user ID) |
| **Gmail (IMAP)** | Data source — Python stdlib `imaplib`, app-password auth |
| **DeepSeek API** | Writes the human-readable summary |

---

## ⚙️ Operational Status

| Piece | State | Notes |
|---|---|---|
| cron-job.org trigger | ✅ **Active** | Primary punctual trigger |
| GitHub Actions workflow | ✅ **Active** | Sends the digest; fallback schedule armed |
| Dedupe gate | ✅ **Active** | Prevents double-sends |
| Interactive Telegram bot | ✅ **Running** | On my PC; needs the gateway up |
| Local Hermes trigger cron | ⏸️ **Paused** | Spare — enable only if cron-job.org dies (never run both punctually, or they race) |
| Email gateway adapter | ⛔ **Disabled** | Was marking mail read; `EMAIL_*` removed from gateway env |

### Health checks

```bash
# Is the local bot alive?
hermes gateway status

# What's scheduled locally?
hermes cron list --all

# Did recent digests run, and what did they decide?
#   → open https://github.com/K9lv1n/hermes-telegram-email-bot/actions
#   → click a run → look for "gate:" lines in the log

# Test the whole cloud path right now (ignores the dedupe gate)
#   → Actions tab → Email Digest → Run workflow → tick "force"
```

---

## 📁 Project Layout

```
hermes-telegram-email-bot/
├── README.md                     ← you are here (operational overview)
├── ARCHITECTURE.md               ← deeper design notes
├── .env.example                  ← template for secrets (.env is git-ignored)
├── .gitignore
├── LICENSE                       ← MIT
├── setup_ubuntu.sh               ← optional: deploy the bot to a Linux VM instead of a PC
├── .github/workflows/
│   └── email-digest.yml          ← the cloud digest job
├── scripts/
│   ├── check_emails.py           ← Gmail read + priority ranking (time-window, BODY.PEEK)
│   ├── send_to_telegram.py       ← DeepSeek summary + Telegram delivery
│   ├── should_run.py             ← 12h-slot dedupe gate
│   └── trigger_digest.py         ← dispatches the workflow (used by the paused local trigger)
└── skills/gmail-check/
    └── SKILL.md                  ← the Hermes skill behind the interactive bot
```

---

## 🚀 Reproducing This Setup

### Prerequisites
- [Hermes Agent](https://hermes-agent.nousresearch.com/install.sh), Python 3.10+
- A Telegram account, a Gmail account with 2FA, a [DeepSeek API key](https://platform.deepseek.com)

### 1. Telegram bot
Message **[@BotFather](https://t.me/BotFather)** → `/newbot` → copy the token.
Get your numeric ID from **[@userinfobot](https://t.me/userinfobot)**.

### 2. Gmail app password
Enable 2FA at `myaccount.google.com/security`, then create an app password at
`myaccount.google.com/apppasswords` (choose "Other" → name it `Hermes`).

### 3. Local helpers (`.env`)
```bash
cp .env.example .env     # fill in the values
```

### 4. Local bot (interactive path)
Add to the Hermes environment file — note the `GMAIL_*` names, **not** `EMAIL_*`
(setting `EMAIL_ADDRESS` makes Hermes auto-connect the Email gateway adapter, which
marks your mail as read):
```
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_ALLOWED_USERS=your_numeric_id
GMAIL_USER=you@gmail.com
GMAIL_APP_PASSWORD=abcd efgh ijkl mnop
DEEPSEEK_API_KEY=sk-...
```

Install the skill and start the gateway:
```bash
cp -r skills/gmail-check ~/.hermes/skills/productivity/
hermes gateway install
hermes gateway status
```

### 5. Cloud digest (scheduled path)
Push this repo, then add the five secrets listed at the top.

### 6. Punctual trigger (the important bit)
1. Create a **fine-grained GitHub token**: repo access → only this repo; permission → **Actions: Read and write**
2. On [cron-job.org](https://cron-job.org) (free): `POST` to
   `https://api.github.com/repos/<owner>/<repo>/actions/workflows/email-digest.yml/dispatches`
   at **09:00 & 21:00 Asia/Singapore**, body `{"ref":"main"}`, headers:
   ```
   Authorization: Bearer github_pat_...
   Accept: application/vnd.github+json
   Content-Type: application/json
   X-GitHub-Api-Version: 2022-11-28
   ```
   A `204 No Content` means success.
3. **Only run one punctual trigger.** If you also enable a local trigger, both will fire
   in the same minute and can race past the dedupe gate.

---

## 🔧 Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| Digest arrived but is empty / "no new emails" | Nothing arrived in the 12h window — normal. Check the run log for `N message(s) in window` |
| Digest arrived many hours late | The fallback schedule fired (GitHub's own cron is unreliable). Check cron-job.org's job history — the punctual trigger may be failing |
| Two digests in one slot | Two punctual triggers are enabled (e.g. local + cron-job.org). Disable one |
| Digest never arrives | Check the Actions tab: is the workflow disabled (60 days repo inactivity)? Is cron-job.org's job enabled? |
| Interactive bot silent | `hermes gateway status`; the gateway must be running |
| Interactive bot says credentials missing | Set `GMAIL_USER` / `GMAIL_APP_PASSWORD` in the Hermes env file |
| Mail is being marked read without me reading it | Something is fetching bodies with `RFC822` — check no `EMAIL_*` vars are set (they enable the Email adapter) |
| Gmail login fails with app password | 2FA must be enabled; the password must be a 16-char app password, not the account password |

### Useful server-side facts
- GitHub **auto-disables scheduled workflows after 60 days of repo inactivity** — the external trigger is immune, which is one more reason it's the primary
- IMAP `SINCE` is **date**-granular, so `check_emails.py` searches a wider window and filters by the message `Date` header locally
- `fetch(id, '(RFC822)')` sets `\Seen`; `fetch(id, '(BODY.PEEK[])')` does not

---

## 🔐 Security

- **Never commit `.env`** — it's git-ignored; real credentials live only on my machine and in GitHub Secrets
- The Gmail access uses an **app password** (revocable, 2FA-gated), not the account password
- The bot is **allowlisted to one Telegram user ID**
- The cron-job.org token is **fine-grained**: `Actions: write` on this single repo, nothing else
- If anything leaks: revoke the BotFather token (`/revoke`), the Gmail app password, the DeepSeek key, and the GitHub token

---

## 🧠 What I Learned

- **Agent harness vs raw API** — Hermes adds skills, tools, memory and multi-platform delivery on top of an LLM API
- **IMAP semantics bite** — fetching a body mutates state; `\Seen` is a side effect, not a read
- **"Unread" is a shared, fragile flag** — multiple clients fight over it; time windows are robust
- **Free cloud cron is best-effort** — GitHub's scheduler is not a clock; external triggers are
- **Idempotency needs designing** — a dedupe gate is what makes multiple triggers safe to run
- **Secret hygiene** — `.env` + `.gitignore`, narrow-scope tokens, and never shipping credentials

---

## 📄 License

MIT — free to use, learn from, and remix. Built with [Hermes Agent](https://github.com/NousResearch/hermes-agent).
