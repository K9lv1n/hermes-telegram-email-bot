# 🤖 Hermes Telegram Email Bot

A personal AI email assistant that **reads your Gmail inbox, ranks messages by priority, and delivers clean summaries to your Telegram** — powered by the [Hermes Agent](https://github.com/NousResearch/hermes-agent) harness and the **DeepSeek API**.

Built as a learning project to explore agent harnesses, messaging gateways, LLM tool-calling, and email automation end-to-end.

---

## ✨ What It Does

| Capability | How |
|---|---|
| 📬 **On-demand inbox checks** | Message your Telegram bot *"check my emails"* → it fetches your latest unread mail, categorizes by priority, and replies with a summary |
| 🕘 **Scheduled summaries** | A cron job delivers a priority-ranked digest to your Telegram twice a day (customizable) |
| 🔴🟡🔵 **Priority ranking** | Emails auto-tagged: **HIGH** (deadlines, urgent, invoices), **MEDIUM** (school/work), **LOW** (promos, newsletters) |
| ✅ **Auto-mark read** | Emails are marked as SEEN after summarization so nothing repeats |
| 🔐 **Only you** | The bot is locked to your Telegram user ID — friends can't use it unless you add them |

---

## 🏗️ Architecture

```
┌─────────────┐    Telegram Bot API (long polling)     ┌──────────────────────┐
│  📱 Your    │ ◄────────────────────────────────────► │   Hermes Agent       │
│  Phone      │                                        │   (gateway process)  │
│  (Telegram) │   "check my emails"                    │                      │
└─────────────┘                                        │  ┌────────────────┐  │
                                                       │  │ gmail-check    │  │
                                                       │  │ skill (imaplib)│  │
┌─────────────┐                                        │  └───────┬────────┘  │
│  💻 CLI /   │                                        │          │           │
│  VS Code    │  hermes gateway / hermes acp          │          ▼           │
│  (optional) │ ◄────────────────────────────────────► │  ┌────────────────┐  │
└─────────────┘                                        │  │ DeepSeek API   │  │
                                                       │  │ (the LLM brain)│  │
                                                       │  └────────────────┘  │
                                                       └──────────┬───────────┘
                                                                  │ IMAP (SSL :993)
                                                                  ▼
                                                       ┌──────────────────────┐
                                                       │  📧 Gmail Inbox      │
                                                       └──────────────────────┘
```

**Data flow for one inbox check:**

1. You message the bot → Telegram webhook/polling delivers it to the **Hermes gateway**
2. Hermes loads the **`gmail-check` skill** (triggered by phrases like *"check my emails"*)
3. The skill runs a Python `imaplib` snippet → connects to Gmail over SSL → fetches the last 10 UNSEEN emails
4. Each email's **From / Subject / Date / preview** is extracted and **priority-categorized** with keyword rules
5. The **DeepSeek API** (the active model provider) formats the result into a clean, emoji-labeled Telegram reply
6. Hermes marks the emails SEEN and sends the summary back to your chat

> **Key insight:** the LLM doesn't *store* your emails — the skill reads them at query time, summarizes, and the raw content lives only in your Gmail. The bot is stateless between checks.

---

## 🧩 Components

### 1. Hermes Agent (the harness)
Open-source agent framework by Nous Research. Provides:
- **Gateway** — the process that connects to Telegram and runs 24/7
- **Skill system** — reusable procedures loaded on demand (our `gmail-check` skill)
- **Cron scheduler** — for the twice-daily email digests
- **Tool-calling loop** — decides when to read email, run Python, or reply

### 2. Telegram Bot
Created via **@BotFather**. The gateway polls Telegram's Bot API (or uses webhooks for cloud deployments). Access is restricted via `TELEGRAM_ALLOWED_USERS`.

### 3. Gmail (IMAP)
Read-only-ish access using an **App Password** (never your real password). The skill uses Python's built-in `imaplib` — no third-party email libraries needed.

### 4. DeepSeek API
The LLM that powers reasoning, summarization, and reply formatting. Set as the model provider in Hermes (`model.provider: deepseek`).

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10+ and [Hermes Agent](https://hermes-agent.nousresearch.com/install.sh)
- A Telegram account
- A Gmail account with 2FA enabled
- A [DeepSeek API key](https://platform.deepseek.com)

### Step 1 — Install Hermes
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes setup
```

### Step 2 — Create the Telegram bot
1. Message **[@BotFather](https://t.me/BotFather)** → `/newbot`
2. Choose a name + username (must end in `bot`)
3. Copy the token it gives you

### Step 3 — Find your Telegram user ID
Message **[@userinfobot](https://t.me/userinfobot)** — it replies with your numeric ID.

### Step 4 — Create a Gmail App Password
1. Enable 2FA: `myaccount.google.com/security`
2. Generate an app password: `myaccount.google.com/apppasswords` → "Other" → name it `Hermes`
3. Copy the 16-character code

### Step 5 — Configure Hermes
Copy the example env and fill in your values:
```bash
cp .env.example .env
# edit .env — fill in TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USERS,
# EMAIL_*, DEEPSEEK_API_KEY
```

Or set the key ones directly:
```bash
echo 'TELEGRAM_BOT_TOKEN=123456789:ABC...'   >> ~/.hermes/.env
echo 'TELEGRAM_ALLOWED_USERS=123456789'      >> ~/.hermes/.env
echo 'EMAIL_ADDRESS=you@gmail.com'           >> ~/.hermes/.env
echo 'EMAIL_PASSWORD=abcd efgh ijkl mnop'    >> ~/.hermes/.env
echo 'EMAIL_IMAP_HOST=imap.gmail.com'        >> ~/.hermes/.env
echo 'DEEPSEEK_API_KEY=sk-...'               >> ~/.hermes/.env
```

### Step 6 — Install the skill
```bash
# Copy the skill into your Hermes skills directory
cp -r skills/gmail-check ~/.hermes/skills/productivity/
hermes skills list   # verify it shows up
```

### Step 7 — Start the gateway
```bash
hermes gateway run        # foreground (test first)
hermes gateway install    # background service (production)
hermes gateway status
```

### Step 8 — Use it!
- Message your bot: **"check my emails"** → instant inbox summary
- Or wait for the scheduled 9am/6pm digest

---

## ⏰ Scheduled Summaries (Cron)

Hermes' cron scheduler runs the same skill on a schedule and delivers results to your Telegram:

```bash
hermes cron create "0 9,18 * * *" \
  --name "Email Priority Summary" \
  --prompt "Load the gmail-check skill and summarize my inbox by priority." \
  --skills gmail-check \
  --deliver telegram:<your_user_id>
```

Or from the Hermes chat UI:
```
/cron create "0 9,18 * * *"  →  then set the prompt + skill
```

---

## 🔐 Security Notes

- **Never commit `.env`** — it's git-ignored; real credentials live only on your machine
- Use **Gmail App Passwords**, never your real Gmail password
- The bot is **locked to your user ID** by default; add friends by appending their IDs to `TELEGRAM_ALLOWED_USERS`
- The DeepSeek key is stored in Hermes' credential store — treat it like a password
- If a token leaks: `/revoke` in BotFather, revoke the Gmail app password, and rotate the DeepSeek key

---

## 📁 Project Layout

```
hermes-telegram-email-bot/
├── README.md                 ← you are here
├── ARCHITECTURE.md           ← deep-dive into how it works
├── .env.example              ← template for secrets (git-ignored .env)
├── .gitignore
├── skills/
│   └── gmail-check/
│       └── SKILL.md          ← the Hermes skill: trigger phrases, logic, output format
└── scripts/
    └── check_emails.py       ← standalone Python version (no Hermes required)
```

---

## 🧠 What I Learned

Building this taught me:
- **Agent harnesses vs raw API calls** — Hermes adds memory, skills, tools, and multi-platform delivery on top of a plain LLM API
- **Telegram Bot API** — BotFather tokens, long polling, `getMe`, command scopes, user-ID allowlisting
- **IMAP from Python** — SSL connection, UNSEEN search, MIME parsing, header decoding, flagging
- **Gmail security model** — why app passwords exist and how 2FA gates IMAP access
- **Cron + delivery** — scheduling agent tasks and routing results to a chat platform
- **Secret hygiene** — `.env` + `.gitignore`, never shipping credentials in a public repo

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full deep-dive.

---

## 🛠️ Troubleshooting

| Symptom | Fix |
|---|---|
| Bot not responding | Check `hermes gateway status`; verify `TELEGRAM_BOT_TOKEN` in `.env` |
| `AUTHENTICATE failed` on Gmail | You're using your real password — generate an App Password instead |
| "Unauthorized" replies | Your user ID isn't in `TELEGRAM_ALLOWED_USERS` |
| Bot tries to use himalaya CLI | The `gmail-check` skill explicitly overrides this — ensure it's installed & reloaded (`/reload_skills`) |
| Emails repeat in summaries | Emails are marked SEEN after reading; check the skill's `M.store` step |

---

## 📄 License

MIT — free to use, learn from, and remix. Built with ❤️ and [Hermes Agent](https://github.com/NousResearch/hermes-agent).
