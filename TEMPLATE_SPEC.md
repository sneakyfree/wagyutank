# The Tank Template — extraction spec

**Goal:** turn WagyuTank from *a site* into *an engine that stamps out sites* — one
codebase driving N niche genetics marketplaces ("tanks"): HighlandTank, HolsteinTank,
a dog stud-service tank, etc. Engine changes propagate to every tank; content stays
per-tank. WagyuTank itself becomes config #1 running on the same engine.

**Design rule for every gray-zone decision:** put it in the ENGINE unless it is
genuinely species-specific. Structure flows to everyone; content stays local.

---

## 1. Architecture

```
tank-engine/                    (this repo, renamed conceptually — ONE codebase)
  backend/                      FastAPI engine (unchanged layout)
  site/                         Next.js engine (wagyutank-site merges in or stays sibling)
  tanks/
    wagyu/
      tank.json                 ← brand + taxonomy + features + vocab
      seed/                     ← breed content (what's now backend/app/seed/data/)
      public/                   ← logo, og-image, foundation photos
    highland/
      tank.json
      seed/
      public/
```

- **One process per tank** on the VPS (`tank@wagyu.service`, `tank@highland.service`
  via a systemd template unit), each with **its own SQLite DB** and **its own port**;
  nginx routes `api.<domain>` → port. NOT single-process multi-tenant: isolation is
  worth more than the ~150MB/tank, a bug in one tank can't corrupt another's data,
  and per-tank restart/backup stays trivial.
- **One CF Pages project per tank** (`wagyutank`, `highlandtank`, …). The Next.js
  build takes `TANK=highland` and reads that tank's config/public at build time.
