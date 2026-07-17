#!/usr/bin/env bash
# The clone factory — scaffold a new tank (niche genetics marketplace) on the engine.
#
#   ./new-tank.sh <key> "<Name>" <domain> "<Breed>" [species] [products]
#   ./new-tank.sh highland "HighlandTank" highlandtank.com "Scottish Highland" cattle semen,embryo
#
# Creates tanks/<key>/{tank.json,tank.env,seed/,public/}, allocates the next port in
# tanks/PORTS, and prints the exact go-live steps (VPS unit, nginx, DNS, CF Pages,
# crons). Repo-only by default — nothing touches the VPS until you run the printed
# steps, so scaffolding is always safe. Content (seed sellers, foundation animals,
# history, FAQ) is per-breed research — see TEMPLATE_SPEC.md §5 for the checklist.
set -euo pipefail
cd "$(dirname "$0")"

KEY="${1:?usage: new-tank.sh <key> \"<Name>\" <domain> \"<Breed>\" [species] [products]}"
NAME="${2:?name required (e.g. HighlandTank)}"
DOMAIN="${3:?domain required (e.g. highlandtank.com)}"
BREED="${4:?breed required (e.g. \"Scottish Highland\")}"
SPECIES="${5:-cattle}"
PRODUCTS="${6:-semen,embryo}"

[[ "$KEY" =~ ^[a-z0-9_]+$ ]] || { echo "key must be [a-z0-9_]"; exit 1; }
[ -d "tanks/$KEY" ] && { echo "tanks/$KEY already exists"; exit 1; }

# ---- port allocation (tanks/PORTS is the registry; wagyu=8120 reserved) ----
touch tanks/PORTS
grep -q "^wagyu=" tanks/PORTS || echo "wagyu=8120" >> tanks/PORTS
LAST=$(cut -d= -f2 tanks/PORTS | sort -n | tail -1)
PORT=$((LAST + 1))
echo "$KEY=$PORT" >> tanks/PORTS

# ---- crawl stagger: 30min per existing tank ----
N=$(wc -l < tanks/PORTS)
OFFSET=$(( (N - 1) * 30 ))

mkdir -p "tanks/$KEY/seed" "tanks/$KEY/public"

# ---- products json from the comma list (labels/units for the known types) ----
PRODUCTS_JSON=$(python3 - "$PRODUCTS" <<'PY'
import json, sys
KNOWN = {
  "semen":        {"label": "Semen",          "unit": "straw",  "icon": "sperm"},
  "embryo":       {"label": "Embryos",        "unit": "embryo", "icon": "morula"},
  "clone_rights": {"label": "Cloning Rights", "unit": "right",  "icon": "helix"},
  "stud_service": {"label": "Stud Service",   "unit": "service","icon": "sperm"},
}
out = []
for k in sys.argv