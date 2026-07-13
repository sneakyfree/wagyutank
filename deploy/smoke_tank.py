#!/usr/bin/env python3
"""Smoke suite for a hatched tank — proves the whole stack is actually wired.

    ./deploy/smoke_tank.py <tank_key> [--no-mutate]

Verifies, end to end:
  1. apex + www serve HTTP 200
  2. the API is up and reports the right brand (name + colours) from /api/config
  3. the site HTML carries the brand name
  4. seed data is loaded (foundation animals present)
  5. office@<domain> can log in over IMAP (inbound mailbox exists)
  6. an outbound email from office@<domain> lands in that same inbox with the
     From address = office@<domain>  (send + receive + From, in one loop)
  7. a listing can actually be created via the API (then cleaned up)

Exit code 0 = all required checks passed. Checks that can't run (e.g. no saved
mailbox password) are reported as SKIP, not failure. HTTP goes through curl
(Cloudflare 403s python-urllib); IMAP/SMTP talk straight to the mail host.
"""
from __future__ import annotations

import argparse
import imaplib
import json
import os
import secrets
import ssl
import subprocess
import sys
import time
from email.parser import BytesParser
from email.policy import default as email_default
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

PASS, FAILED, SKIP = "PASS", "FAIL", "SKIP"
_results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = ""):
    _results.append((name, status, detail))
    icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "–"}[status]
    color = {"PASS": "\033[1;32m", "FAIL": "\033[1;31m", "SKIP": "\033[1;33m"}[status]
    end = "\033[0m" if sys.stdout.isatty() else ""
    c = color if sys.stdout.isatty() else ""
    print(f"  {c}{icon} {status}{end}  {name}" + (f" — {detail}" if detail else ""), flush=True)


# ------------------------------------------------------------------ http (curl)
def http(url: str, *, method: str = "GET", headers: dict | None = None,
         body: str | None = None, timeout: int = 25) -> tuple[int, str]:
    cmd = ["curl", "-s", "-A", UA, "-m", str(timeout), "-X", method,
           "-w", "\n%{http_code}", url]
    for k, v in (headers or {}).items():
        cmd += ["-H", f"{k}: {v}"]
    if body is not None:
        cmd += ["--data", body]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    out = p.stdout
    nl = out.rfind("\n")
    code = out[nl + 1:].strip() if nl >= 0 else ""
    return (int(code) if code.isdigit() else 0), (out[:nl] if nl >= 0 else out)


