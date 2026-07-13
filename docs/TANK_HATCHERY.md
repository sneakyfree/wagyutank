# The Tank Hatchery

One idempotent command that hatches a complete breed-marketplace tank — backend,
DNS, mail (send **and** receive), Pages, seed, smoke — with **zero hand-wiring**,
and converges an existing tank without breaking it.

```bash
./deploy/hatch-tank.sh <tank_key>                 # hatch or converge everything
./deploy/hatch-tank.sh <tank_key> --dry-run       # detect only, change nothing
./deploy/hatch-tank.sh <tank_key> --only mail-dns,stalwart
./deploy/hatch-tank.sh <tank_key> --skip seed,frontend
```

Everything is **detect-then-converge**: re-running is safe and cheap. A second run
of a finished tank makes zero changes (every line reports `unchanged` / `exists`).

---

## The whole flow, start to finish

A brand-new breed (say Highland) goes from nothing to live in three commands:

```bash
# 0. stamp the breed-neutral content scaffold (fills mechanical placeholders)
./deploy/scaffold-content.py highland \
    --brand HighlandTank --domain highlandtank.com --breed "Scottish Highland" \
    --port 8122 --gold '#8a6d2b'

# 1. fill the breed CONTENT by hand — the part that can't be templated
#    (tanks/highland/seed/*: history, foundation animals, faq, seller sites).
#    See tanks/_template/README.md and TEMPLATE_SPEC.md §5.

# 2. hatch the infrastructure (idempotent)
./deploy/hatch-tank.sh highland --with-frontend
```

For an **existing** tank you're just converging (e.g. filling an email gap), skip
step 0/1 and run step 2 — it fixes only what's missing.

---

## Prerequisites

- Run from **Windy 0** (or any box with the repo, `curl`, `ssh`, and — for the
  `frontend` phase — `node`/`npm`). All HTTP goes through `curl` because
  Cloudflare and Resend 403 python-urllib from our IPs.
- **SSH reachability** (already configured in `~/.ssh/config`):
  - `vps` → the backend VPS (72.60.118.54)
  - `windy-mail` → the shared Stalwart mail EC2 (via ProxyJump `vps`)
- **Secrets:** copy `deploy/.hatch-secrets.env.example` → `deploy/.hatch-secrets.env`
  (gitignored) and fill from the fleet lockbox
  (`sneakyfree/kit-army-config/ACCESS_LOCKBOX.md`):

  | Var | What | Lockbox |
  |-----|------|---------|
  | `CF_GOD_TOKEN` | Zone:Read + **zone.create** + Pages | §16 god token |
  | `CF_DNS_TOKEN` | Zone:Read + **DNS:Edit** across all zones | `ZoneREADDNSEdit` |
  | `CF_PAGES_TOKEN` | Pages/Workers + custom-domain attach | Pages deploy token |
  | `CF_ACCOUNT_ID` | `193b347aedeaafe35de0b5a534b2d9aa` (all zones live here) | — |
  | `RESEND_API_KEY` | shared ecosystem key (YOLOTOKEN) | §mail |
  | `STALWART_PASSWORD` | Stalwart admin secret | `STALWART_ADMIN_SECRET` |
  | `STALWART_FOUNDER_ACCOUNT` / `_EMAIL` / `_PASSWORD` | the one founder mailbox every tank's `office@` consolidates into (`c3` / `gwhitmer@windstorminstitute.org`) | §Founder Unified Mailbox |

---

## The phases

Run in this order (default). Each is independently runnable with `--only`.

