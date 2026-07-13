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

## 6a. Compute doctrine — which machine runs what, and why

Three machines, three roles. The decision rule for ANY new recurring job:
**default it to the VPS** — we pay a flat monthly rate for that CPU whether it
works or idles, so idle VPS capacity is wasted money. Move a job to Veron ONLY
if it needs one of the three things a headless datacenter box can't give:
**(a) a residential IP** (DDG, YouTube, GDELT, many seller sites block or
throttle datacenter ranges), **(b) JS rendering at scale** (Playwright/Chromium
fleets), or **(c) the GPU** (vision, whisper, local LLM). Windy 0 is a dev/build
box — it runs NO recurring tank jobs (frontend builds, wrangler deploys, and the
hatchery itself run there interactively).

| Machine | Hardware / network | Recurring role |
|---|---|---|
| **VPS** `vps` (72.60.118.54, Hostinger) | 4 vCPU / 16GB, flat monthly, datacenter IP | System of record + 24/7 workhorse: every `tank@<key>` API process, all SQLite DBs, RSS/httpx news crawls, LLM content jobs (translation, highlights, sale radar, digest) via Windy Mind, watchdog, seeders, all email sends |
| **Veron 1** `wg-veron` (10.10.0.6) | RTX 5090 + Core Ultra 9, residential T1 | The residential/heavy specialist, weekly cadence: `tank-crawl.sh <key>` (Playwright JS-rendered Roundup crawl via `backend/scripts/crawl_listings.cjs`) + `tank-harvest.sh <key>` (yt-dlp video harvest). **Every result ships home to the VPS** (scp → ingest under the tank's env) — Veron is a worker, never a store |
| **Windy 0** (this box) | dev iMac, bad internet | Dev checkout only. Nothing recurring. (It briefly owned the crawl until 2026-07-11; fully retired from tanks — see the crawler memory banner) |

**Job declaration is data, not folklore:** each tank's `tank.json` carries a
`jobs` block (`vps[]` = module+schedule run via `deploy/run-tank-job.sh`,
`veron[]` = script+schedule). The hatchery's `jobs` phase materializes these as
marker-delimited cron blocks on both machines — idempotent, adopting any
hand-typed strays, preserving every unrelated line. Schedules are staggered per
tank by `crawl.cron_offset_min` (wagyu 0, murraygrey 30, next 60…) so tanks
never crawl simultaneously.

**Extraction lane (honest current state):** the crawl's LLM fact-extraction runs
on the **VPS** through Windy Mind → Groq's free lane (llama-3.3-70b) — $0, per
the no-cloud-cost rule, but rate-limited (the documented throughput ceiling).
The sanctioned upgrade when that ceiling bites: move extraction to a **local
model on Veron's 5090** during the crawl itself — faster, unmetered, still $0.
Not yet built.

**Discovery-yield lessons (hard-won on Wagyu — apply to every new breed):**
- Highest yield = crawlable breed-association **member directories**
  (server-rendered lists; one akaushi.com page ≈ 60 listings). Hunt these first.
- Individual ranch/stud pages ≈ 1–2 listings each — fine, not the accelerator.
- JS marketplaces/classifieds (MercadoLibre, AuctionsPlus, Gumtree…) = **0
  yield** — lazy-loaded category pages the extractor can't read. Skip.
- Expect a finite ceiling per breed (Wagyu saturated ≈ 430 sellers / 750
  listings after ~40 discovery agents). Rounds-of-2 agents, inline WebSearch,
  NO nested sub-agents (nested fan-out hangs).

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
- **P2 (frontend config-driven + brand + help-bot) — DONE (live, invisible):**
  build-time bake of `/api/config`→`lib/tank.config.json`; `lib/tank.ts`
  featureOn()/products()/brand; Header nav + footer feature-gated + config products;
  layout metadata/title/keywords/JSON-LD + footer contact/location/legal + Logo
  wordmark all from config; help-bot prompt (`help._system()`) templated with
  brand+breed+`vocab.help_nuance`. WagyuTank byte-identical (nav 13 links, title,
  contact, wordmark, help-bot Akaushi rule all verified). REMAINING (deferred to
  clone-scaffold, they're per-tank CONTENT not engine): home hero i18n strings,
  news/video search-term feeds, extractor species mention, medallion SVG per tank.
- **P3 (factory) — DONE (scaffold + template unit + watchdog labeling):**
  `deploy/new-tank.sh` (own DB + fresh JWT + port + schema + systemd enable;
  verified DATABASE_URL env-override isolates tank DBs) + `deploy/tank@.service`
  template unit + watchdog now labels per-tank (brand name in subject/header).
  Passport SSO DESIGNED (§7b) but wired at P4 (needs a 2nd tank to test).
- **P4:** stand up clone #1 (breed TBD) as the proving run.

P0–P3 ≈ a focused multi-day sprint; nothing user-visible changes on wagyutank.com.

## 7b. Passport (shared identity across tanks) — architecture

Decided: one account works on every tank; reputation travels. Chosen design (to
wire when clone #1 exists, so it's testable across two real tanks):

- **Shared AUTH database, per-tank MARKETPLACE databases.** Add `AUTH_DATABASE_URL`
  (defaults to the tank's own `DATABASE_URL` — so WagyuTank alone is unchanged).
  When a shared value is set, the `users` table + all auth flows (register, login,
  reset, verify, 2FA, roles) read/write the shared auth DB; listings/orders/bids/
  ratings stay in the tank's own DB. A JWT signed with a shared `AUTH_JWT_SECRET`
  validates on any tank → one login everywhere.
- **Reputation travel:** buyer/seller ratings live on the shared `users` row
  (aggregate), so a strong WagyuTank seller arrives on HighlandTank already
  reputable. Per-transaction Feedback rows stay per-tank; each tank's `_recompute`
  writes the aggregate to the shared user.
- **Registration friction remover:** "already have an account on any of our
  marketplaces? just sign in" — same shared auth DB makes this automatic.
- **Future OmniTank/TankTank hub:** a directory site over the shared auth DB +
  each tank's public listing API. Not needed until several tanks exist.
- **Why deferred:** cross-DB auth routing touches every auth query; building it
  with zero clones = untestable. Wire + verify at P4 with a real second tank.

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
