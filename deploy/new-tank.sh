#!/usr/bin/env bash
# new-tank.sh — scaffold a new tank (breed clone) on the VPS.
#
#   ./deploy/new-tank.sh <key> <domain> <port>
#   e.g. ./deploy/new-tank.sh highland highlandtank.com 8121
#
# Idempotent-ish: creates the tank dir skeleton, its own SQLite DB + JWT secret +
# port in tank.env, migrates/creates the schema, and enables the systemd instance.
# It does NOT invent content — you fill tanks/<key>/tank.json + seed data first
# (see TEMPLATE_SPEC.md §5). Ports: wagyu=8120, then 8121, 8122, ... (stagger crons
# via tank.json crawl.cron_offset_min separately).
set -euo pipefail

KEY="${1:?usage: new-tank.sh <key> <domain> <port>}"
DOMAIN="${2:?need domain}"
PORT="${3:?need port}"
ROOT="/root/wagyutank"
TANK_DIR="$ROOT/tanks/$KEY"

echo "== scaffolding tank '$KEY' ($DOMAIN, port $PORT) =="

# 1. tank dir skeleton (tank.json must already exist or be filled after)
mkdir -p "$TANK_DIR/seed" "$TANK_DIR/public"
if [ ! -f "$TANK_DIR/tank.json" ]; then
  echo "  ! $TANK_DIR/tank.json missing — create it before serving (copy tanks/wagyu/tank.json and edit)."
fi

# 2. per-tank env: own DB, own JWT secret, own port + TANK selector.
#    Real env vars override backend/.env, so each tank is isolated.
if [ ! -f "$TANK_DIR/tank.env" ]; then
  JWT="$(head -c 48 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 48)"
  cat > "$TANK_DIR/tank.env" <<ENV
TANK=$KEY
PORT=$PORT
DATABASE_URL=sqlite:///./data/$KEY.db
JWT_SECRET=$JWT
FRONTEND_ORIGIN=https://www.$DOMAIN
ENV
  echo "  + tank.env (own DB, fresh JWT secret, port $PORT)"
else
  echo "  = tank.env exists, leaving it"
fi

# 3. create the DB schema for this tank (migrate builds all tables)
mkdir -p "$ROOT/backend/data"
( cd "$ROOT/backend" && set -a && . "$TANK_DIR/tank.env" && set +a \
    && .venv/bin/python -m app.jobs.migrate )
echo "  + schema created at backend/data/$KEY.db"

# 4. enable the systemd instance (template unit must be installed once)
if [ -f /etc/systemd/system/tank@.service ]; then
  systemctl enable --now "tank@$KEY"
  sleep 2
  systemctl is-active "tank@$KEY" && echo "  + tank@$KEY active on :$PORT"
else
  echo "  ! /etc/systemd/system/tank@.service not installed — run:"
  echo "      cp $ROOT/deploy/tank@.service /etc/systemd/system/ && systemctl daemon-reload"
fi

cat <<NEXT

Next (manual, one-time per tank):
  - nginx: add server block  api.$DOMAIN -> 127.0.0.1:$PORT  (copy the wagyu block)
  - Cloudflare: DNS for $DOMAIN + api.$DOMAIN; create Pages project '$KEY-tank'
  - frontend: build with  TANK_API=https://api.$DOMAIN  (bakes this tank's config)
  - seed content: fill tanks/$KEY/{tank.json,seed/} then run seeders on this DB
  - crawl: add staggered cron using tank.json crawl.cron_offset_min
NEXT
echo "== done: tank '$KEY' scaffolded =="
