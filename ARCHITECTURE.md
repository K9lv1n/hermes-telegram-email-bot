# 🏗️ Architecture Deep-Dive

This document explains how the Hermes Telegram Email Bot works under the hood — every component, every hop a message takes, and why each piece exists.

---

## System Overview

```
                          ┌────────────────────────────────────────────────────────────┐
                          │                      YOUR MACHINE                         │
                          │                                                            │
   Telegram Cloud         │   ┌────────────────────────────────────────────────────┐   │
 ┌──────────────────┐     │   │             HERMES AGENT (gateway)                 │   │
 │  Bot API servers │     │   │                                                    │   │
 │  (api.telegram.  │◄────┼───┼── long polling loop ──► Telegram platform adapter  │   │
 │   org)           │     │   │                          │                          │   │
 └──────────────────┘     │   │                          ▼                          │   │
                          │   │                 ┌────────────────────┐              │   │
   Gmail Cloud            │   │                 │  Agent core loop   │              │   │
 ┌──────────────────┐     │   │                 │  (LLM + tools)     │              │   │
 │  imap.gmail.com  │◄────┼───┼── IMAP over SSL──┤                    │              │   │
 │  (993)           │     │   │                 │  • system prompt   │              │   │
 └──────────────────┘     │   │                 │  • tool dispatch   │              │   │
                          │   │                 │  • skill loading   │              │   │
   DeepSeek Cloud         │   │                 └─────────┬──────────┘              │   │
 ┌──────────────────┐     │   │                           │                          │   │
 │  api.deepseek.com│◄────┼───┼── HTTPS /chat/completions─┘                          │   │
 │  (LLM inference) │     │   │                                                     │   │
 └──────────────────┘     │   └────────────────────────────────────────────────────┘   │
                          └────────────────────────────────────────────────────────────┘
```

---

## Component Breakdown

### 1. The Telegram Bot (identity layer)

- Created with **@BotFather**, which issues a unique **bot token** — the bot's credential to the Telegram Bot API.
- The gateway **polls** `api.telegram.org` for updates (long polling). No public URL or webhook needed for local setups; webhook mode exists for cloud deploys.
- **Allowlisting**: `TELEGRAM_ALLOWED_USERS` restricts which Telegram user IDs the bot will serve. Everyone else gets an "unauthorized" reply. This is the primary access-control layer.

### 2. The Hermes Gateway (transport + lifecycle)

- A long-running Python process (`hermes gateway run`) that:
  - owns the Telegram connection
  - runs the agent loop when messages arrive
  - executes scheduled cron jobs
  - delivers messages back to Telegram
- Installed as a background service (`hermes gateway install`) so it survives terminal closures — on Windows it registers a Startup item; on Linux/macOS a systemd/launchd unit.
- **Each incoming message creates a session** — Hermes tracks conversation history per chat, so the bot has memory across messages.

### 3. The Agent Core (brain + hands)

The agent loop is the classic **ReAct-style tool-calling loop**:

```
User message → build prompt (system + history) → call LLM
      ↓
LLM responds with text AND/OR tool calls
      ↓
if tool calls → execute tool → feed result back to LLM → repeat
      ↓
else → deliver final text reply to Telegram
```

The LLM (DeepSeek) decides *which* tools to invoke based on the user's request. When you say *"check my emails"*, it sees the `gmail-check` skill in its context, loads it, and follows its steps.

### 4. The `gmail-check` Skill (procedural memory)

Skills are **markdown documents with frontmatter** that teach the agent how to do a task. The key parts:

| Section | Purpose |
|---|---|
| `description` | Tells the agent when to load this skill (trigger matching) |
| `## Steps` | The numbered procedure the agent follows |
| Python template | A ready-to-run `imaplib` snippet — no external CLI needed |
| Output format | The exact Telegram reply layout (emojis, sections) |

**Why a skill instead of hardcoded code?** The skill is *content*, not compiled logic — Hermes loads it on demand, and the LLM adapts it to the situation (e.g., "only high priority", "summarize the last 5"). It's also reusable across profiles and platforms.

### 5. Gmail via IMAP (data source)

