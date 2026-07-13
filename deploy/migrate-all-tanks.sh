#!/usr/bin/env bash
# Run the additive DB migration for EVERY tank — use after any deploy that adds
# model columns (each tank has its own SQLite DB, so a new column drifts every
# tank until migrated; migrate.py is additive + idempotent). Safe to re-run.
#   ./deploy/migrate-all-tanks.sh
set -euo pipefail
ROOT="${HATCH_VPS_REPO:-/root/wagyutank}"
cd "$ROOT/backend"
for envf in "$ROOT"/tanks/*/tank.env; do
  key="$(basename "$(dirname "$envf")")"
  echo "== migrate $key =="
  ( set -a; . "$envf"; set +a; .venv/bin/python -m app.jobs.migrate 2>&1 | tail -1 )
done
echo "== all tanks migrated =="
