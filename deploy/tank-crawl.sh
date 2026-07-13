#!/usr/bin/env bash
# Weekly Roundup crawl for a tank — runs on VERON 1 (24-core, residential IP).
# Crawls the tank's seed sellers, ships to the VPS, ingests + refreshes the Atlas
# under that tank's env, reaps dead links, and phones home. In version control so
# it survives any single machine dying; Veron runs it from ~/wagyutank/deploy/.
#   tank-crawl.sh <tank_key>
set -e
KEY="${1:?usage: tank-crawl.sh <tank_key>}"
REPO="$HOME/wagyutank"
VPS="root@72.60.118.54"
SEEDS="$REPO/tanks/$KEY/seed/roundup_seeds.json"
OUT="/tmp/${KEY}-roundup-$(date +%s).json"
export PATH="$HOME/.local/bin:$PATH"
echo "===== $KEY crawl $(date) ====="
cd "$REPO" && git pull -q 2>/dev/null || true
[ -f "$SEEDS" ] || { echo "no seeds for $KEY — skipping"; exit 0; }
# Per-tank breed terms + bot identity for the crawler's link classifier (from
# tank.json; wagyu gets its historical defaults if this fails).
TANKJSON="$REPO/tanks/$KEY/tank.json"
TANK_TERMS=$(python3 - "$TANKJSON" <<'PYEOF'
import json, sys
cfg = json.load(open(sys.argv[1]))
b = cfg.get("brand", {})
words = set()
breed = (b.get("breed") or "")
for part in breed.replace("&", "/").split("/"):
    part = part.split("(")[0].strip().lower()
    if part: words.add(part)
v = cfg.get("vocab", {})
for term in (v.get("news_search_terms") or []) + (v.get("video_search_terms") or []):
    t = term.strip().lower()
    if t: words.add(t)
print("|".join(sorted(words)))
PYEOF
) || TANK_TERMS=""
TANK_BOT=$(python3 -c "import json,sys;b=json.load(open('$TANKJSON'))['brand'];print(f\"{b['name']}Bot/1.0; +https://www.{b['domain']}/roundup\")" 2>/dev/null) || TANK_BOT=""
# Crawl mode from tank.json crawl.mode — "genetics" (default; original behavior)
# or "live_beef" (WagyuSale-style live cattle + beef link classification).
TANK_CRAWL_MODE=$(python3 -c "import json;print((json.load(open('$TANKJSON')).get('crawl') or {}).get('mode') or 'genetics')" 2>/dev/null) || TANK_CRAWL_MODE="genetics"
export TANK_TERMS TANK_BOT TANK_CRAWL_MODE
node "$REPO/backend/scripts/crawl_listings.cjs" --seeds "$SEEDS" --out "$OUT" \
  --per-site 5 --concurrency 8 --goto-timeout 30000 --max-pages 500
scp -q "$OUT" "$VPS:/root/wagyutank/backend/${KEY}_rendered.json"
ssh "$VPS" "cd /root/wagyutank/backend && set -a && . ../tanks/$KEY/tank.env && set +a && \
  .venv/bin/python -m app.jobs.ingest_rendered ${KEY}_rendered.json && \
  .venv/bin/python -m app.jobs.seed_directory && \
  .venv/bin/python -m app.jobs.enrich_directory && \
  .venv/bin/python -m app.jobs.reap_links && \
  .venv/bin/python -m app.jobs.record_run roundup_crawl"
rm -f "$OUT"
echo "===== $KEY done $(date) ====="
