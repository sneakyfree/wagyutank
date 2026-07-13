# `tanks/_template` — the per-breed starting point

This is the **breed-neutral scaffold** every new tank starts from, so a clone is
never a find-and-replace on a Wagyu-specific copy. It fixes the old template hole
where seed content was WagyuTank-shaped.

## How to use it

**Step 0 — stamp the scaffold** (fills the mechanical placeholders):

```bash
./deploy/scaffold-content.py highland \
    --brand HighlandTank --domain highlandtank.com --breed "Scottish Highland" \
    --port 8122 --gold '#8a6d2b'
```

That copies this directory to `tanks/highland/` and substitutes the tokens it can
derive (`{{KEY}}`, `{{BRAND_NAME}}`, `{{DOMAIN}}`, `{{BREED}}`, colours, port,
pages project, service name) — and staggers the `jobs` schedules by
`--cron-offset` minutes (pick the next free slot: wagyu=0, murraygrey=30, then
60, 90…) so tanks never crawl simultaneously. The `jobs` block declares the
tank's whole recurring-compute layer (VPS news/watchdog + Veron weekly
crawl/harvest); the hatchery's `jobs` phase materializes it as managed cron
blocks on both machines. It then lists the `{{PLACEHOLDERS}}` you still owe.

**Step 1 — fill the breed CONTENT** (the part that can't be templated — it's
knowledge, ~$30–80 of research per breed per TEMPLATE_SPEC §8):

| File | What to write | Model tier |
|------|---------------|-----------|
| `seed/breed_history.md` | ~1.5–3k word fact-checked breed history | Sonnet research → Opus/Fable prose → **flagship fact-check + human skim** |
| `seed/foundation_animals.json` | the breed's foundation/notable sires & dams (schema pre-shaped) | Opus/Fable, facts checked vs the registry |
| `seed/faq.json` | marketplace + breed FAQ | Sonnet |
| `seed/roundup_seeds.json` | real seller catalog URLs (rounds-of-2 discovery sweep) | Sonnet |
| `seed/facilities.json` | collection/embryo/storage facilities for this breed (optional; `[]` is fine) | Sonnet |
| `tank.json` | finish `help_nuance`, registry names, founder substitutions, feature flags | judgment |

**Optional deeper-content seed files** (each unlocks a section; **absent = that
seeder safely SKIPS** — a clone never inherits Wagyu's data, per
`tank.seed_path_strict`):

| Optional file | Feeds | Shape reference (wagyu's copy) |
|---|---|---|
| `seed/sale_events.json` | Sale Reports history + charts | `backend/app/seed/data/sale_events.json` |
| `seed/upcoming_sales.json` | sales calendar | `backend/app/seed/data/upcoming_sales.json` |
| `seed/notable_sales.json` | Hall of Records | dict shape of `seed_notable_sales.SALES` |
| `seed/foundation_reference_prices.json` | Price-Index reference prices | `backend/app/seed/data/foundation_reference_prices.json` |
| `seed/animal_photos.json` | foundation photo galleries | `backend/app/seed/data/animal_photos.json` |
| `seed/great_sires.json` / `zenkyo.json` / `feeding.json` | their feature pages (usually OFF for clones) | wagyu's copies |

House ads need **no** file — `seed_ads` templates them from the brand. Curated
discussion threads (`seed_comments`) are wagyu-only and skip on clones.

**Brand art (binary assets tankify can't rewrite):** the frontend postbuild
auto-generates a branded `og-image.png` (social card) + `favicon.svg` (medallion)
from the tank's colors/wordmark, so a clone never ships WagyuTank's. Replace with
designer art whenever ready by dropping files into `tanks/<key>/public/` and
copying them into the site build. The `components/Logo.tsx` medallion SVG is the
one remaining hand-crafted mark (wagyu's marbled ribeye) — swap it per tank when
you want a real logo; until then the wordmark carries the brand.

Leave `{{TOKENS}}` you don't have data for — they're visible and greppable, not
silent gaps. Niche communities are unforgiving of wrong breed facts, so **fact-
check before serving**.

**Step 2 — hatch the infrastructure** (idempotent, one command):

```bash
./deploy/hatch-tank.sh highland
```

See `docs/TANK_HATCHERY.md` for the full runbook and what each phase does.

## Placeholder reference

`{{KEY}}` tank key · `{{BRAND_NAME}}` · `{{DOMAIN}}` · `{{BREED}}` /
`{{BREED_UPPER}}` · `{{SPECIES}}` · `{{LOGO_TEXT}}` · `{{COLOR_GOLD*}}` ·
`{{PORT}}` · `{{CRON_OFFSET_MIN}}` · `{{REGISTRY_PRIMARY/SECONDARY}}` ·
`{{HELP_NUANCE}}` (the one-line breed disambiguation the help bot uses) ·
`{{FOUNDER_1..3}}` (marquee founders, for copy substitutions) · plus the
content tokens inside each `seed/` file.