def ssh(host: str, cmd: str, timeout: int = 40) -> tuple[int, str]:
    p = subprocess.run(["ssh", "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=no",
                        host, cmd], capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout


# ------------------------------------------------------------------ the checks
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key")
    ap.add_argument("--no-mutate", action="store_true",
                    help="skip the listing-create check (no writes to prod)")
    args = ap.parse_args()

    cfg = json.loads((REPO / "tanks" / args.key / "tank.json").read_text())
    brand = cfg.get("brand", {})
    domain = brand["domain"]
    name = brand.get("name", "")
    gold = (brand.get("colors") or {}).get("gold", "")
    office = f"office@{domain}"
    mail_host = os.environ.get("HATCH_MAIL_HOST", "mail.windymail.ai")
    vps = os.environ.get("HATCH_VPS_SSH", "vps")

    print(f"\n🔎 Smoke — {name} ({domain})\n")

    # 1. apex + www 200
    for host in (domain, f"www.{domain}"):
        code, _ = http(f"https://{host}/")
        record(f"{host} serves 200", PASS if code == 200 else FAILED, f"HTTP {code}")

    # 2. API up + brand correct
    api = f"https://api.{domain}"
    code, txt = http(f"{api}/api/config")
    conf = {}
    if code == 200:
        try:
            conf = json.loads(txt)
        except json.JSONDecodeError:
            pass
    cbrand = conf.get("brand", {}) if conf else {}
    record("API /api/config up", PASS if code == 200 and cbrand else FAILED, f"HTTP {code}")
    record("brand name correct in API",
           PASS if cbrand.get("name") == name else FAILED,
           f"{cbrand.get('name')!r} == {name!r}")
    cgold = (cbrand.get("colors") or {}).get("gold", "")
    record("brand colour correct in API",
           PASS if cgold and cgold == gold else (FAILED if cgold else SKIP),
           f"{cgold!r} == {gold!r}")
    record("contactEmail = office@<domain>",
           PASS if cbrand.get("contactEmail") == office else FAILED,
           f"{cbrand.get('contactEmail')!r}")

    # 3. brand name in site HTML
    code, html = http(f"https://{domain}/")
    token = name.replace("Tank", "")  # e.g. "Murray Grey" appears even if wordmark split
    present = (name in html) or (token and token in html)
    record("brand name in site HTML", PASS if code == 200 and present else FAILED,
           f"HTTP {code}, '{name}' present={present}")

    # 4. seed data loaded
    code, txt = http(f"{api}/api/animals/foundation")
    n = 0
    if code == 200:
        try:
            n = len(json.loads(txt))
        except json.JSONDecodeError:
            pass
    record("seed data loaded (foundation animals)",
           PASS if n > 0 else FAILED, f"{n} animals")

    # 5 + 6. founder-mailbox consolidation + send/receive loop.
    #   office@<domain> is an alias on the ONE founder mailbox (not a separate
    #   login), so we log in as the founder and prove office@<domain> mail lands
    #   in that shared inbox with the right From address.
    founder = os.environ.get("STALWART_FOUNDER_EMAIL", "gwhitmer@windstorminstitute.org")
    fpw = os.environ.get("STALWART_FOUNDER_PASSWORD", "")
    if not fpw:
        record("founder mailbox login", SKIP, "STALWART_FOUNDER_PASSWORD not set")
        record("office@ mail lands in founder inbox + From correct", SKIP, "needs founder password")
    else:
        ok_login, imap, detail = _imap_login(mail_host, founder, fpw)
        record("founder mailbox login", PASS if ok_login else FAILED,
               f"{founder}" if ok_login else detail)
        if ok_login:
            _mail_loopback(imap, office, domain)
            try:
                imap.logout()
            except Exception:
                pass

    # 6b. recurring jobs wired on the right machines (declared in tank.json)
    _jobs_wired(cfg, args.key, vps)

    # 7. listing create (mutating — cleaned up)
    if args.no_mutate:
        record("listing create works", SKIP, "--no-mutate")
    else:
        _listing_create(api, domain, cfg, vps, args.key)

    # summary
    fails = [r for r in _results if r[1] == FAILED]
    passes = [r for r in _results if r[1] == PASS]
    skips = [r for r in _results if r[1] == SKIP]
    print(f"\n  {len(passes)} passed · {len(fails)} failed · {len(skips)} skipped")
    if fails:
        print("  FAILED: " + ", ".join(r[0] for r in fails))
    sys.exit(1 if fails else 0)


def _jobs_wired(cfg: dict, key: str, vps: str):
    """Verify the recurring-compute layer landed where tank.json declares it:
    VPS lane (cron block, or legacy systemd timers for wagyu) + Veron lane
    (weekly crawl/harvest cron block on the residential box)."""
    jobs = cfg.get("jobs") or {}
    marker = f"# >>> tank:{key} "
    # VPS lane
    if jobs.get("vps"):
        rc, out = ssh(vps, f"crontab -l 2>/dev/null | grep -cF '{marker}' ; "
                           f"crontab -l 2>/dev/null | grep -c 'run-tank-job.sh {key} '")
        nums = out.split()
        blk = int(nums[0]) if nums and nums[0].isdigit() else 0
        lines = int(nums[1]) if len(nums) > 1 and nums[1].isdigit() else 0
        want = len(jobs["vps"])
        record("VPS jobs cron block present",
               PASS if blk >= 1 and lines >= want else FAILED,
               f"block={bool(blk)}, {lines}/{want} job lines")
    elif jobs.get("vps_note"):
        rc, out = ssh(vps, "systemctl list-timers --all --no-pager 2>/dev/null "
                           "| grep -cE 'wagyutank-(news|aggregate|digest)'")
        n = int(out.strip() or 0) if out.strip().isdigit() else 0
        record("VPS legacy timers active", PASS if n >= 3 else FAILED, f"{n}/3 timers")
    # Veron lane
    if jobs.get("veron"):
        veron = os.environ.get("HATCH_CRAWL_SSH", "wg-veron")
        rc, out = ssh(veron, f"crontab -l 2>/dev/null | grep -cF '{marker}'", timeout=45)
        n = int(out.strip() or 0) if out.strip().isdigit() else 0
        record("Veron crawl/harvest cron block present",
               PASS if n >= 1 else FAILED,
               f"managed block on {veron}" if n else f"no block on {veron}")


def _imap_login(host: str, email: str, pw: str):
    # The shared Stalwart presents a self-signed cert on 993 (mail clients use
    # "manual setup" for the same reason) — this is our own infra, so connect
    # without chain verification.
    try:
        ctx = ssl._create_unverified_context()  # noqa: SLF001
        m = imaplib.IMAP4_SSL(host, 993, ssl_context=ctx, timeout=25)
        m.login(email, pw)
        return True, m, email
    except Exception as e:  # noqa: BLE001
        return False, None, f"{type(e).__name__}: {e}"


def _mail_loopback(imap: imaplib.IMAP4_SSL, office: str, domain: str):
    """Send office@ → office@ via Resend, then confirm it arrives with From=office@."""
    key = os.environ.get("RESEND_API_KEY", "")
    if not key:
        record("outbound send lands + From correct", SKIP, "RESEND_API_KEY not set")
        return
    nonce = secrets.token_hex(6)
    subject = f"hatch-smoke {nonce}"
    payload = json.dumps({"from": f"{office.split('@')[0]} <{office}>", "to": [office],
                          "subject": subject, "text": f"smoke {nonce}"})
    code, out = http("https://api.resend.com/emails", method="POST",
                     headers={"Authorization": f"Bearer {key}",
                              "Content-Type": "application/json"}, body=payload)
    accepted = code < 300
    if not accepted:
        record("outbound send accepted (Resend)", FAILED, f"HTTP {code} {out[:80]}")
        return
    record("outbound send accepted (Resend)", PASS, f"id sent")
    # poll for the nonce — INBOX first, then every folder (the founder mailbox
    # has sieve rules that file each site's mail into Sites/<domain>).
    def _folders() -> list[str]:
        try:
            typ, lst = imap.list()
            names = []
            for f in lst or []:
                name = f.decode().split(' "/" ')[-1].strip('"')
                if name and "\\Noselect" not in f.decode():
                    names.append(name)
            # INBOX first, then Sites/*, then the rest
            return sorted(set(names), key=lambda n: (n != "INBOX", not n.startswith("Sites"), n))
        except Exception:  # noqa: BLE001
            return ["INBOX"]

    found_from = None
    where = None
    for _ in range(15):
        time.sleep(4)
        for fld in _folders():
            try:
                typ, _sel = imap.select(f'"{fld}"', readonly=True)
                if typ != "OK":
                    continue
                typ, data = imap.search(None, "SUBJECT", f'"{subject}"')
                ids = data[0].split() if data and data[0] else []
                if ids:
                    typ, msg = imap.fetch(ids[-1], "(RFC822)")
                    parsed = BytesParser(policy=email_default).parsebytes(msg[0][1])
                    found_from = str(parsed.get("From", ""))
                    where = fld
                    break
            except Exception:  # noqa: BLE001
                continue
        if found_from:
            break
    if not found_from:
        record("office@ mail lands in founder inbox", FAILED,
               "message not received within ~60s (searched all folders)")
        return
    record("office@ mail lands in founder inbox", PASS,
           f"received in {where or 'shared inbox'}")
    from_ok = office in found_from
    record("From address = office@<domain>", PASS if from_ok else FAILED,
           f"From: {found_from}")


def _listing_create(api: str, domain: str, cfg: dict, vps: str, key: str):
    ts = int(time.time())
    email = f"hatch-smoke-{ts}@{domain}"
    pw = "SmokeTest-" + secrets.token_hex(4)
    reg = http(f"{api}/api/auth/register", method="POST",
               headers={"Content-Type": "application/json"},
               body=json.dumps({"email": email, "password": pw,
                                "display_name": "Hatch Smoke", "marketing_opt_in": False}))
    code, txt = reg
    if code >= 300:
        record("listing create works", FAILED, f"register HTTP {code}: {txt[:80]}")
        return
    try:
        tokn = json.loads(txt).get("access_token")
    except json.JSONDecodeError:
        tokn = None
    if not tokn:
        record("listing create works", FAILED, "no access_token from register")
        return
    prod = (cfg.get("products") or [{"key": "semen"}])[0]["key"]
    lc = http(f"{api}/api/listings", method="POST",
              headers={"Content-Type": "application/json",
                       "Authorization": f"Bearer {tokn}"},
              body=json.dumps({"product_type": prod, "sale_type": "fixed",
                               "unit_price": 99, "quantity_available": 1}))
    code, txt = lc
    listing_id = None
    if code < 300:
        try:
            listing_id = json.loads(txt).get("id")
        except json.JSONDecodeError:
            pass
    record("listing create works",
           PASS if listing_id else FAILED,
           f"listing #{listing_id}" if listing_id else f"HTTP {code}: {txt[:100]}")
    # cleanup: drop the throwaway listing + user straight out of the tank DB
    _cleanup(vps, key, email, listing_id)


def _cleanup(vps: str, key: str, email: str, listing_id):
    """Delete the throwaway listing + user via the tank's own SQLAlchemy engine
    (the VPS has no sqlite3 CLI, and going through the app respects the DB lock/WAL
    that the live service holds). Reports honestly — a failed clean is not a PASS."""
    root = os.environ.get("HATCH_VPS_REPO", "/root/wagyutank")
    lid = int(listing_id) if listing_id else 0
    py = (
        "from app.db import SessionLocal; from app import models; "
        "db=SessionLocal(); "
        f"db.query(models.Listing).filter(models.Listing.id=={lid}).delete() if {lid} else None; "
        f"db.query(models.User).filter(models.User.email=={email!r}).delete(synchronize_session=False); "
        "db.commit(); "
        "print('CLEAN', db.query(models.User).filter(models.User.email=="
        f"{email!r}).count())"
    )
    cmd = (f"cd {root}/backend && set -a && . {root}/tanks/{key}/tank.env && set +a "
           f"&& .venv/bin/python -c \"{py}\"")
    rc, out = ssh(vps, cmd, timeout=60)
    left = out.strip().split()[-1] if "CLEAN" in out else "?"
    ok = rc == 0 and left == "0"
    detail = ("removed throwaway user" + (f" + listing #{listing_id}" if listing_id else "")
              if ok else f"cleanup FAILED — remove {email} manually ({out.strip()[:80]})")
    record("smoke cleanup", PASS if ok else FAILED, detail)


if __name__ == "__main__":
    main()
