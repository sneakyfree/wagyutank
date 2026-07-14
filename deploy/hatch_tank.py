#!/usr/bin/env python3
"""Tank Hatchery — hatch a complete breed-marketplace tank with zero hand-wiring.

One idempotent command stands up (or converges) every piece of a tank:

  scaffold  → VPS: tank dir, tank.env, DB schema, systemd unit, nginx block
  zone      → Cloudflare zone for the domain (create if new)
  web-dns   → api.<d> A record + apex/www CNAME → Pages
  pages     → CF Pages project + custom-domain attach
  resend    → Resend domain add + DNS records + verify (outbound mail)
  mail-dns  → receive/policy DNS: MX→Stalwart, apex SPF, DMARC, autoconfig
  stalwart  → mail domain + office@<d> mailbox + catch-all (inbound mail)
  seed      → run the tank's content seeders on its DB
  frontend  → build (TANK_API) + wrangler deploy to CF Pages
  smoke     → deploy/smoke_tank.py end-to-end verification

Every phase detects-then-converges, so re-running is safe and cheap. Prove it by
re-running against an existing tank: unchanged pieces report "unchanged", missing
pieces get filled.

    ./deploy/hatch-tank.sh <tank_key> [--only p1,p2] [--skip p3] [--dry-run]
                                      [--port N] [--with-frontend]

Secrets come from the environment (deploy/.hatch-secrets.env). See
docs/TANK_HATCHERY.md for the full runbook.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
import time
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hatch_common as h  # noqa: E402

REPO = Path(__file__).resolve().parent.parent            # .../wagyutank
MAIL_HOST_DEFAULT = "mail.windymail.ai"

PHASES = ["scaffold", "zone", "web-dns", "pages", "resend", "mail-dns",
          "stalwart", "seed", "jobs", "frontend", "smoke"]


# ============================================================ config / context
class Ctx:
    def __init__(self, key: str, args):
        self.key = key
        self.args = args
        self.dry = args.dry_run
        self.cfg = self._load_cfg()
        b = self.cfg.get("brand", {})
        self.brand = b
        self.domain = b.get("domain") or f"{key}tank.com"
        self.name = b.get("name") or f"{key.title()}Tank"
        dep = self.cfg.get("deploy", {})
        self.port = args.port or dep.get("port")
        self.pages_project = dep.get("pagesProject") or f"{key}-tank"
        self.service = dep.get("service") or f"tank@{key}"
        self.legacy_service = self.service == "wagyutank-api"
        # tokens / secrets
        self.god = h.env("CF_GOD_TOKEN")
        self.dns_token = h.env("CF_DNS_TOKEN")
        self.pages_token = h.env("CF_PAGES_TOKEN")
        self.resend_key = h.env("RESEND_API_KEY")
        # the fleet-wide SSO secret every peer tank shares (cross-site login). One
        # value across the whole trust circle; the hatchery writes it into each
        # peer tank's tank.env so a clone's flywheel login works with no hand-wiring.
        self.sso_secret = h.env("SSO_SHARED_SECRET", "")
        self.mail_host = h.env("HATCH_MAIL_HOST", MAIL_HOST_DEFAULT)
        # the one founder mailbox every tank's mail consolidates into (Stalwart
        # account id). Grant reads all domains under this single Roundcube login.
        self.founder_account_id = h.env("STALWART_FOUNDER_ACCOUNT", "c3")
        self.founder_email = h.env("STALWART_FOUNDER_EMAIL",
                                   "gwhitmer@windstorminstitute.org")
        self._zone_id = None

    def _load_cfg(self) -> dict:
        p = REPO / "tanks" / self.key / "tank.json"
        if not p.exists():
            raise h.HatchError(f"tanks/{self.key}/tank.json not found — scaffold "
                               f"content from tanks/_template first (see runbook)")
        return json.loads(p.read_text())

    # (mail no longer generates a per-tank password — office@ is an alias on the
    #  shared founder mailbox, so there's nothing tank-specific to store.)

    def zone_id(self) -> str:
        if self._zone_id:
            return self._zone_id
        zid = h.cf_zone_id(self.domain, token=self.god or self.dns_token)
        if not zid:
            if self.dry:
                return ""   # dry-run: the 'zone' phase would create it — let callers narrate
            raise h.HatchError(f"no Cloudflare zone for {self.domain} — the domain must be "
                               f"registered and its nameservers pointed at Cloudflare, "
                               f"then run the 'zone' phase")
        self._zone_id = zid
        return zid


# ============================================================ phase: scaffold
def _preflight_port(ctx: Ctx):
    """Fail fast on a duplicate port. `tanks/PORTS` was an inert ledger nobody
    read; the source of truth is each tank.json `deploy.port`. Scan siblings,
    reject a collision, and auto-assign the next free port if none was set."""
    used: dict[int, str] = {}
    for p in (REPO / "tanks").glob("*/tank.json"):
        key = p.parent.name
        if key == ctx.key:
            continue
        try:
            port = (json.loads(p.read_text()).get("deploy") or {}).get("port")
        except Exception:
            continue
        if port:
            used[int(port)] = key
    if ctx.port and int(ctx.port) in used:
        raise h.HatchError(
            f"port {ctx.port} is already assigned to tank '{used[int(ctx.port)]}' — "
            f"pick a free port in tanks/{ctx.key}/tank.json deploy.port "
            f"(in use: {', '.join(f'{k}={v}' for k, v in sorted(used.items()))})")
    if not ctx.port:
        ctx.port = (max(used) + 1) if used else 8120
        h.warn(f"no port set for '{ctx.key}' — auto-assigned {ctx.port}; "
               f"lock it in tanks/{ctx.key}/tank.json deploy.port")


def phase_scaffold(ctx: Ctx):
    h.step(f"scaffold — VPS runtime for '{ctx.key}' (port {ctx.port})")
    _preflight_port(ctx)
    vps = h.VPS_SSH()
    root = h.REPO_ROOT_VPS()
    tank_dir = f"{root}/tanks/{ctx.key}"

    if ctx.dry:
        h.info(f"[dry] would ensure {tank_dir}/tank.env, schema, systemd, nginx")
        return

    # 0. the VPS repo must carry the code being hatched — a new tank's service,
    #    migrate, and seeders all run from it. Fast-forward only: never rewrites
    #    VPS-local commits, and running services aren't touched until restarted.
    rc, out, err = h.ssh_run(vps, f"cd {root} && git pull --ff-only 2>&1 | tail -1")
    (h.ok if rc == 0 else h.warn)(f"VPS repo sync: {(out or err).strip()[:90] or 'ok'}")

    # 1. ensure tank dir + tank.json present on the VPS (push config for a brand-new
    #    tank; never clobber an existing one — those are managed via normal deploys).
    rc, out, _ = h.ssh_run(vps, f"test -f {tank_dir}/tank.json && echo yes || echo no")
    if out.strip() == "no":
        h.info("tank.json absent on VPS — syncing tank config up")
        h.run(["ssh", vps, f"mkdir -p {tank_dir}/seed {tank_dir}/public"])
        local = REPO / "tanks" / ctx.key
        h.run(["scp", "-q", str(local / "tank.json"), f"{vps}:{tank_dir}/tank.json"])
        seed_dir = local / "seed"
        if seed_dir.exists() and any(seed_dir.iterdir()):
            h.run(["scp", "-q", "-r", str(seed_dir) + "/.", f"{vps}:{tank_dir}/seed/"])
        h.ok("tank config synced to VPS")
    else:
        h.ok("tank.json present on VPS")

    # 2. tank.env — the isolation boundary. CONVERGES (not write-once): managed
    #    keys are reconciled from tank.json on every run so a port/domain/SSO edit
    #    actually reaches the running backend; JWT_SECRET and any hand-added keys
    #    are preserved (JWT is never rotated — that would log everyone out).
    _ensure_tank_env(ctx, vps, tank_dir)

    # 3. DB schema (migrate builds every table). Safe to re-run.
    if not ctx.legacy_service:
        cmd = (f"cd {root}/backend && mkdir -p data && set -a && . {tank_dir}/tank.env && set +a "
               f"&& .venv/bin/python -m app.jobs.migrate")
        rc, out, err = h.ssh_run(vps, cmd, timeout=120)
        if rc == 0:
            h.ok("DB schema ensured (migrate)")
        else:
            h.warn(f"migrate rc={rc}: {(err or out).strip()[:200]}")
    else:
        h.ok("legacy tank — schema owned by wagyutank-api (skip migrate)")

    # 4. systemd unit
    if not ctx.legacy_service:
        h.ssh_run(vps, f"test -f /etc/systemd/system/tank@.service || "
                       f"(cp {root}/deploy/tank@.service /etc/systemd/system/ && systemctl daemon-reload)")
        rc, out, err = h.ssh_run(vps, f"systemctl enable --now tank@{ctx.key} 2>&1; "
                                       f"sleep 2; systemctl is-active tank@{ctx.key}")
        if "active" in out:
            h.ok(f"tank@{ctx.key} active on :{ctx.port}")
        else:
            h.warn(f"tank@{ctx.key} not active: {out.strip()[:160]}")
    else:
        rc, out, _ = h.ssh_run(vps, "systemctl is-active wagyutank-api")
        h.ok(f"legacy service wagyutank-api: {out.strip()}")

    # 5. nginx block for api.<domain>
    _ensure_nginx(ctx, vps)


# keys the hatchery OWNS and reconciles from tank.json on every run. Anything
# else in tank.env (JWT_SECRET, manual admin entries, one-off overrides) is
# preserved untouched.
_ENV_RECONCILE_CLONE = ["TANK", "PORT", "DATABASE_URL", "FRONTEND_ORIGIN",
                        "R2_BUCKET", "R2_PUBLIC_BASE",
                        "SSO_SHARED_SECRET", "SSO_PEER_API"]
_ENV_RECONCILE_LEGACY = ["TANK", "PORT", "DATABASE_URL", "FRONTEND_ORIGIN"]


def _parse_env(text: str) -> "OrderedDict[str, str]":
    d: "OrderedDict[str, str]" = OrderedDict()
    for line in text.splitlines():
        line = line.rstrip("\n")
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        d[k.strip()] = v
    return d


def _ensure_tank_env(ctx: Ctx, vps: str, tank_dir: str):
    """Reconcile tank.env: keep JWT + manual keys, refresh the managed set."""
    _, cur, _ = h.ssh_run(vps, f"cat {tank_dir}/tank.env 2>/dev/null")
    existing = _parse_env(cur or "")
    desired = OrderedDict(existing)  # preserve order + any hand-added keys

    if ctx.legacy_service:
        # WagyuTank serves off backend/.env; its tank.env exists only so
        # run-tank-job.sh targets the right DB — never a JWT/SSO/R2 override.
        managed = {"TANK": ctx.key, "PORT": str(ctx.port or 8120),
                   "DATABASE_URL": "sqlite:///./wagyutank.db",
                   "FRONTEND_ORIGIN": f"https://www.{ctx.domain}"}
        reconcile = _ENV_RECONCILE_LEGACY
    else:
        managed = {"TANK": ctx.key, "PORT": str(ctx.port),
                   "DATABASE_URL": f"sqlite:///./data/{ctx.key}.db",
                   "FRONTEND_ORIGIN": f"https://www.{ctx.domain}",
                   "R2_BUCKET": f"{ctx.key}-tank-videos",
                   "R2_PUBLIC_BASE": f"https://videos.{ctx.domain}"}
        # SSO trust circle — templated from tank.json network.peers (previously
        # hand-wired, which meant a new peer tank silently shipped with login OFF).
        peers = (ctx.cfg.get("network") or {}).get("peers") or []
        peer_domain = peers[0].get("domain") if peers else ""
        if peers and peer_domain and ctx.sso_secret:
            managed["SSO_SHARED_SECRET"] = ctx.sso_secret
            managed["SSO_PEER_API"] = f"https://api.{peer_domain}"
        elif peers and not ctx.sso_secret:
            h.warn("tank.json has network.peers but SSO_SHARED_SECRET is not in "
                   "hatch-secrets — cross-site login stays OFF until it's provided")
        reconcile = _ENV_RECONCILE_CLONE
        # JWT: generate ONCE, then preserve forever (rotating logs everyone out).
        if not existing.get("JWT_SECRET"):
            jwt = base64.b64encode(secrets.token_bytes(36)).decode().replace("+", "").replace("/", "")[:48]
            desired["JWT_SECRET"] = jwt
        # ADMIN_EMAILS: empty on first create (super_admin stays Grant via code);
        # preserved if an operator later fills it in.
        if "ADMIN_EMAILS" not in existing:
            desired["ADMIN_EMAILS"] = ""

    for k in reconcile:
        if k in managed:
            desired[k] = managed[k]   # never DELETE keys — only add/refresh

    if desired == existing:
        h.ok("tank.env converged (unchanged)")
        return
    envtxt = "".join(f"{k}={v}\n" for k, v in desired.items())
    h.ssh_run(vps, f"mkdir -p {tank_dir} && cat > {tank_dir}/tank.env <<'HATCHENV'\n{envtxt}HATCHENV")
    updated = [k for k in desired if existing.get(k) != desired.get(k)]
    h.ok(f"tank.env {'created' if not existing else 'converged'} "
         f"({len(desired)} keys; changed: {', '.join(updated) or 'none'})")


def _ensure_nginx(ctx: Ctx, vps: str):
    site = f"api.{ctx.domain}"
    avail = f"/etc/nginx/sites-available/{ctx.key}-api"
    rc, out, _ = h.ssh_run(vps, f"grep -rl 'server_name {site};' /etc/nginx/sites-available/ 2>/dev/null | head -1")
    if out.strip():
        h.ok(f"nginx block for {site} present ({out.strip()})")
        return
    block = f"""server {{
    listen 80;
    listen [::]:80;
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name {site};
    ssl_certificate /etc/ssl/certs/ssl-cert-snakeoil.pem;
    ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;
    client_max_body_size 15M;
    location / {{
        proxy_pass http://127.0.0.1:{ctx.port};
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }}
}}
"""
    h.ssh_run(vps, f"cat > {avail} <<'HATCHNGINX'\n{block}HATCHNGINX")
    h.ssh_run(vps, f"ln -sf {avail} /etc/nginx/sites-enabled/{ctx.key}-api")
    rc, out, err = h.ssh_run(vps, "nginx -t 2>&1 && systemctl reload nginx && echo reloaded")
    if "reloaded" in out:
        h.ok(f"nginx block for {site} created + reloaded")
    else:
        h.warn(f"nginx not reloaded: {(err or out).strip()[:200]}")


# ============================================================ phase: zone
def phase_zone(ctx: Ctx):
    h.step(f"zone — Cloudflare zone for {ctx.domain}")
    tok = ctx.god or ctx.dns_token
    zid = h.cf_zone_id(ctx.domain, token=tok)
    if zid:
        h.ok(f"zone exists ({zid})")
        ctx._zone_id = zid
        return
    if ctx.dry:
        h.info(f"[dry] would create zone {ctx.domain}")
        return
    if not ctx.god:
        raise h.HatchError("zone missing and CF_GOD_TOKEN (zone.create) not set")
    d = h.cf_api("POST", "/zones", token=ctx.god,
                 body={"name": ctx.domain, "account": {"id": h.CF_ACCOUNT()}, "type": "full"})
    if not d.get("success"):
        raise h.HatchError(f"zone create failed: {d.get('errors')}")
    zid = d["result"]["id"]
    ns = d["result"].get("name_servers", [])
    ctx._zone_id = zid
    h.ok(f"zone created ({zid})")
    h.warn(f"point the registrar's nameservers at: {', '.join(ns)} "
           f"(GoDaddy: PATCH /v1/domains/{ctx.domain} nameServers) — DNS won't "
           f"resolve until NS delegation propagates")


# ============================================================ phase: web-dns
def phase_web_dns(ctx: Ctx):
    h.step(f"web-dns — api/apex/www for {ctx.domain}")
    zid = ctx.zone_id()
    if ctx.dry and not zid:
        h.info("[dry] would converge api A + apex/www CNAME once the zone exists")
        return
    tok = ctx.dns_token
    recs = h.cf_dns_list(zid, token=tok)
    pages = f"{ctx.pages_project}.pages.dev"
    wanted = [
        ("A", f"api.{ctx.domain}", h.VPS_IP(), True, None),
        ("CNAME", ctx.domain, pages, True, None),
        ("CNAME", f"www.{ctx.domain}", pages, True, None),
    ]
    for typ, name, content, proxied, prio in wanted:
        r = h.cf_dns_ensure(zid, token=tok, type=typ, name=name, content=content,
                            proxied=proxied, priority=prio, existing=recs, dry=ctx.dry)
        _report(typ, name, content, r)


# ============================================================ phase: pages
def phase_pages(ctx: Ctx):
    h.step(f"pages — CF Pages project '{ctx.pages_project}' + custom domains")
    acct = h.CF_ACCOUNT()
    tok = ctx.pages_token or ctx.god
    d = h.cf_api("GET", f"/accounts/{acct}/pages/projects/{ctx.pages_project}", token=tok)
    if d.get("success"):
        existing = set(d["result"].get("domains", []))
        h.ok(f"project exists (domains: {', '.join(sorted(existing)) or 'none'})")
    else:
        if ctx.dry:
            h.info(f"[dry] would create Pages project {ctx.pages_project}")
            existing = set()
        else:
            c = h.cf_api("POST", f"/accounts/{acct}/pages/projects", token=tok,
                         body={"name": ctx.pages_project, "production_branch": "main"})
            if not c.get("success"):
                raise h.HatchError(f"Pages project create failed: {c.get('errors')}")
            h.ok(f"project created ({ctx.pages_project})")
            existing = set()
    for dom in (ctx.domain, f"www.{ctx.domain}"):
        if dom in existing:
            _report("domain", dom, "attached", "unchanged")
            continue
        if ctx.dry:
            _report("domain", dom, "attach", "would-create")
            continue
        a = h.cf_api("POST", f"/accounts/{acct}/pages/projects/{ctx.pages_project}/domains",
                     token=tok, body={"name": dom})
        _report("domain", dom, "attach", "created" if a.get("success") else f"ERR {a.get('errors')}")


# ============================================================ phase: resend
def phase_resend(ctx: Ctx):
    h.step(f"resend — outbound sender for {ctx.domain}")
    key = ctx.resend_key
    if not key:
        raise h.HatchError("RESEND_API_KEY not set")
    dom = h.resend_find_domain(ctx.domain, key=key)
    if not dom:
        if ctx.dry:
            h.info(f"[dry] would add Resend domain {ctx.domain}")
            return
        c = h.resend_api("POST", "/domains", key=key,
                         body={"name": ctx.domain, "region": "us-east-1"})
        if not c.get("id"):
            raise h.HatchError(f"Resend domain add failed: {c}")
        dom = c
        h.ok(f"Resend domain added ({dom['id']})")
    else:
        h.ok(f"Resend domain exists ({dom['id']}, status={dom.get('status')})")

    # fetch the authoritative record set + create them in CF
    full = h.resend_api("GET", f"/domains/{dom['id']}", key=key)
    zid = ctx.zone_id()
    recs = h.cf_dns_list(zid, token=ctx.dns_token)
    for rec in full.get("records", []) or []:
        typ = rec.get("type", "").upper()
        name = rec.get("name", "").rstrip(".")
        val = rec.get("value", "").strip()
        if not (typ and name and val):
            continue
        # Resend returns record names relative to the domain ("send",
        # "resend._domainkey") — Cloudflare needs the FQDN to match/create cleanly.
        if name in ("@", ctx.domain):
            name = ctx.domain
        elif not name.endswith(ctx.domain):
            name = f"{name}.{ctx.domain}"
        prio = rec.get("priority")
        prio = int(prio) if str(prio).isdigit() else (10 if typ == "MX" else None)
        r = h.cf_dns_ensure(zid, token=ctx.dns_token, type=typ, name=name, content=val,
                            proxied=False, priority=prio, existing=recs, dry=ctx.dry)
        _report(typ, name, val[:32], r)

    if full.get("status") == "verified":
        h.ok("Resend domain already verified")
        return
    if ctx.dry:
        h.info("[dry] would trigger verify + poll")
        return
    h.resend_api("POST", f"/domains/{dom['id']}/verify", key=key)
    for i in range(12):
        time.sleep(8)
        st = h.resend_api("GET", f"/domains/{dom['id']}", key=key).get("status")
        if st == "verified":
            h.ok("Resend domain verified")
            return
        h.info(f"verify pending ({st})… {(i+1)*8}s")
    h.warn("Resend not verified yet — DNS may still be propagating; re-run later")


# ============================================================ phase: mail-dns
def phase_mail_dns(ctx: Ctx):
    h.step(f"mail-dns — receive + policy records for {ctx.domain}")
    zid = ctx.zone_id()
    if ctx.dry and not zid:
        h.info("[dry] would converge MX/SPF/DMARC/autoconfig once the zone exists")
        return
    tok = ctx.dns_token
    recs = h.cf_dns_list(zid, token=tok)
    mail = ctx.mail_host
    wanted = [
        # inbound: mail to office@<d> and catch-all lands on the shared Stalwart
        ("MX", ctx.domain, mail, False, 10),
        # apex SPF: authorises our MX hosts + Resend/SES for the bare domain
        ("TXT", ctx.domain, "v=spf1 mx include:amazonses.com -all", False, None),
        # DMARC policy (monitor mode; reports to postmaster)
        ("TXT", f"_dmarc.{ctx.domain}",
         f"v=DMARC1; p=none; rua=mailto:postmaster@{ctx.domain}", False, None),
        # mail-client autodiscovery (nice-to-have, matches the wagyu reference)
        ("CNAME", f"autoconfig.{ctx.domain}", mail, False, None),
        ("CNAME", f"autodiscover.{ctx.domain}", mail, False, None),
    ]
    for typ, name, content, proxied, prio in wanted:
        r = h.cf_dns_ensure(zid, token=tok, type=typ, name=name, content=content,
                            proxied=proxied, priority=prio, existing=recs, dry=ctx.dry)
        _report(typ, name, content[:40], r)


# ============================================================ phase: stalwart
def phase_stalwart(ctx: Ctx):
    """Wire the tank's mail INTO the one founder mailbox — NOT a separate login.

    Grant runs every domain under a single Roundcube login (the `gwhitmer`
    principal), each address just an alias landing in that one inbox. So a tank
    gets: (1) its domain in Stalwart, (2) office@<domain> as an alias on the
    founder principal (so it lands in the shared inbox AND can be sent-as), and
    (3) a catch-all → office@<domain> so info@/sales@/anything@ lands there too.
    No new account, no extra password."""
    fid = ctx.founder_account_id
    h.step(f"stalwart — office@{ctx.domain} → founder inbox (alias, not a new login)")
    if ctx.dry:
        h.info(f"[dry] would ensure Stalwart domain + office@{ctx.domain} alias on "
               f"founder account {fid} + catch-all")
        return
    # 1. domain
    dom_id = _stalwart_domain_id(ctx.domain)
    if dom_id:
        h.ok(f"Stalwart domain exists (id {dom_id})")
    else:
        rc, out, err = h.stalwart(["create", "Domain",
                                   "--field", f"name={ctx.domain}",
                                   "--field", f"description={ctx.name}"])
        if rc != 0:
            raise h.HatchError(f"Stalwart domain create failed: {(err or out)[:200]}")
        dom_id = _stalwart_domain_id(ctx.domain)
        h.ok(f"Stalwart domain created (id {dom_id})")

    # 1a. a leftover STANDALONE office@ account from the old pattern would collide
    #     with the alias — retire it (its mail was never read separately).
    stray = _stalwart_account_id(f"office@{ctx.domain}")
    if stray:
        h.stalwart(["delete", "Account", "--ids", stray])
        h.warn(f"removed stray standalone office@ account (id {stray}) — "
               f"consolidating into the founder mailbox")

    # 2. office@<domain> as an alias on the founder principal
    r = _ensure_founder_alias(fid, "office", dom_id)
    email = f"office@{ctx.domain}"
    if r == "exists":
        h.ok(f"{email} already an alias on founder account {fid}")
    elif r == "added":
        h.ok(f"{email} added as an alias on founder account {fid} "
             f"(lands in the one shared inbox; sendable-as)")
    else:
        h.warn(f"could not add founder alias for {email}: {r}")

    # 3. catch-all → office@<domain>
    rc, out, _ = h.stalwart(["get", "Domain", dom_id])
    if f"Catch-All Address: {email}" in out:
        h.ok(f"catch-all → {email} already set")
    else:
        rc, out, err = h.stalwart(["update", "Domain", dom_id,
                                   "--field", f"catchAllAddress={email}"])
        if rc != 0:
            h.warn(f"catch-all update rc={rc}: {(err or out)[:160]}")
        else:
            h.ok(f"catch-all → {email} set (info@/sales@/anything@ lands here)")


def _ensure_founder_alias(founder_id: str, localpart: str, domain_id: str) -> str:
    """Append {localpart}@<domain> to the founder principal's alias map, preserving
    every existing alias. Returns 'exists' | 'added' | error string."""
    rc, out, err = h.stalwart(["get", "Account", founder_id, "--json"])
    if rc != 0:
        return f"get founder failed: {(err or out)[:120]}"
    try:
        acct = json.loads(out)
    except json.JSONDecodeError:
        return "founder account JSON parse failed"
    aliases = acct.get("aliases") or {}
    if any(v.get("name") == localpart and v.get("domainId") == domain_id
           for v in aliases.values()):
        return "exists"
    next_key = str(max((int(k) for k in aliases.keys()), default=-1) + 1)
    aliases[next_key] = {"enabled": True, "name": localpart,
                         "domainId": domain_id, "description": None}
    payload = json.dumps(aliases, separators=(",", ":"))
    rc, out, err = h.stalwart(["update", "Account", founder_id,
                               "--field", f"aliases={payload}"])
    if rc != 0:
        return f"update failed: {(err or out)[:120]}"
    return "added"


def _stalwart_domain_id(domain: str) -> str | None:
    out = h.stalwart_query("Domain")
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 2 and p[1] == domain:
            return p[0]
    return None


def _stalwart_account_id(email: str) -> str | None:
    out = h.stalwart_query("Account")
    for line in out.splitlines():
        p = line.split()
        if len(p) >= 2 and p[1] == email:
            return p[0]
    return None


# ============================================================ phase: seed
def phase_seed(ctx: Ctx):
    h.step(f"seed — load {ctx.key} content into its DB")
    if ctx.dry:
        h.info("[dry] would run seeders under the tank env")
        return
    vps = h.VPS_SSH()
    root = h.REPO_ROOT_VPS()
    tank_dir = f"{root}/tanks/{ctx.key}"
    modules = ["app.seed.seed"]  # base spine: foundation/facilities/history/faq
    # optional content seeders — only those the tank's features enable
    feats = ctx.cfg.get("features", {})
    # A tank that sells live cattle or beef needs the postal gazetteer for the
    # "near me" search (breed-agnostic; skipped on pure-genetics tanks).
    prods = ctx.cfg.get("products", [])
    has_geo = any((p.get("family") in ("live", "beef")) for p in prods)
    opt = {
        "app.jobs.seed_reference_prices": feats.get("price_index"),
        "app.jobs.seed_sale_events": feats.get("sale_reports"),
        "app.jobs.seed_upcoming_sales": feats.get("sale_reports"),
        "app.jobs.seed_notable_sales": feats.get("sale_reports"),
        "app.jobs.seed_comments": feats.get("foundation"),
        "app.jobs.seed_ads": feats.get("ads"),
        "app.jobs.seed_market": feats.get("market_data"),
        "app.jobs.seed_geo": has_geo,
    }
    modules += [m for m, on in opt.items() if on]
    for mod in modules:
        cmd = (f"cd {root}/backend && set -a && . {tank_dir}/tank.env && set +a "
               f"&& .venv/bin/python -m {mod}")
        rc, out, err = h.ssh_run(vps, cmd, timeout=300)
        tail = (out.strip().splitlines() or [""])[-1][:80]
        (h.ok if rc == 0 else h.warn)(f"{mod}: {'ok' if rc==0 else 'rc='+str(rc)} {tail}")


# ============================================================ phase: jobs
def phase_jobs(ctx: Ctx):
    """Converge the tank's RECURRING-COMPUTE layer on both machines.

    Compute doctrine (see TEMPLATE_SPEC §6b): the VPS is flat-rate 24/7 CPU we
    already pay for — every job that CAN run there DOES (API serving, RSS/httpx
    news crawls, LLM content jobs via Windy Mind, watchdog, digest). Veron 1
    (RTX 5090 + Core Ultra 9 + residential T1) runs ONLY what the VPS can't:
    JS-rendered Playwright crawling and yt-dlp video harvest (datacenter IPs get
    blocked/throttled) — and ships every result home to the VPS, which stays the
    system of record. Windy 0 is a dev/build box: no recurring tank jobs.

    Schedules are declared in tank.json `jobs` (vps[] / veron[]) and materialized
    as a marker-delimited cron block per tank; stray hand-typed lines for the
    same tank are adopted into the block. Everything else in the crontab is
    preserved byte-for-byte (backup at ~/.crontab.pre-hatch.bak)."""
    h.step(f"jobs — recurring compute for '{ctx.key}' (VPS + Veron)")
    jobs = ctx.cfg.get("jobs") or {}
    root = h.REPO_ROOT_VPS()

    # ---- VPS lane -------------------------------------------------------
    vps_jobs = jobs.get("vps") or []
    if ctx.legacy_service and not vps_jobs:
        _report_legacy_vps_jobs(ctx)
    elif vps_jobs:
        lines = []
        for j in vps_jobs:
            sched, mod = j.get("schedule", ""), j.get("module", "")
            if len(sched.split()) != 5 or not mod:
                h.warn(f"skipping malformed vps job: {j}")
                continue
            log = f"/root/tank-{ctx.key}-{mod.rsplit('.', 1)[-1]}.log"
            lines.append(f"{sched} {root}/deploy/run-tank-job.sh {ctx.key} {mod} >> {log} 2>&1")
        res, adopted = h.cron_converge(
            h.VPS_SSH(), ctx.key, lines,
            adopt_patterns=[f"run-tank-job.sh {ctx.key} "], dry=ctx.dry)
        msg = f"VPS cron block ({len(lines)} jobs) [{res}]"
        if adopted:
            msg += f" — adopted {adopted} hand-typed line(s)"
        (h.ok if res == "unchanged" else h.info)(msg)
    else:
        h.info("no VPS jobs declared")

    # ---- Veron lane ------------------------------------------------------
    veron_jobs = jobs.get("veron") or []
    if not veron_jobs:
        h.info("no Veron jobs declared")
        return
    veron = h.env("HATCH_CRAWL_SSH", "wg-veron")
    rc, out, _ = h.ssh_run(veron, "test -d ~/wagyutank/deploy && echo yes || echo no",
                           timeout=40)
    if out.strip() != "yes":
        h.warn(f"~/wagyutank missing on {veron} — clone it there first "
               f"(git clone https://github.com/sneakyfree/wagyutank.git ~/wagyutank); "
               f"skipping Veron jobs")
        return
    # the workers the scripts depend on
    rc, out, _ = h.ssh_run(veron, "which node >/dev/null && echo node-ok; "
                                   "PATH=$HOME/.local/bin:$PATH which yt-dlp >/dev/null && echo ytdlp-ok",
                           timeout=40)
    for tool, tag in (("node", "node-ok"), ("yt-dlp", "ytdlp-ok")):
        if tag not in out:
            h.warn(f"{tool} not found on {veron} — its jobs will no-op until installed")
    lines = []
    for j in veron_jobs:
        sched, script = j.get("schedule", ""), j.get("script", "")
        if len(sched.split()) != 5 or not script:
            h.warn(f"skipping malformed veron job: {j}")
            continue
        log = f"$HOME/.{script.replace('tank-', '').replace('.sh', '')}-{ctx.key}.log"
        lines.append(f"{sched} $HOME/wagyutank/deploy/{script} {ctx.key} >> {log} 2>&1")
    res, adopted = h.cron_converge(
        veron, ctx.key, lines,
        adopt_patterns=[f"tank-crawl.sh {ctx.key}", f"tank-harvest.sh {ctx.key}"],
        dry=ctx.dry)
    msg = f"Veron cron block ({len(lines)} jobs) [{res}]"
    if adopted:
        msg += f" — adopted {adopted} hand-typed line(s)"
    (h.ok if res == "unchanged" else h.info)(msg)


def _report_legacy_vps_jobs(ctx: Ctx):
    """WagyuTank's VPS jobs predate the hatchery (systemd timers + a root cron
    watchdog). Report their health; don't manage them."""
    note = ctx.cfg.get("jobs", {}).get("vps_note")
    if note:
        h.info(note[:110] + ("…" if len(note) > 110 else ""))
    rc, out, _ = h.ssh_run(
        h.VPS_SSH(),
        "systemctl list-timers --all --no-pager 2>/dev/null | grep -cE 'wagyutank-(news|aggregate|digest)'; "
        "crontab -l 2>/dev/null | grep -c 'app.jobs.watchdog'")
    counts = out.split()
    timers = counts[0] if counts else "?"
    wd = counts[1] if len(counts) > 1 else "?"
    h.ok(f"legacy VPS jobs detected: {timers}/3 systemd timers + watchdog cron×{wd} (report-only)")


