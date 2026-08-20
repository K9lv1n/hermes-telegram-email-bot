#!/usr/bin/env bash
# ============================================================================
# Hermes Telegram Email Bot — Oracle Cloud Free Tier Setup Script
# Run this ONCE on your fresh Ubuntu Oracle VM (as the default ubuntu user)
#
#   curl -fsSL https://raw.githubusercontent.com/K9lv1n/hermes-telegram-email-bot/main/setup_ubuntu.sh | bash
#
# What it does:
#   1. Updates the system
#   2. Installs Python 3 + uv (Hermes installer dependency)
#   3. Installs Hermes Agent
#   4. Writes .env with your credentials (edit this file first!)
#   5. Installs the gmail-check skill
#   6. Registers the gateway as a systemd service (survives reboots)
# ============================================================================

set -euo pipefail

echo "=============================================="
echo "  Hermes Telegram Email Bot — Oracle Setup"
echo "=============================================="

# ---------------------------------------------------------------
# 0. CREDENTIALS — EDIT THESE BEFORE RUNNING
#    (or set them in ~/.hermes/.env afterwards)
# ---------------------------------------------------------------
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-YOUR_BOT_TOKEN}"
TELEGRAM_ALLOWED_USERS="${TELEGRAM_ALLOWED_USERS:-YOUR_USER_ID}"
EMAIL_ADDRESS="${EMAIL_ADDRESS:-your.email@gmail.com}"
EMAIL_PASSWORD="${EMAIL_PASSWORD:-your_gmail_app_password}"
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-sk-your_key}"

# ---------------------------------------------------------------
# 1. System update + deps
# ---------------------------------------------------------------
echo "▶ Updating system..."
sudo apt-get update -y && sudo apt-get upgrade -y
sudo apt-get install -y curl git python3 python3-venv python3-pip

# ---------------------------------------------------------------
# 2. Install Hermes Agent (via official installer — sets up uv + venv)
# ---------------------------------------------------------------
echo "▶ Installing Hermes Agent..."
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash

# Add hermes to PATH for this session
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/.hermes/hermes-agent/venv/Scripts:$PATH"

# ---------------------------------------------------------------
# 3. Configure credentials (~/.hermes/.env)
# ---------------------------------------------------------------
echo "▶ Writing credentials to ~/.hermes/.env..."
mkdir -p "$HOME/.hermes"
cat >> "$HOME/.hermes/.env" <<EOF

# --- Telegram ---
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USERS=$TELEGRAM_ALLOWED_USERS

# --- Gmail ---
EMAIL_ADDRESS=$EMAIL_ADDRESS
EMAIL_PASSWORD=$EMAIL_PASSWORD
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993
EMAIL_ALLOWED_USERS=$EMAIL_ADDRESS
EMAIL_HOME_ADDRESS=$EMAIL_ADDRESS

# --- DeepSeek LLM ---
DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL=https://api.deepseek.com
EOF

# ---------------------------------------------------------------
# 4. Install the gmail-check skill
# ---------------------------------------------------------------
echo "▶ Installing gmail-check skill..."
mkdir -p "$HOME/.hermes/skills/productivity"
curl -fsSL https://raw.githubusercontent.com/K9lv1n/hermes-telegram-email-bot/main/skills/gmail-check/SKILL.md \
  -o "$HOME/.hermes/skills/productivity/gmail-check.md"

# ---------------------------------------------------------------
# 5. Create the cron job for scheduled email summaries
# ---------------------------------------------------------------
echo "▶ Scheduling daily email summaries (9am & 6pm)..."
hermes cron create "0 9,18 * * *" \
  --name "Email Priority Summary" \
  --prompt "Load the gmail-check skill and summarize my inbox by priority." \
  --skills gmail-check \
  --deliver "telegram:$TELEGRAM_ALLOWED_USERS" || echo "  (cron create skipped — run manually: hermes cron create ...)"

# ---------------------------------------------------------------
# 6. Install gateway as a systemd service (survives reboot)
# ---------------------------------------------------------------
echo "▶ Installing gateway as systemd service..."
hermes gateway install

echo ""
echo "=============================================="
echo "  ✅ SETUP COMPLETE!"
echo "=============================================="
echo ""
echo "  Check status:    hermes gateway status"
echo "  View logs:       tail -f ~/.hermes/logs/gateway.log"
echo "  Your bot should be online within seconds."
echo "  Message it: \"check my emails\""
echo ""
echo "  NOTE: If you didn't set credentials above, edit:"
echo "        nano ~/.hermes/.env   then:  hermes gateway restart"
echo "=============================================="