- Python's built-in **`imaplib`** connects to `imap.gmail.com:993` (SSL).
- `SEARCH UNSEEN` returns message IDs; `FETCH (RFC822)` pulls full raw messages.
- The `email` stdlib module parses MIME: headers (`From`, `Subject`, `Date`) + body extraction.
- **App passwords**: Gmail requires an app-specific password (16 chars) when 2FA is on. This replaces your real password in the IMAP `LOGIN`.
- After summarization, `STORE +FLAGS \Seen` marks messages read so the next check only sees *new* mail.

### 6. DeepSeek API (the LLM brain)

- DeepSeek is the **model provider** configured in Hermes (`model.provider: deepseek`, `model.default: deepseek-chat`).
- The API key lives in `~/.hermes/.env` (or Hermes' credential store) — **never in the repo**.
- DeepSeek handles: understanding the user's intent, following the skill, categorizing priority, and writing the human-friendly summary.

---

## Message Lifecycle — One Full Inbox Check

```
1.  📱 "check my emails"                    (you, Telegram)
2.  ─► api.telegram.org long-poll           (gateway picks it up)
3.  ─► Telegram adapter → agent loop         (session keyed by chat_id)
4.  ─► LLM sees request → loads gmail-check skill
5.  ─► Skill instructs: run imaplib snippet
6.  ─► terminal tool executes python:
        imaplib.IMAP4_SSL('imap.gmail.com', 993)
        .login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        .search(None, 'UNSEEN')              → last 10 IDs
        .fetch(id, '(RFC822)')               → parse From/Subject/Date/body
        .store(id, '+FLAGS', '\\Seen')       → mark read
7.  ─► Tool result (JSON of emails) fed back to LLM
8.  ─► LLM categorizes 🔴🟡🔵 and formats the summary
9.  ─► Gateway sends formatted reply to Telegram
10. 📱 Summary appears in your chat
```

Total round trip: ~2–5 seconds for 10 emails.

---

## Scheduled Digests (Cron)

The same skill runs on a schedule without any user message:

```
cron scheduler (in gateway)
   │  every tick at 09:00 / 18:00
   ▼
spawns agent session with prompt:
   "Load the gmail-check skill and summarize my inbox by priority."
   ▼
same imaplib → LLM → summary pipeline
   ▼
delivers result to telegram:<user_id>  (your DM)
```

Cron jobs are **durable** — they're persisted in Hermes' scheduler and survive gateway restarts.

---

## Security Model

| Layer | Control |
|---|---|
| Telegram access | `TELEGRAM_ALLOWED_USERS` (numeric IDs) |
| Gmail access | App password + 2FA; IMAP-only (no send unless SMTP configured) |
| LLM access | DeepSeek API key in `.env` (git-ignored) |
| Repo | `.gitignore` blocks `.env`, keys, logs, DBs |
| Sessions | Per-chat isolation — other users' chats never share context |

**Threat model:** an attacker who gets the bot token can impersonate the bot (but can't read your Gmail — that needs the app password). An attacker with the app password can read your mail. An attacker with the DeepSeek key can spend your API credits. Keep all three separate and revocable.

---

## Design Decisions & Trade-offs

| Decision | Why | Trade-off |
|---|---|---|
| Skill over standalone script | Reusable, adaptive, works across platforms | Needs Hermes running |
| `imaplib` over Gmail API | Zero extra dependencies, no OAuth scopes | No fancy features (labels, push) |
| Long polling over webhook | Simple, works behind NAT, no public URL | Keeps connection open (minor) |
| Allowlist over open access | Safety first | Friends must be added manually |
| DeepSeek as provider | Cheap, capable, OpenAI-compatible | Tied to DeepSeek's API |

---

## Extending It

- **More platforms** — Hermes gateway supports Discord, Slack, WhatsApp, Signal… the same skill works everywhere.
- **Richer analysis** — swap the keyword priority rules for an LLM classification pass.
- **Email actions** — add SMTP to reply/forward; add Gmail labels via the API.
- **Multi-user** — add friends to `TELEGRAM_ALLOWED_USERS`; each gets their own session.
- **Observability** — Hermes exposes `/usage`, session logs, and `hermes insights` for token tracking.
