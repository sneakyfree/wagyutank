#!/usr/bin/env bash
# hatch-tank.sh — one idempotent command to hatch or converge a breed tank.
#
#   ./deploy/hatch-tank.sh <tank_key> [--dry-run] [--only p1,p2] [--skip p3]
#                                     [--port N] [--with-frontend]
#
# Sources deploy/.hatch-secrets.env (gitignored) for the API tokens, then hands
# off to hatch_tank.py. See docs/TANK_HATCHERY.md for the full runbook.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SECRETS="$HERE/.hatch-secrets.env"
if [ -f "$SECRETS" ]; then
  set -a; . "$SECRETS"; set +a
else
  echo "! $SECRETS not found — copy .hatch-secrets.env.example and fill it in." >&2
  echo "  (or export CF_GOD_TOKEN / CF_DNS_TOKEN / CF_PAGES_TOKEN / RESEND_API_KEY" >&2
  echo "   / STALWART_PASSWORD / CF_ACCOUNT_ID yourself before running.)" >&2
fi

exec python3 "$HERE/hatch_tank.py" "$@"
