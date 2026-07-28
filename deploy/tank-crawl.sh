#!/usr/bin/env bash
# Weekly Roundup crawl for a tank — runs on VERON 1 (24-core, residential IP).
# Crawls the tank's seed sellers, ships to the VPS, ingests + refreshes the Atlas
# under that tank's env, reaps dead links, and phones home. In version control so
# it survives any single machine dying; Veron runs it from ~/wagyutank/deploy/.
#   tank-crawl.sh <tank_key>
set -e
KEY="${1:?usage: tank-crawl.sh <tank_key>}"

# One crawler at a time across the whole fleet. The tanks are cron-staggered 30
# minutes apart, which was ample when a run took ~20 minutes — but the effective
# seed list is now the Atlas (wagyu went 43 -> 401 sites), so a run can outlast
# its slot and collide with the next tank. Queue instead of overlapping: Veron
# runs one crawl, the others wait their turn. Doctrine is one crawler per tank at
# a time, and an overlapping fleet would thrash the box and the target sites.
LOCK="/tmp/tank-crawl.lock"
if [ -z "${TANK_CRAWL_LOCKED:-}" ]; then
  export TANK_CRAWL_LOCKED=1
  exec flock -w 21600 "$LOCK" "$0" "$@"
fi

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
# Effective seed list = curated seeds ∪ the Atlas (every operation we've already
# identified, plus candidates discovered from outbound links on previous runs).
# Built on the VPS where the tank's DB lives, then pulled here. If anything about
# that fails we fall back to the curated file — the crawl must never not run.
EFFECTIVE="/tmp/${KEY}-seeds-effective.json"
if ssh "$VPS" "cd /root/wagyutank/backend && set -a && . ../tanks/$KEY/tank.env && set +a && \
     .venv/bin/python -m app.jobs.export_seeds /tmp/${KEY}_seeds.json" \
   && scp -q "$VPS:/tmp/${KEY}_seeds.json" "$EFFECTIVE" \
   && [ -s "$EFFECTIVE" ]; then
  SEEDS="$EFFECTIVE"
else
  echo "export_seeds unavailable — falling back to curated seed file"
fi

# Page budget must scale with the seed list, not sit at a flat 500. WagyuSale has
# 429 seeds and was exhausting the budget at site ~290 every night ("budget -6"),
# so a third of its sellers were never crawled at all — silently, since the run
# still reported success. Floor 500, then ~3 pages per seed.
SEED_COUNT=$(python3 -c "import json;print(len(json.load(open('$SEEDS'))))" 2>/dev/null || echo 0)
MAX_PAGES=$(( SEED_COUNT * 3 ))
[ "$MAX_PAGES" -lt 500 ] && MAX_PAGES=500
echo "Seeds: $SEED_COUNT · page budget: $MAX_PAGES"
node "$REPO/backend/scripts/crawl_listings.cjs" --seeds "$SEEDS" --out "$OUT" \
  --per-site 5 --concurrency 8 --goto-timeout 30000 --max-pages "$MAX_PAGES"
scp -q "$OUT" "$VPS:/root/wagyutank/backend/${KEY}_rendered.json"
CANDS="${OUT%.json}-candidates.json"
[ -f "$CANDS" ] && scp -q "$CANDS" "$VPS:/root/wagyutank/backend/${KEY}_candidates.json" || true
# Ingest, then phone home with the REAL added count. record_run was being called
# with no argument, so every crawl logged "added=0" on the health dashboard no
# matter how many listings it actually brought in.
ssh "$VPS" "cd /root/wagyutank/backend && set -a && . ../tanks/$KEY/tank.env && set +a && \
  .venv/bin/python -m app.jobs.ingest_rendered ${KEY}_rendered.json | tee /tmp/${KEY}_ingest.out && \
  .venv/bin/python -m app.jobs.seed_directory && \
  .venv/bin/python -m app.jobs.discover_sites ${KEY}_candidates.json && \
  .venv/bin/python -m app.jobs.enrich_directory && \
  .venv/bin/python -m app.jobs.reap_links && \
  ADDED=\$(sed -n 's/.*added=\([0-9]\+\).*/\1/p' /tmp/${KEY}_ingest.out | tail -1) && \
  .venv/bin/python -m app.jobs.record_run roundup_crawl \${ADDED:-0}"
rm -f "$OUT"
echo "===== $KEY done $(date) ====="
