#!/usr/bin/env python3
"""Capture a distinctive visual mark (logo, or a clip of the hero) for every
ranch/operation we link to, so the Wagyu Atlas isn't a wall of text.

Two target sources share one image folder (wagyutank-site/public/ranch/):

  * sellers    -- DirectorySeller rows, the ones the Atlas actually renders.
                  Keyed by registrable domain -> /ranch/<domain>.png
                  (the Atlas client already knows each seller's domain, so it can
                  derive the path with no API change).
  * facilities -- Facility rows (AI / repro / cloning centers).
                  Keyed by id -> /ranch/<id>.png, and written back to
                  facilities.logo_url / .logo_captured_at.

Strategy per site, in order:
  1. A real logo image on the page (img with "logo" in src/alt/class/id, or a
     header/nav img, or an inline SVG logo). Raster URLs are downloaded; SVG and
     undownloadable candidates fall back to an element screenshot.
  2. The Open-Graph image (og:image / twitter:image).
  3. A cropped screenshot of the top hero area (top 420px of a 1280 viewport).

House rules: identify ourselves (WagyuTankBot), honour robots.txt when it's
readable, hard timeout per site, rate-limit between sites, and never let one
broken site kill the run. Idempotent and resumable -- an already-captured target
is skipped unless --force.

Honesty rule: if a site blocks us or yields nothing usable we record a failure
and leave logo_url NULL. We never substitute a placeholder or someone else's mark.

Usage:
    python3 scripts/capture_ranch_marks.py --source sellers --limit 5
    python3 scripts/capture_ranch_marks.py --source facilities --only 3 --force
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from datetime import datetime, timezone

from PIL import Image

UA = "WagyuTankBot/1.0 (+https://wagyutank.com; ranch mark capture; contact office@wagyutank.com)"
NAV_TIMEOUT_MS = 20_000
SETTLE_MS = 2_000
MAX_W = 600
VIEWPORT = {"width": 1280, "height": 900}
HERO_H = 420
POLITE_DELAY = (2.0, 4.0)          # seconds between sites
MIN_PIXELS = 2_400                 # anything smaller is a sliver, not an image
MIN_LOGO_W = 80                    # a logo candidate narrower than this is an icon
MIN_LOGO_PIXELS = 5_000
MAX_BYTES = 100_000                # keep the Atlas light; squeeze anything bigger
ROBOTS_TIMEOUT = 6

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
DEFAULT_DB = os.path.join(BACKEND, "wagyutank.db")
DEFAULT_OUT = os.path.abspath(
    os.path.join(BACKEND, "..", "..", "wagyutank-site", "public", "ranch")
)
# The run record lives with the backend, not in the published web folder --
# only the images and index.json are meant to ship.
DEFAULT_MANIFEST = os.path.join(BACKEND, "data", "ranch_marks_manifest.json")

# JS that runs in the page and ranks logo candidates.
FIND_LOGO_JS = r"""
() => {
  const out = [];
  const abs = (u) => { try { return new URL(u, location.href).href; } catch (e) { return null; } };
  const vis = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width >= 40 && r.height >= 18 && r.top < 700 &&
           st.visibility !== 'hidden' && st.display !== 'none' && +st.opacity > 0.1;
  };
  const inHeader = (el) => !!el.closest('header, nav, .header, .site-header, #header, .navbar, .topbar, .masthead, .logo');
  const hay = (el) => [
    el.getAttribute('src') || '', el.getAttribute('data-src') || '',
    el.getAttribute('alt') || '', el.className && el.className.baseVal !== undefined
      ? el.className.baseVal : (el.className || ''),
    el.id || '', (el.parentElement && el.parentElement.className &&
      (el.parentElement.className.baseVal !== undefined
        ? el.parentElement.className.baseVal : el.parentElement.className)) || '',
  ].join(' ').toLowerCase();

  document.querySelectorAll('img').forEach((el, i) => {
    if (!vis(el)) return;
    const h = hay(el);
    const r = el.getBoundingClientRect();
    let score = 0;
    if (/logo|brand|wordmark|lockup/.test(h)) score += 60;
    if (inHeader(el)) score += 40;
    if (r.top < 200) score += 15;
    if (/sprite|icon-|banner|slide|hero|placeholder|avatar|flag|cart|search|menu/.test(h)) score -= 35;
    if (r.width > 900) score -= 30;          // full-width banner, not a mark
    if (score <= 0) return;
    const src = el.currentSrc || el.getAttribute('src') || el.getAttribute('data-src');
    out.push({ kind: 'img', score, idx: i, url: src ? abs(src) : null,
               w: Math.round(r.width), h: Math.round(r.height),
               nw: el.naturalWidth || 0, nh: el.naturalHeight || 0 });
  });

  document.querySelectorAll('svg').forEach((el, i) => {
    if (!vis(el)) return;
    const h = hay(el);
    let score = 0;
    if (/logo|brand|wordmark|lockup/.test(h)) score += 55;
    if (inHeader(el)) score += 30;
    if (/icon|arrow|chevron|caret|social|facebook|instagram|twitter|search|menu|cart/.test(h)) score -= 60;
    const r = el.getBoundingClientRect();
    if (r.width < 60 || r.height < 20) score -= 40;
    if (score <= 0) return;
    out.push({ kind: 'svg', score, idx: i, url: null,
               w: Math.round(r.width), h: Math.round(r.height), nw: 0, nh: 0 });
  });

  // Background-image logos (common on .logo <a> wrappers)
  document.querySelectorAll('a,div,span').forEach((el, i) => {
    const h = hay(el);
    if (!/logo|wordmark/.test(h)) return;
    if (!vis(el)) return;
    const bg = getComputedStyle(el).backgroundImage || '';
    const m = bg.match(/url\(["']?(.*?)["']?\)/);
    if (!m) return;
    const r = el.getBoundingClientRect();
    out.push({ kind: 'bg', score: 45 + (inHeader(el) ? 25 : 0), idx: i, url: abs(m[1]),
               w: Math.round(r.width), h: Math.round(r.height), nw: 0, nh: 0 });
  });

  out.sort((a, b) => b.score - a.score);
  return out.slice(0, 6);
}
"""

META_JS = r"""
() => {
  const pick = (sel, attr) => {
    const el = document.querySelector(sel);
    return el ? el.getAttribute(attr) : null;
  };
  const abs = (u) => { try { return u ? new URL(u, location.href).href : null; } catch (e) { return null; } };
  return {
    og: abs(pick('meta[property="og:image"]', 'content') ||
            pick('meta[name="og:image"]', 'content') ||
            pick('meta[name="twitter:image"]', 'content') ||
            pick('meta[property="twitter:image"]', 'content')),
  };
}
"""


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def log(*a):
    print(*a, flush=True)


def robots_ok(url: str) -> tuple[bool, str]:
    """Fail-open: if robots.txt is unreachable/unparseable we proceed."""
    try:
        parts = urllib.parse.urlsplit(url)
        robots = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        req = urllib.request.Request(robots, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=ROBOTS_TIMEOUT) as r:
            if r.status != 200:
                return True, "robots:none"
            body = r.read(200_000).decode("utf-8", "replace")
        rp = urllib.robotparser.RobotFileParser()
        rp.parse(body.splitlines())
        allowed = rp.can_fetch("WagyuTankBot", url)
        if not allowed:
            # A blanket Disallow: / that also blocks Googlebot is usually a
            # misconfigured or parked site; but we obey regardless.
            return False, "robots:disallow"
        return True, "robots:allow"
    except Exception:
        return True, "robots:unreadable"


def fetch_bytes(url: str, referer: str | None = None, timeout: int = 15) -> bytes | None:
    try:
        headers = {"User-Agent": UA, "Accept": "image/*,*/*"}
        if referer:
            headers["Referer"] = referer
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            if r.status != 200:
                return None
            return r.read(8_000_000)
    except Exception:
        return None


def _encode(im: Image.Image) -> bytes:
    """PNG, squeezed. Logos palettise beautifully; photos get a second downscale."""
    def png(x: Image.Image, **kw) -> bytes:
        b = io.BytesIO()
        x.save(b, "PNG", optimize=True, **kw)
        return b.getvalue()

    out = png(im)
    if len(out) <= MAX_BYTES:
        return out
    try:
        q = im.quantize(colors=128, method=Image.MEDIANCUT) if im.mode == "RGB" else \
            im.convert("RGBA").quantize(colors=128, method=Image.FASTOCTREE)
        cand = png(q)
        if len(cand) < len(out):
            out = cand
    except Exception:
        pass
    if len(out) > MAX_BYTES and im.width > 380:
        small = im.resize((380, max(1, round(im.height * 380 / im.width))), Image.LANCZOS)
        try:
            small = small.quantize(colors=128, method=Image.FASTOCTREE) \
                if small.mode == "RGBA" else small.quantize(colors=128)
        except Exception:
            pass
        cand = png(small)
        if len(cand) < len(out):
            out = cand
    return out


def normalise(raw: bytes, *, strict: bool = False) -> bytes | None:
    """Decode, trim uniform margins, downscale to MAX_W, return PNG bytes.

    strict=True is used for logo candidates: it rejects icon fragments (a stray
    16x16 sprite is not a ranch's mark) that are fine as part of a hero crop."""
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        return None
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA" if "A" in im.mode or im.mode == "P" else "RGB")

    im = _trim(im)
    if im is None:
        return None
    w, h = im.size
    if w * h < MIN_PIXELS:
        return None
    if strict and (w < MIN_LOGO_W or w * h < MIN_LOGO_PIXELS):
        return None
    if w > MAX_W:
        im = im.resize((MAX_W, max(1, round(h * MAX_W / w))), Image.LANCZOS)
    if im.height > 400:
        s = 400 / im.height
        im = im.resize((max(1, round(im.width * s)), 400), Image.LANCZOS)
    return _encode(im)


def _trim(im: Image.Image) -> Image.Image | None:
    """Trim fully-transparent or uniform-colour borders. None if the image is blank."""
    try:
        if im.mode == "RGBA":
            alpha = im.getchannel("A")
            bbox = alpha.getbbox()
            if bbox and (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) > 0:
                sub = im.crop(bbox)
                if sub.getchannel("A").getextrema()[1] == 0:
                    return None
                im = sub
        rgb = im.convert("RGB")
        ex = rgb.getextrema()
        if all(lo == hi for lo, hi in ex):
            return None                      # single flat colour -> useless
        bg = rgb.getpixel((0, 0))
        from PIL import ImageChops
        diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, bg))
        bbox = diff.getbbox()
        if bbox:
            pad = 2
            bbox = (max(0, bbox[0] - pad), max(0, bbox[1] - pad),
                    min(im.width, bbox[2] + pad), min(im.height, bbox[3] + pad))
            if (bbox[2] - bbox[0]) > 8 and (bbox[3] - bbox[1]) > 8:
                im = im.crop(bbox)
        return im
    except Exception:
        return im


def interesting(png: bytes) -> bool:
    """Reject near-empty captures (blank/one-colour hero, cookie wall, etc)."""
    try:
        im = Image.open(io.BytesIO(png)).convert("RGB")
        small = im.resize((48, 48))
        colours = {p for p in small.getdata()}
        if len(colours) < 6:
            return False
        ex = small.getextrema()
        spread = max(hi - lo for lo, hi in ex)
        return spread >= 30
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# per-site capture
# --------------------------------------------------------------------------- #
def _variants(url: str) -> list[str]:
    """The original URL plus one www/apex flip -- many ranch sites only answer on one."""
    out = [url]
    try:
        p = urllib.parse.urlsplit(url)
        host = p.netloc
        alt = host[4:] if host.startswith("www.") else "www." + host
        out.append(urllib.parse.urlunsplit((p.scheme, alt, p.path or "/", p.query, "")))
    except Exception:
        pass
    return out


def is_parked(page) -> bool:
    """Domain-parking / for-sale / under-construction pages carry no real mark."""
    try:
        info = page.evaluate(
            "() => ({t: (document.title||'').toLowerCase(),"
            " b: (document.body ? document.body.innerText : '').slice(0, 1500).toLowerCase(),"
            " n: document.querySelectorAll('a,p,h1,h2,img').length})"
        ) or {}
    except Exception:
        return False
    blob = f"{info.get('t','')} {info.get('b','')}"
    marks = (
        "under construction", "coming soon", "domain is for sale", "buy this domain",
        "this domain may be for sale", "parked", "related searches", "sponsored listings",
        "domain for sale", "website is under maintenance", "account suspended",
        "default web page", "welcome to nginx", "apache2 ubuntu default",
        "future home of something quite cool", "godaddy.com", "sedo", "hugedomains",
        "network solutions", "site not found", "this site can't be reached",
        "expired", "renew now", "checking your browser", "enable javascript",
        "just a moment", "attention required",
        # bot walls: whatever is behind them, it is not the ranch's own mark
        "verifying you are human", "verify you are human", "security of your connection",
        "ddos protection", "ray id", "performance & security by", "human verification",
        "are you a robot", "access denied", "request blocked", "unusual traffic",
        "please turn javascript on", "captcha",
        # error and unconfigured-host pages
        "page not found", "404 not found", "error 404", "404 error", "not found",
        "403 forbidden", "forbidden", "500 internal server", "502 bad gateway",
        "503 service", "domain isn't connected", "domain is not connected",
        "this site is not published", "create a website", "start building",
        "server error", "temporarily unavailable", "site is temporarily down",
    )
    if any(m in blob for m in marks):
        return True
    # An almost-empty DOM is a placeholder, not a ranch site.
    return int(info.get("n") or 0) < 4


def capture_site(page, url: str) -> tuple[bytes | None, str]:
    """Return (png_bytes, method). method describes what worked / what failed."""
    last = "nav_failed"
    landed = False
    for cand in _variants(url):
        try:
            page.goto(cand, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
            landed = True
            break
        except Exception as e:
            last = f"nav_failed:{type(e).__name__}"
    if not landed:
        return None, last
    try:
        page.wait_for_timeout(SETTLE_MS)
        page.evaluate("() => window.scrollTo(0, 0)")
    except Exception:
        pass

    if is_parked(page):
        return None, "parked_or_placeholder"

    # --- 1. logo on the page -------------------------------------------------
    try:
        cands = page.evaluate(FIND_LOGO_JS) or []
    except Exception:
        cands = []
    for c in cands:
        curl = c.get("url") or ""
        # raster download first (best fidelity, keeps transparency)
        if curl and not curl.lower().split("?")[0].endswith(".svg") \
                and not curl.startswith("data:"):
            raw = fetch_bytes(curl, referer=url)
            if raw:
                png = normalise(raw, strict=True)
                if png and interesting(png):
                    return png, f"logo_img({c['kind']})"
        # data: URI
        if curl.startswith("data:image"):
            try:
                import base64
                head, b64 = curl.split(",", 1)
                raw = base64.b64decode(b64) if ";base64" in head else None
                if raw:
                    png = normalise(raw, strict=True)
                    if png and interesting(png):
                        return png, "logo_datauri"
            except Exception:
                pass
        # SVG / undownloadable -> screenshot the element itself
        try:
            sel = "img" if c["kind"] == "img" else ("svg" if c["kind"] == "svg" else None)
            if sel:
                els = page.query_selector_all(sel)
                if c["idx"] < len(els):
                    raw = els[c["idx"]].screenshot(type="png", timeout=8000)
                    png = normalise(raw, strict=True)
                    if png and interesting(png):
                        return png, f"logo_shot({c['kind']})"
        except Exception:
            pass

    # --- 2. og:image ---------------------------------------------------------
    try:
        meta = page.evaluate(META_JS) or {}
    except Exception:
        meta = {}
    if meta.get("og"):
        raw = fetch_bytes(meta["og"], referer=url)
        if raw:
            png = normalise(raw)
            if png and interesting(png):
                return png, "og_image"

    # --- 3. hero crop --------------------------------------------------------
    try:
        raw = page.screenshot(
            type="png", timeout=15000,
            clip={"x": 0, "y": 0, "width": VIEWPORT["width"], "height": HERO_H},
        )
        png = normalise(raw)
        if png and interesting(png):
            return png, "hero_crop"
        return None, "hero_blank"
    except Exception as e:
        return None, f"shot_failed:{type(e).__name__}"


# --------------------------------------------------------------------------- #
# targets
# --------------------------------------------------------------------------- #
def load_targets(db: str, source: str) -> list[dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out: list[dict] = []
    if source in ("facilities", "both"):
        for r in con.execute(
            "SELECT id, name, website, logo_url FROM facilities "
            "WHERE website IS NOT NULL AND website != '' ORDER BY id"
        ):
            out.append({"source": "facility", "key": str(r["id"]), "id": r["id"],
                        "name": r["name"], "url": r["website"], "done": bool(r["logo_url"])})
    if source in ("sellers", "both"):
        for r in con.execute(
            "SELECT site, name, url FROM directory_sellers "
            "WHERE status='active' ORDER BY site"
        ):
            out.append({"source": "seller", "key": r["site"], "id": None,
                        "name": r["name"], "url": r["url"] or f"https://{r['site']}",
                        "done": False})
    con.close()
    return out


def load_manifest(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_manifest(path: str, data: dict, index_path: str):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
    # {key: kind} for every key that actually has an image. The Atlas fetches this
    # so it only ever requests marks that exist (no 404 storm, no broken icons),
    # and so it can tell a logo (wants a light plate, contained) from a scene
    # (an og/hero photo, which wants to run edge to edge).
    index = {}
    for k, v in sorted(data.items()):
        if not v.get("ok"):
            continue
        img = os.path.join(os.path.dirname(index_path), f"{k}.png")
        index[k] = v.get("plate") or plate_for(img, v.get("method", ""))
    tmp = index_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=0)
    os.replace(tmp, index_path)


def kind_of(method: str) -> str:
    return "logo" if method.startswith("logo_") else "scene"


def plate_for(path: str, method: str) -> str:
    """Which backdrop this mark needs.

    A logo drawn in white ink on transparency is just as invisible on a light
    plate as a black one is on our dark cards, so look at the ink and say so:
      "logo"      -- dark ink, wants the light plate (the common case)
      "logo_dark" -- light ink, wants a dark plate
      "scene"     -- a photo/hero clip, runs edge to edge, no plate
    Opaque images carry their own background, so the plate never shows: they
    stay on the default."""
    if not method.startswith("logo_"):
        return "scene"
    try:
        im = Image.open(path)
        im.load()
        if im.mode not in ("RGBA", "LA", "P"):
            return "logo"
        im = im.convert("RGBA")
        a = im.getchannel("A")
        if a.getextrema()[0] > 250:          # effectively opaque
            return "logo"
        rgb = im.convert("RGB")
        px, ap = rgb.getdata(), a.getdata()
        tot = n = 0
        for (r, g, b), al in zip(px, ap):
            if al < 200:
                continue
            tot += 0.299 * r + 0.587 * g + 0.114 * b
            n += 1
        if n < 50:
            return "logo"
        return "logo_dark" if (tot / n) > 186 else "logo"
    except Exception:
        return "logo"


# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["sellers", "facilities", "both"], default="both")
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--manifest", default=DEFAULT_MANIFEST,
                    help="run record (kept out of the published web folder)")
    ap.add_argument("--limit", type=int, default=0, help="max sites this run (0 = all)")
    ap.add_argument("--only", default=None, help="single target: facility id or seller domain")
    ap.add_argument("--force", action="store_true", help="recapture even if already done")
    ap.add_argument("--no-robots", action="store_true", help="skip the robots.txt check")
    ap.add_argument("--delay", type=float, default=0, help="fixed delay between sites (0 = polite random)")
    ap.add_argument("--reindex", action="store_true",
                    help="reclassify the marks already on disk and rewrite index.json; fetches nothing")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(os.path.dirname(args.manifest) or ".", exist_ok=True)
    manifest_path = args.manifest
    index_path = os.path.join(args.out, "index.json")
    manifest = load_manifest(manifest_path)
    if not manifest:  # one-time pickup of the old in-public location
        manifest = load_manifest(os.path.join(args.out, "_manifest.json"))

    if args.reindex:
        n = 0
        for k, v in manifest.items():
            if not v.get("ok"):
                continue
            img = os.path.join(args.out, f"{k}.png")
            if not os.path.exists(img):
                v["ok"] = False
                v["method"] = "file_missing"
                continue
            v["plate"] = plate_for(img, v.get("method", ""))
            n += 1
        save_manifest(manifest_path, manifest, index_path)
        import collections as _c
        log(f"reindexed {n} marks: {dict(_c.Counter(v['plate'] for v in manifest.values() if v.get('ok')))}")
        return 0

    targets = load_targets(args.db, args.source)
    if args.only:
        targets = [t for t in targets if t["key"] == args.only]
        if not targets:
            log(f"no target matching --only {args.only}")
            return 2

    todo = []
    for t in targets:
        img = os.path.join(args.out, f"{t['key']}.png")
        # The image file is the source of truth. A facilities row can still
        # carry a logo_url whose file has since been deleted (a bad capture
        # pulled back out) -- that has to be recaptured, not skipped.
        have = os.path.exists(img)
        prev = manifest.get(t["key"])
        if not args.force:
            if have:
                continue
            # Don't re-hammer a site that already failed hard, unless forced.
            if prev and not prev.get("ok") and prev.get("attempts", 0) >= 2:
                continue
        todo.append(t)
    if args.limit:
        todo = todo[: args.limit]

    log(f"targets: {len(targets)}  to capture now: {len(todo)}  out: {args.out}")
    if not todo:
        save_manifest(manifest_path, manifest, index_path)
        return 0

    from playwright.sync_api import sync_playwright

    ok = fail = 0
    by_method: dict[str, int] = {}
    fac_updates: list[tuple[str, str, int]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-dev-shm-usage"])
        ctx = browser.new_context(
            user_agent=UA, viewport=VIEWPORT,
            ignore_https_errors=True, java_script_enabled=True,
        )
        ctx.set_default_timeout(NAV_TIMEOUT_MS)
        for n, t in enumerate(todo, 1):
            key, url = t["key"], t["url"]
            entry = manifest.get(key, {})
            entry["name"] = t["name"]
            entry["url"] = url
            entry["source"] = t["source"]
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

            if not args.no_robots:
                allowed, why = robots_ok(url)
                if not allowed:
                    entry.update(ok=False, method=why)
                    manifest[key] = entry
                    fail += 1
                    log(f"[{n}/{len(todo)}] {key:38} SKIP robots.txt disallow")
                    continue

            page = None
            try:
                page = ctx.new_page()
                png, method = capture_site(page, url)
            except Exception as e:                       # never kill the run
                png, method = None, f"error:{type(e).__name__}"
            finally:
                try:
                    if page:
                        page.close()
                except Exception:
                    pass

            if png:
                with open(os.path.join(args.out, f"{key}.png"), "wb") as f:
                    f.write(png)
                entry.update(ok=True, method=method, bytes=len(png))
                entry["plate"] = plate_for(os.path.join(args.out, f"{key}.png"), method)
                by_method[method] = by_method.get(method, 0) + 1
                ok += 1
                if t["source"] == "facility":
                    fac_updates.append((f"/ranch/{key}.png",
                                        datetime.now(timezone.utc).isoformat(sep=" ", timespec="seconds"),
                                        t["id"]))
                log(f"[{n}/{len(todo)}] {key:38} OK   {method} ({len(png)//1024}kB)")
            else:
                entry.update(ok=False, method=method)
                fail += 1
                log(f"[{n}/{len(todo)}] {key:38} --   {method}")

            manifest[key] = entry
            if n % 10 == 0:
                save_manifest(manifest_path, manifest, index_path)
            if n < len(todo):
                time.sleep(args.delay if args.delay else random.uniform(*POLITE_DELAY))
        try:
            ctx.close()
            browser.close()
        except Exception:
            pass

    save_manifest(manifest_path, manifest, index_path)

    if fac_updates:
        con = sqlite3.connect(args.db)
        con.executemany(
            "UPDATE facilities SET logo_url = ?, logo_captured_at = ? WHERE id = ?",
            fac_updates)
        con.commit()
        con.close()
        log(f"facilities updated in DB: {len(fac_updates)}")

    log(f"\ndone: {ok} captured, {fail} failed")
    for m, c in sorted(by_method.items(), key=lambda kv: -kv[1]):
        log(f"  {c:4}  {m}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