# ============================================================ phase: frontend
def phase_frontend(ctx: Ctx):
    h.step(f"frontend — build + deploy {ctx.pages_project}")
    site = REPO.parent / "wagyutank-site"
    if not site.exists():
        h.warn(f"site repo not found at {site} — skipping frontend build")
        return
    if ctx.dry:
        h.info(f"[dry] would: TANK_API=https://api.{ctx.domain} npm run build && wrangler deploy")
        return
    tank_json = REPO / "tanks" / ctx.key / "tank.json"
    h.info(f"TANK_API=https://api.{ctx.domain} npm run build … (TANK_JSON bootstrap fallback set)")
    p = h.run(["bash", "-lc",
               f'cd {site!s} && TANK_API=https://api.{ctx.domain} TANK_JSON="{tank_json}" npm run build'],
              timeout=900)
    if p.returncode != 0:
        raise h.HatchError(f"frontend build failed: {p.stderr[-300:]}")
    h.ok("built")
    # Per-breed designer art (tanks/<key>/public/*) overrides the generated
    # brand assets in out/ — og-image, favicon, foundation photos, etc.
    art = REPO / "tanks" / ctx.key / "public"
    if art.exists() and any(art.iterdir()):
        p = h.run(["bash", "-lc", f'cp -r "{art}"/. "{site!s}/out/"'])
        (h.ok if p.returncode == 0 else h.warn)(
            f"per-breed art copied from tanks/{ctx.key}/public/ into the build")
    tok = ctx.pages_token or ctx.god
    p = h.run(["bash", "-lc",
               f"cd {site!s} && CLOUDFLARE_API_TOKEN={tok} CLOUDFLARE_ACCOUNT_ID={h.CF_ACCOUNT()} "
               f"npx wrangler pages deploy out --project-name={ctx.pages_project}"], timeout=600)
    (h.ok if p.returncode == 0 else h.warn)(f"wrangler deploy rc={p.returncode}")
    if p.returncode != 0:
        h.warn(p.stderr[-300:])


