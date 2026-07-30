#!/usr/bin/env bash
# Run a backend job for a specific tank (loads its tank.env for TANK/DB/secret).
#   run-tank-job.sh <tank_key> <module> [job args…]
#     run-tank-job.sh murraygrey app.jobs.news
#     run-tank-job.sh wagyu app.jobs.translate_transcripts --source-lang ja --limit 60
# Anything after the module is forwarded to the job, so a job that takes flags can
# still be driven from cron. Existing two-argument callers are unaffected.
set -euo pipefail
KEY="${1:?tank key}"; MOD="${2:?module}"; shift 2
cd /root/wagyutank/backend
set -a; . "/root/wagyutank/tanks/$KEY/tank.env"; set +a
exec .venv/bin/python -m "$MOD" "$@"
