"""Shared helpers for the Tank Hatchery (hatch_tank.py + smoke_tank.py).

Everything here is deliberately dependency-light: HTTP goes through the system
`curl` (Cloudflare and Resend both 403 python-urllib from a datacenter/residential
IP unless you spoof a browser UA — curl -A sidesteps it), and cross-machine work
goes through `ssh`. No third-party Python packages required.

Secrets are read from the environment (see deploy/.hatch-secrets.env.example).
Nothing here hardcodes a credential.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from typing import Any

# ---------------------------------------------------------------- pretty output
_C = {
    "step": "\033[1;36m", "ok": "\033[1;32m", "warn": "\033[1;33m",
    "err": "\033[1;31m", "dim": "\033[2m", "end": "\033[0m",
}
_NO_COLOR = not sys.stdout.isatty() or os.environ.get("NO_COLOR")


def _c(tag: str, s: str) -> str:
    if _NO_COLOR:
        return s
    return f"{_C.get(tag,'')}{s}{_C['end']}"


def step(msg: str) -> None:
    print(_c("step", f"\n=== {msg} ==="), flush=True)


def ok(msg: str) -> None:
    print(_c("ok", f"  ✓ {msg}"), flush=True)


def info(msg: str) -> None:
    print(f"  · {msg}", flush=True)


def warn(msg: str) -> None:
    print(_c("warn", f"  ! {msg}"), flush=True)


def fail(msg: str) -> None:
    print(_c("err", f"  ✗ {msg}"), flush=True)


class HatchError(RuntimeError):
    pass


# ---------------------------------------------------------------- env / secrets
def env(name: str, default: str | None = None, required: bool = False) -> str:
    v = os.environ.get(name, default)
    if required and not v:
        raise HatchError(f"missing required env var {name} "
                         f"(source deploy/.hatch-secrets.env first)")
    return v or ""


# Defaults for the WagyuTank fleet — overridable via env.
VPS_SSH = lambda: env("HATCH_VPS_SSH", "vps")
VPS_IP = lambda: env("HATCH_VPS_IP", "72.60.118.54")
MAIL_SSH = lambda: env("HATCH_MAIL_SSH", "windy-mail")
MAIL_HOST = lambda: env("HATCH_MAIL_HOST", "mail.windymail.ai")
REPO_ROOT_VPS = lambda: env("HATCH_VPS_REPO", "/root/wagyutank")
CF_ACCOUNT = lambda: env("CF_ACCOUNT_ID", "193b347aedeaafe35de0b5a534b2d9aa")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


# ---------------------------------------------------------------- subprocess
def run(cmd: list[str], *, input_text: str | None = None, timeout: int = 120,
        check: bool = False) -> subprocess.CompletedProcess:
    """Run a command, capturing stdout/stderr as text."""
    return subprocess.run(cmd, input=input_text, capture_output=True, text=True,
                          timeout=timeout, check=check)


def ssh_run(host: str, remote_cmd: str, *, timeout: int = 120) -> tuple[int, str, str]:
    """Run a command on a remote host over ssh. Returns (rc, stdout, stderr)."""
    p = run(["ssh", "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=no",
             host, remote_cmd], timeout=timeout)
    return p.returncode, p.stdout, p.stderr


# ---------------------------------------------------------------- Cloudflare API
def cf_api(method: str, path: str, *, token: str, body: dict | None = None,
           timeout: int = 40) -> dict:
    """Call the Cloudflare v4 API through curl. `path` is appended to the v4 base.
    Returns the parsed JSON (always a dict; raises HatchError on transport error)."""
    url = f"https://api.cloudflare.com/client/v4{path}"
    cmd = ["curl", "-s", "-A", UA, "-X", method.upper(), url,
           "-H", f"Authorization: Bearer {token}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data", json.dumps(body)]
    p = run(cmd, timeout=timeout)
    if p.returncode != 0:
        raise HatchError(f"curl failed for {method} {path}: {p.stderr[:200]}")
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        raise HatchError(f"non-JSON from CF {method} {path}: {p.stdout[:200]}")


def cf_zone_id(domain: str, *, token: str) -> str | None:
    d = cf_api("GET", f"/zones?name={domain}&per_page=1", token=token)
    res = d.get("result") or []
    return res[0]["id"] if res else None


def cf_dns_list(zone_id: str, *, token: str) -> list[dict]:
    d = cf_api("GET", f"/zones/{zone_id}/dns_records?per_page=200", token=token)
    if not d.get("success"):
        raise HatchError(f"CF dns list failed: {d.get('errors')}")
    return d.get("result", [])


def cf_dns_ensure(zone_id: str, *, token: str, type: str, name: str, content: str,
                  proxied: bool = False, priority: int | None = None,
                  existing: list[dict] | None = None, dry: bool = False) -> str:
    """Idempotently ensure a DNS record exists with the given content.
    Matches on (type, fully-qualified name). For records where multiple values
    are legitimate (MX, TXT), matches on (type, name, content-prefix) so we don't
    clobber a sibling. Returns 'created' | 'updated' | 'unchanged' | 'would-*'.
    """
    fqdn = name
    recs = existing if existing is not None else cf_dns_list(zone_id, token=token)

    def norm(s: str) -> str:
        return s.strip().strip('"').lower()

    def txt_cat(s: str) -> str:
        # A category so we don't clobber e.g. an SPF record with a DMARC one at
        # the same name (rare, but apex can hold SPF + a site-verification TXT).
        n = norm(s)
        if n.startswith("v=spf1"):
            return "spf"
        if n.startswith("v=dmarc1"):
            return "dmarc"
        if n.startswith("v=dkim1") or n.startswith("k=") or n.startswith("p="):
            return "dkim"
        return n[:24]

    # find a match
    match = None
    for r in recs:
        if r["type"] != type or r["name"] != fqdn:
            continue
        if type == "MX":
            # MX is keyed by (name) — at a given name we converge onto our host.
            match = r
            break
        elif type == "TXT":
            if txt_cat(content) == txt_cat(r["content"]):
                match = r
                break
            continue
        else:
            match = r
            break

    payload: dict[str, Any] = {"type": type, "name": fqdn, "content": content,
                               "ttl": 1, "proxied": proxied}
    if priority is not None:
        payload["priority"] = priority
        payload.pop("proxied", None)  # MX/SRV aren't proxied

    if match:
        same = (norm(match["content"]) == norm(content)
                and bool(match.get("proxied")) == bool(proxied)
                and (priority is None or match.get("priority") == priority))
        if same:
            return "unchanged"
        if dry:
            return "would-update"
        d = cf_api("PATCH", f"/zones/{zone_id}/dns_records/{match['id']}",
                   token=token, body=payload)
        if not d.get("success"):
            raise HatchError(f"CF dns update {type} {name} failed: {d.get('errors')}")
        return "updated"

    if dry:
        return "would-create"
    d = cf_api("POST", f"/zones/{zone_id}/dns_records", token=token, body=payload)
    if not d.get("success"):
        raise HatchError(f"CF dns create {type} {name} failed: {d.get('errors')}")
    return "created"


# ---------------------------------------------------------------- Resend API
def resend_api(method: str, path: str, *, key: str, body: dict | None = None,
               timeout: int = 40) -> dict:
    url = f"https://api.resend.com{path}"
    cmd = ["curl", "-s", "-A", UA, "-X", method.upper(), url,
           "-H", f"Authorization: Bearer {key}"]
    if body is not None:
        cmd += ["-H", "Content-Type: application/json", "--data", json.dumps(body)]
    p = run(cmd, timeout=timeout)
    if p.returncode != 0:
        raise HatchError(f"curl failed for resend {method} {path}: {p.stderr[:200]}")
    try:
        return json.loads(p.stdout or "{}")
    except json.JSONDecodeError:
        raise HatchError(f"non-JSON from Resend {method} {path}: {p.stdout[:200]}")


def resend_find_domain(domain: str, *, key: str) -> dict | None:
    d = resend_api("GET", "/domains", key=key)
    for x in d.get("data", []) or []:
        if x.get("name") == domain:
            return x
    return None


# ---------------------------------------------------------------- Stalwart CLI
def stalwart(args: list[str], *, timeout: int = 60) -> tuple[int, str, str]:
    """Run stalwart-cli on the mail host over ssh. Requires STALWART_PASSWORD in
    the environment. Uses the host binary against the loopback management port."""
    pw = env("STALWART_PASSWORD", required=True)
    url = env("STALWART_MGMT_URL", "http://localhost:8080")
    user = env("STALWART_USER", "admin")
    # single-quote-safe: pass the password via the remote env to avoid quoting hell
    remote = ("STALWART_PASSWORD=%s stalwart-cli --url %s --user %s %s"
              % (_shq(pw), _shq(url), _shq(user), " ".join(_shq(a) for a in args)))
    return ssh_run(MAIL_SSH(), remote, timeout=timeout)


def _shq(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def stalwart_query(obj: str) -> str:
    """Return the raw text of a Stalwart `query <obj>` table (columns: Id first)."""
    rc, out, err = stalwart(["query", obj])
    if rc != 0:
        raise HatchError(f"stalwart query {obj} failed: {(err or out)[:200]}")
    return out