# ============================================================ phase: smoke
def phase_smoke(ctx: Ctx):
    h.step(f"smoke — end-to-end verification of {ctx.domain}")
    if ctx.dry:
        h.info("[dry] would run deploy/smoke_tank.py")
        return
    p = h.run([sys.executable, str(REPO / "deploy" / "smoke_tank.py"), ctx.key],
              timeout=240)
    print(p.stdout, end="")
    if p.stderr.strip():
        print(p.stderr, end="")
    if p.returncode != 0:
        raise h.HatchError(f"smoke suite reported failures (rc={p.returncode})")


# ============================================================ helpers
def _report(typ: str, name: str, content: str, result: str):
    icon = {"created": "＋", "updated": "↻", "unchanged": "=",
            "would-create": "＋?", "would-update": "↻?"}.get(result, "•")
    line = f"  {icon} {typ:6} {name:42} {content}"
    if result.startswith("ERR"):
        h.fail(f"{typ} {name}: {result}")
    else:
        print(line + h._c("dim", f"  [{result}]"), flush=True)


PHASE_FN = {
    "scaffold": phase_scaffold, "zone": phase_zone, "web-dns": phase_web_dns,
    "pages": phase_pages, "resend": phase_resend, "mail-dns": phase_mail_dns,
    "stalwart": phase_stalwart, "seed": phase_seed, "jobs": phase_jobs,
    "frontend": phase_frontend, "smoke": phase_smoke,
}