| Phase | What it converges | Idempotency check |
|-------|-------------------|-------------------|
| `scaffold` | VPS: tank dir + **`tank.env`** (the DB/JWT/port isolation boundary), DB schema (`migrate` — additive + **model-derived drift heal**), systemd unit (`tank@<key>` or legacy `wagyutank-api`), nginx `api.<domain>` block | file/unit/grep presence |
| `zone` | Cloudflare zone for the domain (creates if new; then warns to repoint registrar NS) | `GET /zones?name=` |
| `web-dns` | `api.<d>` A→VPS (proxied) + apex/www CNAME→`<project>.pages.dev` (proxied) | record match on (type,name) |
| `pages` | CF Pages project + custom-domain attach (apex+www) | project GET + domains list |
| `resend` | Resend domain add → pulls its DNS records → creates them in CF → verify + poll | Resend domain status |
| `mail-dns` | **receive + policy** records: MX apex→`mail.windymail.ai`, apex SPF, DMARC, autoconfig/autodiscover | record match |
| `stalwart` | mail **domain** + `office@<d>` as an **alias on the one founder mailbox** (the `gwhitmer` principal — NOT a separate login) + domain **catch-all** → office | `query Domain` / founder alias map |
| `seed` | runs the tank's content seeders on its DB (feature-gated) | seeders are idempotent-replace |
| `jobs` | the **recurring-compute layer** on both machines: VPS cron block (news/watchdog via `run-tank-job.sh`) + Veron cron block (weekly `tank-crawl.sh` + `tank-harvest.sh`), declared in `tank.json jobs` | marker-block text comparison |
| `frontend` | `TANK_API=… npm run build` + `wrangler pages deploy` (off by default — `--with-frontend`) | — |
| `smoke` | `deploy/smoke_tank.py` end-to-end verification | — |

### Why send **and** receive both matter — and the one-mailbox model

Resend gives a domain **outbound** (DKIM/SPF via `send.<d>` + `resend._domainkey`).
That alone does **not** let `office@<domain>` receive anything. The `mail-dns` +
`stalwart` phases add the **inbound** half — MX at the apex pointing to the shared
Stalwart, and a catch-all so `info@`/`sales@`/anything@ has somewhere to land.

### The recurring-compute layer (`jobs` phase)

The backend isn't just a process — it's a fleet of crawlers and content
generators split across two machines by the **compute doctrine**
(TEMPLATE_SPEC §6a): the flat-rate **VPS** runs everything it can (API, RSS
news crawls, LLM content jobs, watchdog, digest — idle VPS CPU is wasted
money); **Veron 1** (5090 + residential T1, `wg-veron`) runs only what a
datacenter box can't — Playwright JS-rendered crawling and yt-dlp video
harvest — and ships every result home to the VPS. Windy 0 runs nothing
recurring.

Each tank **declares** its jobs in `tank.json`:

```jsonc
"jobs": {
  "vps": [
    {"module": "app.jobs.news",     "schedule": "20 5,17 * * *"},
    {"module": "app.jobs.watchdog", "schedule": "40 11 * * *"}
  ],
  "veron": [
    {"script": "tank-crawl.sh",   "schedule": "30 4 * * 0"},   // weekly Roundup crawl
    {"script": "tank-harvest.sh", "schedule": "30 6 * * 0"}    // weekly video harvest
  ]
}
```

The `jobs` phase materializes these as a marker-delimited block in each
machine's crontab (`# >>> tank:<key> … <<<`), **adopting** any pre-existing
hand-typed lines for that tank, replacing an existing block in place, and
preserving every unrelated crontab line byte-for-byte (backup at
`~/.crontab.pre-hatch.bak`). Change a schedule by editing `tank.json` and
re-running — never by editing crontabs.

`scaffold-content.py` staggers a new tank's schedules by `--cron-offset`
minutes (wagyu=0, murraygrey=30, next=60…) so tanks never crawl at once.

**Reference inventory (what actually runs today):**

| Tank | VPS | Veron |
|---|---|---|
| wagyu *(legacy)* | systemd timers: news 3×/day, aggregate daily 06:38, digest Mon 14:00 + watchdog cron 11:30 — report-only, managed outside the hatchery | crawl Sun 04:00, harvest Sun 06:00 (managed block) |
| murraygrey | managed block: news 05:20+17:20, watchdog 11:40 | crawl Sun 04:30, harvest Sun 06:30 (managed block) |

New tanks get the murraygrey shape (cron via `run-tank-job.sh`), not wagyu's
legacy timers.

**One founder mailbox, not one login per tank.** Every tank's `office@<domain>` is
added as an **alias on the single `gwhitmer` principal** — the same mailbox Grant
reads in Roundcube for all ~19 domains. So a new tank's mail just shows up in the
one inbox (sendable-as via the client's From: dropdown), with **no new password and
no separate login**. `office@<domain>` is the property's machine channel (what the
app sends as and the site shows); the founder mailbox is where a human reads and
replies. If you ever want a tank's mail to go to a dedicated employee login instead,
that's a deliberate later step — the default is consolidation.

---

