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

# Run once for cron/reminder execution.
export RUN_ONCE_AND_EXIT=1
exec ./.venv/bin/python bot.py
