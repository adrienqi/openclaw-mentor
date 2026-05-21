#!/usr/bin/env bash
# Rotate local secrets after exposure. Telegram + Anthropic must be rotated manually.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

ENV_FILE="${ROOT}/.env"
SECRETS_FILE="${ROOT}/homeassistant/config/secrets.yaml"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing .env — copy from .env.template first." >&2
  exit 1
fi

NEW_HA="$(openssl rand -hex 24)"
NEW_PIN="$(openssl rand -hex 4)"

update_env() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >>"$ENV_FILE"
  fi
}

update_env HA_WEBHOOK_SECRET "$NEW_HA"
update_env DASHBOARD_PIN "$NEW_PIN"

if [[ -f "$SECRETS_FILE" ]]; then
  if grep -q '^mentor_webhook_secret:' "$SECRETS_FILE"; then
    sed -i "s|^mentor_webhook_secret:.*|mentor_webhook_secret: \"Bearer ${NEW_HA}\"|" "$SECRETS_FILE"
  else
    printf '\nmentor_webhook_secret: "Bearer %s"\n' "$NEW_HA" >>"$SECRETS_FILE"
  fi
fi

if [[ -n "${NEW_TELEGRAM_BOT_TOKEN:-}" ]]; then
  update_env TELEGRAM_BOT_TOKEN "$NEW_TELEGRAM_BOT_TOKEN"
  echo "Updated TELEGRAM_BOT_TOKEN from NEW_TELEGRAM_BOT_TOKEN."
fi

if [[ -n "${NEW_ANTHROPIC_API_KEY:-}" ]]; then
  update_env ANTHROPIC_API_KEY "$NEW_ANTHROPIC_API_KEY"
  echo "Updated ANTHROPIC_API_KEY from NEW_ANTHROPIC_API_KEY."
fi

echo "Rotated HA_WEBHOOK_SECRET and DASHBOARD_PIN in .env (+ secrets.yaml)."
echo ""
echo "REQUIRED manual steps (old values may be in logs/history):"
echo "  1. Telegram: @BotFather → your bot → API Token → Revoke current token"
echo "     Copy the new token, then run:"
echo "       NEW_TELEGRAM_BOT_TOKEN='paste-here' $0"
echo "  2. Anthropic: https://console.anthropic.com → revoke old key, create new"
echo "       NEW_ANTHROPIC_API_KEY='paste-here' $0"
echo "  3. Restart: docker compose up -d --build mentor-core && docker compose restart home-assistant"
echo "  4. Update dashboard bookmark PIN to the new DASHBOARD_PIN (check .env locally)."