## The smoke suite

```bash
./deploy/smoke_tank.py <tank_key> [--no-mutate]
```

Verifies, end to end:

1. apex + www serve HTTP 200
2. the API is up and `/api/config` reports the right brand (name + colours + `office@` contact)
3. the brand name appears in the site HTML
4. seed data is loaded (foundation animals present)
5. the **founder mailbox** logs in over IMAP
6. an email **from** `office@<domain>` **lands in the founder inbox** with **From =
   office@<domain>** — proving the alias/catch-all consolidation + From, in one loop
7. a listing can actually be created via the API (then cleaned up)

`--no-mutate` skips the listing-create write. Checks that can't run (e.g. no
`STALWART_FOUNDER_PASSWORD` set) are reported `SKIP`, not `FAIL`. The mail checks
log in as the shared founder mailbox (from the secrets file), not a per-tank
account — there is no per-tank mailbox password.

---

## Idempotency & re-runs

- **Proven** against `murraygrey`: a second full run reported `unchanged` on every
  DNS record, Pages domain, Resend record, and Stalwart object, and `exists` on the
  mailbox — zero mutations.
- The `stalwart` phase appends `office@<domain>` to the founder principal's alias
  map **preserving every existing alias**, and no-ops if it's already there — so
  re-running can't disturb the other domains' mail. (A leftover standalone
  `office@` account from the older per-tank pattern is auto-retired into the alias.)
- DNS convergence matches on `(type, name)` (+ SPF/DMARC/DKIM category for TXT), so
  it updates the intended record and never clobbers a sibling.

---

## Clone-proofing guarantees (the 2026-07-13 steamroller pass)

- **No Wagyu data can leak into a clone's DB**: every content seeder resolves via
  `tank.seed_path_strict` — a missing per-tank seed file means SKIP, never
  "fall back to Wagyu". Curated wagyu-only content (`seed_comments`) refuses to
  run on clones; house ads are templated from the brand.
- **No Wagyu strings can leak into a clone's pages/emails/prompts**: all links
  derive from `tank.base_url()`; digest/verify/help/ads/LLM-prompts all read
  `tank.brand()`/`vocab()`; tankify also rewrites ALL-CAPS `WAGYU` and CJK `和牛`.
- **One env var builds a clone frontend**: `TANK_API` (or `NEXT_PUBLIC_API_BASE`
  — either works everywhere now) drives config bake, sitemap, API base, tankify,
  and the generated brand assets (og-image + favicon) in one `npm run build`.
- **Crawlers hunt the right breed on the right machine**: `tank-crawl.sh` passes
  `TANK_TERMS`/`TANK_BOT` from tank.json into the Veron crawler's link
  classifier; `harvest_videos.py` builds every query from the target tank's
  `/api/config`.
- The smoke suite enforces all of it, including "clone serves its OWN og-image".

## Troubleshooting

- **`no such column …` / a page 500s after a code bump** — schema drift. Run
  `--only scaffold`; `migrate` now heals drift generically from the ORM model
  (not just a hand-maintained column list), so any missing column is added.
- **Resend won't verify** — DNS still propagating. Re-run `--only resend` later;
  it re-triggers verify and polls.
- **IMAP login fails with a cert error** — the shared Stalwart presents a
  self-signed cert on 993; the smoke suite connects without chain verification
  (this is our own infra). Mail clients use "manual setup" for the same reason.
- **New domain doesn't resolve** — the `zone` phase created the CF zone but the
  registrar's nameservers still point elsewhere. Repoint NS to the two Cloudflare
  nameservers it printed (GoDaddy: `PATCH /v1/domains/<d>` `nameServers`).
- **`sqlite3: command not found`** — the VPS has no sqlite CLI; the smoke cleanup
  goes through the app's SQLAlchemy engine instead (no action needed).

---

## Notes on WagyuTank itself (the legacy tank)

WagyuTank runs as the original `wagyutank-api.service` off `backend/.env`, not
`tank@wagyu`. Its `tank.env` exists **only** so `run-tank-job.sh wagyu …` targets
the right DB — it deliberately does **not** override `DATABASE_URL`/`JWT_SECRET`.
The hatchery detects this (`deploy.service == "wagyutank-api"`) and leaves the
service and schema alone. Migrating it to `tank@wagyu` is optional and not required.
