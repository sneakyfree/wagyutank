#!/usr/bin/env bash
# Harvest source-language transcripts for a tank's videos. RUNS ON VERON.
#   tank-transcripts.sh <tank_key> [limit]
#
# Same split as tank-crawl.sh: Veron has the residential IP and the yt-dlp
# toolchain, the VPS has the database. Ask the VPS what is missing, fetch it
# here, ship it back.
#
# NEEDS A JS RUNTIME on PATH. Without one every caption download fails with
# HTTP 429 — that was the original blocker, and deno fixes it outright.
set -e
KEY="${1:?usage: tank-transcripts.sh <tank_key> [limit]}"
LIMIT="${2:-40}"

# Share the crawl lock: both jobs hammer the same residential IP, and running a
# transcript sweep during a Roundup crawl is how you earn a rate-limit ban.
LOCK="/tmp/tank-crawl.lock"
if [ -z "${TANK_CRAWL_LOCKED:-}" ]; then
  export TANK_CRAWL_LOCKED=1
  exec flock -w 21600 "$LOCK" "$0" "$@"
fi

REPO="$HOME/wagyutank"
VPS="root@72.60.118.54"
export PATH="$HOME/.deno/bin:$HOME/.local/bin:$PATH"
echo "===== $KEY transcripts $(date) ====="
cd "$REPO" && git pull -q 2>/dev/null || true

command -v deno >/dev/null || echo "WARNING: no JS runtime on PATH — caption fetches will 429"

Q=/tmp/${KEY}-transcript-queue.json
OUT=/tmp/${KEY}-transcripts.json
ssh "$VPS" "cd /root/wagyutank/backend && set -a && . ../tanks/$KEY/tank.env && set +a && \
  .venv/bin/python -m app.jobs.export_transcript_queue /tmp/${KEY}_tq.json --limit $LIMIT"
scp -q "$VPS:/tmp/${KEY}_tq.json" "$Q"
[ -s "$Q" ] || { echo "no queue file — skipping"; exit 0; }

python3 "$REPO/backend/scripts/fetch_transcripts.py" --queue "$Q" --out "$OUT" --limit "$LIMIT"
[ -s "$OUT" ] || { echo "nothing fetched"; exit 0; }

scp -q "$OUT" "$VPS:/root/wagyutank/backend/${KEY}_transcripts.json"
ssh "$VPS" "cd /root/wagyutank/backend && set -a && . ../tanks/$KEY/tank.env && set +a && \
  .venv/bin/python -m app.jobs.ingest_transcripts ${KEY}_transcripts.json"
rm -f "$Q" "$OUT"
echo "===== $KEY transcripts done $(date) ====="
