#!/bin/bash
# WagyuTank Roundup — full JS-render crawl + ingest, run FROM Windy 0 (residential
# IP; datacenter IPs get blocked at discovery). Renders the SPA/Shopify seller
# catalogs static fetch can't see, ships the rendered text to the VPS, and runs
# the LLM extractor there (facts + our neutral summary + link-back only).
#
# Tuning learned the hard way: networkidle hangs forever on tracker-heavy sites
# (use domcontentloaded + bounded settle, in crawl_listings.cjs); and slow
# site-builder hosts time out under high concurrency, so keep it gentle with a
# retry. One pass at conc 3 / 30s timeout covers ~75% of curated seller pages.
#
#   bash scripts/roundup_crawl.sh
set -euo pipefail
BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
SEEDS="$BACKEND/app/seed/data/roundup_seeds.json"
OUT="/tmp/roundup_rendered_$(date +%s 2>/dev/null || echo run).json"
VPS="${VPS_HOST:-vps}"

echo "[$(date)] crawling $(python3 -c "import json;print(len(json.load(open('$SEEDS'))))") seed sites…"
node "$BACKEND/scripts/crawl_listings.cjs" \
  --seeds "$SEEDS" --out "$OUT" \
  --per-site 5 --concurrency 3 --goto-timeout 30000 --max-pages 900

echo "[$(date)] shipping rendered pages to $VPS and ingesting…"
scp -q "$OUT" "$VPS:/root/wagyutank/backend/rendered_cron.json"
ssh "$VPS" 'cd /root/wagyutank/backend && .venv/bin/python -m app.jobs.ingest_rendered rendered_cron.json'
echo "[$(date)] done."
