""""The Roundup" aggregation pipeline (MASTER_PLAN growth lever).

Scours a curated + auto-expanding set of public Wagyu-genetics listing pages,
extracts the *facts* of each for-sale listing (sire, price, count, location,
seller, link), writes our own neutral summary, and upserts an AggregatedListing
that points back to the original. It is deliberately polite and defensible:

  - Respects robots.txt (skips disallowed URLs).
  - Identifies itself (WagyuTankBot) and rate-limits.
  - Stores extracted facts + a neutral blurb — NEVER rehosts the seller's ad copy
    or images; every listing links prominently to the source.
  - Sellers can opt out (a flagged listing is hidden).
  - Daily refresh marks listings that vanished from a successfully-fetched source
    as `delisted`.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from ..models import AggregatedListing, ProductType
from .ai import chat

USER_AGENT = "WagyuTankBot/1.0 (+https://www.wagyutank.com/roundup; aggregator)"

# Curated seed of public Wagyu-genetics listing pages. The daily job also runs a
# web-search discovery step to grow this over time; sellers/sites can opt out.
SEED_SOURCES = [
    "https://bovine-elite.com/beef-semen-sales-registered/wagyu/",
    "https://www.chisholmcattle.com/wagyu-semen",
    "https://www.z6cattle.com/wagyu-semen/",
    "https://nuwagyu.com/products/wagyu-semen-for-sale",
    "https://www.sirebuyer.com/wagyu-semen/",
]

_PRODUCT_LABEL = {"semen": "Semen", "embryo": "Embryos", "clone_rights": "Cloning Rights"}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _robots_ok(url: str) -> bool:
    try:
        p = urlparse(url)
        rp = RobotFileParser()
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        # If robots is unreadable, be conservative but not blocking: allow.
        return True


def _fetch(url: str) -> str | None:
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT},
                      timeout=25, follow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text
    except Exception:
        pass
    return None


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&amp;|&#39;|&quot;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:14000]


_EXTRACT_SYSTEM = (
    "You extract structured facts about FROZEN WAGYU GENETICS for sale (semen straws, "
    "embryos, or cloning/cell-line rights) from a web page's text. Return ONLY a JSON array. "
    "Each element: {product_type: 'semen'|'embryo'|'clone_rights', animal_name, registration_no, "
    "bloodline, price (number or null), price_unit, currency, quantity, seller_name, location, "
    "country (2-letter)}. Include ONLY genuine for-sale listings of Wagyu genetics — skip live "
    "cattle, beef products, general info, and non-Wagyu. If the page has none, return []. "
    "Never invent data; use null for unknown fields."
)


def _extract(text: str, source_url: str) -> list[dict]:
    if not text:
        return []
    out = chat(_EXTRACT_SYSTEM, f"Page URL: {source_url}\n\nPage text:\n{text}", max_tokens=1800)
    if not out:
        return []
    # Pull the first JSON array out of the response.
    m = re.search(r"\[.*\]", out, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _product(pt: str | None) -> ProductType | None:
    try:
        return ProductType((pt or "").strip().lower())
    except ValueError:
        return None


def _dedup_key(source_url: str, product: str, animal: str, price) -> str:
    raw = f"{source_url}|{product}|{(animal or '').lower().strip()}|{price}"
    return hashlib.sha1(raw.encode()).hexdigest()[:40]


def _title(animal: str | None, product: ProductType, seller: str | None) -> str:
    name = animal or "Wagyu"
    label = _PRODUCT_LABEL[product.value]
    return f"{name} {label}" + (f" — {seller}" if seller else "")


def _summary(li: dict, animal: str | None, product: ProductType) -> str:
    bits = []
    qty = li.get("quantity")
    noun = {"semen": "semen straws", "embryo": "embryos", "clone_rights": "cloning rights"}[product.value]
    lead = f"{qty} " if qty else ""
    reg = f" ({li['registration_no']})" if li.get("registration_no") else ""
    bits.append(f"{lead}{noun} from {animal or 'a Wagyu sire'}{reg}.")
    if li.get("bloodline"):
        bits.append(f"{li['bloodline']} bloodline.")
    if li.get("seller_name"):
        loc = f" in {li['location']}" if li.get("location") else ""
        bits.append(f"Listed by {li['seller_name']}{loc}.")
    if li.get("price"):
        unit = f" {li['price_unit']}" if li.get("price_unit") else ""
        bits.append(f"Asking {li.get('currency', 'USD')} {li['price']}{unit}.")
    return " ".join(bits)


def _upsert(db, li: dict, source_url: str, source_site: str) -> bool:
    product = _product(li.get("product_type"))
    if not product:
        return False
    animal = (li.get("animal_name") or "").strip() or None
    price = li.get("price") if isinstance(li.get("price"), (int, float)) else None
    key = _dedup_key(source_url, product.value, animal or "", price)
    row = db.query(AggregatedListing).filter(AggregatedListing.dedup_key == key).first()
    now = _now()
    if row:
        row.last_seen_at = now
        row.status = "active" if not row.flagged else row.status
        row.price = price if price is not None else row.price
        return False
    db.add(AggregatedListing(
        dedup_key=key, product_type=product,
        title=_title(animal, product, li.get("seller_name")),
        summary=_summary(li, animal, product),
        animal_name=animal, animal_reg=(li.get("registration_no") or None),
        bloodline=(li.get("bloodline") or None),
        price=price, price_unit=(li.get("price_unit") or None),
        currency=(li.get("currency") or "USD")[:3].upper(),
        quantity_text=(str(li["quantity"]) if li.get("quantity") else None),
        seller_name=(li.get("seller_name") or None),
        location=(li.get("location") or None),
        country=((li.get("country") or "")[:2].upper() or None),
        source_site=source_site, source_url=source_url,
        first_seen_at=now, last_seen_at=now, status="active",
    ))
    return True


def run(db, sources: list[str] | None = None, delist: bool = True) -> dict:
    """Fetch each source, extract listings, upsert. Mark listings from
    successfully-fetched sources that weren't seen this run as delisted."""
    started = _now()
    sources = sources or SEED_SOURCES
    added = seen = 0
    ok_sites: set[str] = set()
    for url in sources:
        site = urlparse(url).netloc
        if not _robots_ok(url):
            continue
        html = _fetch(url)
        if not html:
            continue
        ok_sites.add(site)
        for li in _extract(_html_to_text(html), url):
            seen += 1
            if _upsert(db, li, url, site):
                added += 1
        db.commit()
        time.sleep(2.5)  # be polite
    delisted = 0
    if delist and ok_sites:
        stale = db.query(AggregatedListing).filter(
            AggregatedListing.source_site.in_(ok_sites),
            AggregatedListing.last_seen_at < started,
            AggregatedListing.status == "active",
        ).all()
        for row in stale:
            row.status = "delisted"
            delisted += 1
        db.commit()
    return {"sources": len(sources), "ok_sites": len(ok_sites),
            "seen": seen, "added": added, "delisted": delisted}
