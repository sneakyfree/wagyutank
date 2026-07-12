#!/usr/bin/env bash
# Weekly video harvest for a tank — runs on VERON 1 (residential IP; YouTube
# throttles datacenter IPs). Uses yt-dlp to discover the breed's videos, ships to
# the VPS, ingests/classifies/enriches under the tank's env, phones home. In
# version control; Veron runs it from ~/wagyutank/deploy/.
#   tank-harvest.sh <tank_key>
set -e
KEY="${1:?usage: tank-harvest.sh <tank_key>}"
REPO="$HOME/wagyutank"
VPS="root@72.60.118.54"
TANKJSON="$REPO/tanks/$KEY/tank.json"
OUT="/tmp/${KEY}-videos-$(date +%Y%m%d).json"
export PATH="$HOME/.local/bin:$PATH"
echo "===== $KEY video harvest $(date) ====="
cd "$REPO/backend" && git -C "$REPO" pull -q 2>/dev/null || true
[ -f "$TANKJSON" ] || { echo "no tank.json for $KEY — skipping"; exit 0; }
DOMAIN=$(python3 -c "import json;print(json.load(open('$TANKJSON'))['brand']['domain'])")
# Target THIS tank's API so the query pool is built from its own animals/sales.
HARVEST_API="https://api.$DOMAIN" python3 scripts/harvest_videos.py --per-query 8 --out "$OUT"
scp -q "$OUT" "$VPS:/root/wagyutank/backend/${KEY}-videos.json"
ssh "$VPS" "cd /root/wagyutank/backend && set -a && . ../tanks/$KEY/tank.env && set +a && \
  .venv/bin/python -m app.jobs.ingest_videos ${KEY}-videos.json && \
  .venv/bin/python -m app.jobs.classify_videos && \
  .venv/bin/python -m app.jobs.enrich_videos --editorial-top 40 && \
  .venv/bin/python -m app.jobs.record_run video_harvest"
rm -f "$OUT"
echo "===== $KEY harvest done $(date) ====="
