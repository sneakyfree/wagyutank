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
| `stalwart` | mail **domain** + `office@<d>` **mailbox** (password saved to `tanks/<key>/.mail-credentials`) + domain **catch-all** → office | `query Domain` / `query Account` |
| `seed` | runs the tank's content seeders on its DB (feature-gated) | seeders are idempotent-replace |
| `frontend` | `TANK_API=… npm run build` + `wrangler pages deploy` (off by default — `--with-frontend`) | — |
| `smoke` | `deploy/smoke_tank.py` end-to-end verification | — |

### Why send **and** receive both matter

Resend gives a domain **outbound** (DKIM/SPF via `send.<d>` + `resend._domainkey`).
That alone does **not** let `office@<domain>` receive anything. The `mail-dns` +
`stalwart` phases add the **inbound** half — MX at the apex pointing to the shared
Stalwart, the mailbox itself, and a catch-all so `info@`/`grant@`/anything@ lands
in one place. This is the email doctrine: `office@<domain>` = the property's
machine channel, FROM and TO.

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
5. `office@<domain>` logs in over IMAP (the mailbox exists)
6. an email **from** `office@<domain>` **lands in** that same inbox with **From =
   office@<domain>** — send + receive + From, proven in one loop
7. a listing can actually be created via the API (then cleaned up)

`--no-mutate` skips the listing-create write. Checks that can't run (e.g. no saved
mailbox password) are reported `SKIP`, not `FAIL`. The mailbox password for the
loopback/IMAP checks is read from `tanks/<key>/.mail-credentials` (written by the
`stalwart` phase on first creation).

---

## Idempotency & re-runs

- **Proven** against `murraygrey`: a second full run reported `unchanged` on every
  DNS record, Pages domain, Resend record, and Stalwart object, and `exists` on the
  mailbox — zero mutations.
- The `stalwart` phase never rewrites an existing mailbox password (it can't read
  it back), so re-running won't lock you out. If you lost the password, delete the
  account in Stalwart and re-run to mint a fresh one.
- DNS convergence matches on `(type, name)` (+ SPF/DMARC/DKIM category for TXT), so
  it updates the intended record and never clobbers a sibling.

---

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