def main():
    ap = argparse.ArgumentParser(description="Hatch or converge a breed tank.")
    ap.add_argument("key", help="tank key (e.g. wagyu, murraygrey, highland)")
    ap.add_argument("--only", help="comma-separated phases to run")
    ap.add_argument("--skip", help="comma-separated phases to skip")
    ap.add_argument("--port", type=int, help="API port (new tanks only)")
    ap.add_argument("--with-frontend", action="store_true",
                    help="include the frontend build+deploy phase (off by default)")
    ap.add_argument("--dry-run", action="store_true", help="detect only, change nothing")
    args = ap.parse_args()

    try:
        ctx = Ctx(args.key, args)
    except h.HatchError as e:
        h.fail(str(e))
        sys.exit(2)

    phases = PHASES[:]
    if not args.with_frontend and not (args.only and "frontend" in args.only):
        phases = [p for p in phases if p != "frontend"]
    if args.only:
        want = [p.strip() for p in args.only.split(",")]
        phases = [p for p in PHASES if p in want]
    if args.skip:
        skip = {p.strip() for p in args.skip.split(",")}
        phases = [p for p in phases if p not in skip]

    print(h._c("step", f"\n🐣 Hatchery — {ctx.name} ({ctx.domain})  "
                        f"[{'DRY-RUN' if ctx.dry else 'LIVE'}]  phases: {', '.join(phases)}"))
    failures = []
    for name in phases:
        try:
            PHASE_FN[name](ctx)
        except h.HatchError as e:
            h.fail(f"{name}: {e}")
            failures.append(name)
        except Exception as e:  # noqa: BLE001 — surface, keep going
            h.fail(f"{name}: unexpected {type(e).__name__}: {e}")
            failures.append(name)

    print()
    if failures:
        h.fail(f"hatch finished with issues in: {', '.join(failures)}")
        sys.exit(1)
    h.ok(f"hatch complete for {ctx.name} — all phases converged")


if __name__ == "__main__":
    main()
