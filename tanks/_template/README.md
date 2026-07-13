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
pages project, service name). It then lists the `{{PLACEHOLDERS}}` you still owe.

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
