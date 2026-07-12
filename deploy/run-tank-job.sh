#!/usr/bin/env bash
# Run a backend job for a specific tank (loads its tank.env for TANK/DB/secret).
#   run-tank-job.sh <tank_key> <module>   e.g. run-tank-job.sh murraygrey app.jobs.news
set -euo pipefail
KEY="${1:?tank key}"; MOD="${2:?module}"
cd /root/wagyutank/backend
set -a; . "/root/wagyutank/tanks/$KEY/tank.env"; set +a
exec .venv/bin/python -m "$MOD"