- Deploys: `git pull` once on the VPS, restart all tank services (systemd template
  makes this one command). Frontends rebuild per tank (only when engine or that
  tank's config changed).

## 2. `tank.json` — the per-tank config schema

```jsonc
{
  "key": "highland",
  "brand": {
    "name": "HighlandTank", "domain": "highlandtank.com",
    "tagline": "The world's marketplace for Highland cattle genetics",
    "species": "cattle", "breed": "Scottish Highland",
    "logoText": "HT", "colors": {"gold": "#8a6d2b"},         // theme tokens
    "contactEmail": "office@highlandtank.com",
    "legal": "Salt Lake City, Utah, USA · a Utah company"
  },
  // THE key generalization — product taxonomy is data, not a Python enum:
  "products": [
    {"key": "semen",  "label": "Semen",  "unit": "straw",  "icon": "sperm",
     "fresh_chilled": false},
    {"key": "embryo", "label": "Embryos","unit": "embryo", "icon": "morula"}
    // dog tank: semen w/ fresh_chilled:true + {"key":"stud_service", ...}; no embryo
  ],
  "features": {                     // Wagyu-only sections become flags
    "japan_hub": false, "zenkyo": false, "feeding": false, "great_sires": false,
    "foundation": true, "history": true, "news": true, "market_data": false,
    "price_index": true, "sale_reports": true, "videos": true, "catalog": true,
    "roundup": true, "directory": true, "help": true, "ads": true
  },
  "vocab": {                        // words the engine templates into copy/prompts
    "animal_singular": "cow", "animal_plural": "cattle",
    "registry_names": ["Highland Cattle Society", "AHCA"],
    "export_program": "CSS",        // null if N/A (dogs)
    "news_search_terms": ["Highland cattle", "fold of Highland"],
    "video_search_terms": ["Highland cattle", "Highland bull"]
  },
  "langs": ["en", "es", "de"],      // translation targets (Wagyu keeps 6 incl ja/zh)
  "crawl": {"cron_offset_min": 30}  // stagger: wagyu 04:00, highland 04:30, ...
}
```

## 3. Inventory — where every current piece lands

**ENGINE (species-neutral, ~85%):** auth/roles/2FA · listings/bids/orders/payments
(Stripe Connect) · aggregator + JS crawler + ingest + reaper + delist · directory
(Atlas) · claim-your-listings + email verification · flag/takedown + RemovalRequest ·
ratings/feedback/follow/feed · discussions/comments + translate-on-read · help bot
(ai.chat) · watchdog + health + record_run · admin panel · ads · campaigns/digest
machinery · search · videos harvest/ingest/theater · news machinery · price-index
machinery · sitemap/SEO scaffolding · i18n framework.

**CONFIG/CONTENT (per tank):** everything in `backend/app/seed/data/` (foundation
animals + photos, breed_history.md, faq.json, feeding.json, great_sires.json,
zenkyo.json, sale_events.json, upcoming_sales, reference prices, **roundup_seeds.json**)
· news feeds + search queries · video search queries · digest subject/copy ·
help-bot system-prompt breed facts · logo/og-image/favicon · i18n dictionary
extras · mock/sample listings.

**FEATURE-FLAGGED (exist in engine, off unless the tank wants them):** /japan,
/zenkyo, /feeding, /great-sires, /market (USDA data is cattle-specific), catalog
editions, price-index ticker tape.

**HARDCODED-WAGYU TO TEMPLATE (the actual extraction work, from grep):** config.py
brand strings · news.py queries/feeds · price_index.py sire names · sale_radar
prompts · translate.py "preserve breed proper nouns" list · email.py from-name +
templates · help.py system prompt · seed_directory/videos harvest queries ·
frontend Header/hero/footer copy, Logo.tsx, metadata, i18n STRINGS.

## 4. Schema change: ProductType enum → data

The ONE structural migration. `ProductType(str, enum.Enum)` (semen/embryo/
clone_rights) is baked into Listing, AggregatedListing, schemas, and frontend
PRODUCT_LABEL/ProductBadge. Becomes: `product_type: str` validated against the
tank's `config.products[*].key` at the API boundary; frontend renders label/unit/
icon from config. Wagyu's three keys stay identical → **zero data migration for
existing rows**. Extractor + LLM prompts take the product vocabulary from config
(a dog tank extracts "fresh chilled semen" listings; embryo never appears).
`fresh_chilled` is a product attribute, not a new architecture.

## 5. The clone factory — per-tank checklist (with model tier)

| # | Step | What | Tier |
|---|------|------|------|
| 1 | Scaffold | `./new-tank.sh highland` → tank dir, DB, port, systemd unit, staggered cron, CF Pages project, DNS | script |
| 2 | Discovery | rounds-of-2 agent sweep → that breed's roundup_seeds (the proven playbook) | Sonnet |
| 3 | Content | foundation/notable animals, history, FAQ, news+video queries — **facts checked against registries; niche communities are unforgiving** | Opus/Fable + human skim |
| 4 | Brand | logo/colors/og-image | judgment |
| 5 | Wire | fill tank.json, seed, build, deploy | Haiku/script |
| 6 | QA | smoke pages, crawl one batch, verify Atlas/help-bot/takedown, fact-check pass | Opus/Fable |

First clone (Highland) = the template's proving run; expect to move the engine/
config line once. Clones 3+ ≈ days each, mostly steps 2–3.

## 6. Infra plan (from measured VPS state)

4 vCPU / 16GB / 75GB free; each tank ≈150MB RAM + MB-scale DB. **Comfortable: 10–15
tanks on this box.** Prereqs before tank #2: (a) add 4–8GB swap (box has none),
(b) staggered crawl crons via `crawl.cron_offset_min`, (c) shared free-LLM lane is
the real throughput ceiling — the watchdog already monitors per-tank jobs; extend
its report to group by tank. Past ~20 tanks: second small VPS or shift crawl load
to Windy 0 (which already does all JS rendering + video harvest for every tank —
its weekly scripts loop over tanks). Frontends: CF Pages free tier, no limit that
matters. Email: one Resend account, per-domain verified senders (office@<domain>,
per the email doctrine).

## 7. Migration path for WagyuTank (no big-bang)

- **P0 (prep) — DONE:** `tanks/wagyu/tank.json` created; nothing reads it yet.
- **P1 (backend config) — DONE (live, invisible):** `app/tank.py` loader (TANK env,
  wagyu fallback) + `GET /api/config` + config-driven product gate on listing-create.
  KEY FINDING: `product_type` columns are already plain `VARCHAR(32)` (no CHECK) —
  the enum is Python-only — so config narrows the *allowed subset* per tank with
  ZERO DB risk. Novel product types (dog stud-service) only need the model column
  typed `String`; do it at first-non-cattle-tank scaffold (fresh DB, no migration).
- **P2 (frontend config-driven) — DONE (partial, live, invisible):** build-time
  bake of `/api/config` → `lib/tank.config.json` (prebuild `scripts-gen-tank-config.mjs`,
  `TANK_API` picks tank, committed WagyuTank default so builds never need the API);
  `lib/tank.ts` featureOn()/products(); Header nav (desktop+mobile) feature-gated +
  product sub-links from config. Wagyu byte-identical (all 13 links verified live).
  STILL TODO in P2: brand tokens (name/logo/colors/contact/legal) + hero/footer copy
  from config; sweep remaining hardcoded-Wagyu strings (§3) → vocab; template the
  backend LLM prompts (extractor/classifier/help/news queries) in `vocab`.
- **P3:** `new-tank.sh` + systemd template unit + watchdog per-tank grouping +
  shared-identity (passport) auth service.
- **P4:** stand up clone #1 (breed TBD) as the proving run.

P0–P3 ≈ a focused multi-day sprint; nothing user-visible changes on wagyutank.com.

## 8. Decisions (Grant, 2026-07-11)

- **Passport login: YES — decided.** One account works across every tank ("do you
  already have an account with any of these platforms?"). Future roll-up hub à la
  Craigslist (TankTank/OmniTank .com) listing all tanks. Design the engine's auth
  for a shared identity service from the start; reputation (buyer/seller ratings)
  travels with the account across tanks.
- **Engine: build DELUXE — decided.** All machinery (encyclopedia, history,
  price index, news, videos, market data frameworks) goes into the one-time
  engine; every clone inherits every capability.
- **Cost model (clarified):** engine = one-time. Per-breed deluxe CONTENT (that
  breed's foundation animals/history/records) ≈ $30–80 of research tokens per
  clone — recurring per breed, can't be templated. Lean-vs-deluxe is therefore a
  per-breed content dial, not a template fork. Grant's current lean: deluxe
  content for early breeds; revisit only at hundreds-of-niches scale.
- Model policy: Sonnet for discovery/research/wiring, Opus/Fable for flagship
  prose + final fact-check, Haiku/scripts for mechanical steps.
- Still open: which breed is clone #1 (Highland vs Holstein vs other — under
  discussion); legal entity/footer per tank.
