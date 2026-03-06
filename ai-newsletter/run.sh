#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and fill OPENCLAW_TOKEN." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

# Re-apply any caller-provided overrides (so .env can't blank them out)
OPENCLAW_CHANNEL=${OPENCLAW_CHANNEL_FROM_CALLER:-${OPENCLAW_CHANNEL:-}}
OPENCLAW_TARGET=${OPENCLAW_TARGET_FROM_CALLER:-${OPENCLAW_TARGET:-}}
export OPENCLAW_CHANNEL OPENCLAW_TARGET

# Run once for cron/reminder execution.
export RUN_ONCE_AND_EXIT=1

# Allow cron/reminder to override routing without editing .env.
# (.env may set OPENCLAW_TARGET empty, which breaks standalone sends.)
: "${OPENCLAW_CHANNEL:=}"
: "${OPENCLAW_TARGET:=}"
export OPENCLAW_CHANNEL OPENCLAW_TARGET

exec ./.venv/bin/python bot.py
