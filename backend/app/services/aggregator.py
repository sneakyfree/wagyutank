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
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

MAX_PAGES_PER_SITE = 6   # follow pagination up to this many pages per catalog
DEFAULT_PAGE_BUDGET = 220  # global cap on total page fetches per run (politeness + runtime)
DELIST_AFTER_DAYS = 5    # grace period — LLM extraction varies run-to-run, so only
                         # age out listings genuinely unseen for this many days

import httpx

from ..models import AggregatedListing, ProductType
from .ai import chat

USER_AGENT = "WagyuTankBot/1.0 (+https://www.wagyutank.com/roundup; aggregator)"
# Search engines gate non-browser agents; use a browser UA only for the discovery query.
SEARCH_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Curated international seed of public Wagyu/Akaushi genetics listing pages. The
# daily job ALSO runs a web-search discovery step (below) to grow this globally.
SEED_SOURCES = [
    # North America
    "https://bovine-elite.com/beef-semen-sales-registered/wagyu/",
    "https://www.chisholmcattle.com/wagyu-semen",
    "https://www.z6cattle.com/wagyu-semen/",
    "https://nuwagyu.com/products/wagyu-semen-for-sale",
    "https://lonemountainwagyu.com/wagyu-semen-for-sale/",
    "https://www.sirebuyer.com/wagyu-semen/",
    "https://www.sirebuyer.com/wagyu-embryos/",
    # Australia
    "https://tlg.com.au/wagyu/",
    "https://www.grsembryos.com.au/export",
    "https://www.agrigene.com.au/beef/",
    # Europe / UK
    "https://www.wagyu-genetics.de/",
]

# Auto-discovery queries — cast a wide, international net across products + regions.
DISCOVERY_QUERIES = [
    # products
    "wagyu semen for sale", "wagyu embryos for sale", "fullblood wagyu semen for sale",
    "akaushi semen for sale", "akaushi embryos for sale", "wagyu sire semen for sale",
    "buy wagyu semen straws online", "wagyu semen catalog price list",
    "wagyu embryos IVF for sale", "sexed wagyu semen for sale",
    # North America
    "wagyu semen for sale usa", "wagyu embryos for sale canada", "wagyu semen for sale mexico",
    # Australia / NZ
    "wagyu semen for sale australia", "wagyu embryos for sale australia",
    "wagyu genetics for sale new zealand", "fullblood wagyu semen australia",
    # Europe / UK
    "wagyu semen for sale europe", "wagyu genetics for sale uk",
    "wagyu semen for sale germany", "wagyu embryos for sale netherlands",
    "wagyu semen for sale france", "wagyu semen for sale spain", "wagyu genetics ireland",
    # South / Central America
    "wagyu semen for sale brazil", "wagyu embryos for sale argentina",
    "wagyu semen for sale uruguay", "wagyu genetics colombia",
    # Asia / Africa
    "wagyu semen for sale south africa", "wagyu genetics for sale asia",
]

_PRODUCT_LABEL = {"semen": "Semen", "embryo": "Embryos", "clone_rights": "Cloning Rights"}

# country (ISO-2) -> broad region code for the "international feel" facet.
_REGION_BY_COUNTRY = {
    "US": "NA", "CA": "NA", "MX": "NA",
    "BR": "SA", "AR": "SA", "UY": "SA", "CL": "SA", "PY": "SA", "CO": "SA", "PE": "SA",
    "GT": "CAM", "CR": "CAM", "PA": "CAM", "NI": "CAM", "HN": "CAM",
    "GB": "EU", "IE": "EU", "DE": "EU", "FR": "EU", "ES": "EU", "IT": "EU", "NL": "EU",
    "BE": "EU", "DK": "EU", "SE": "EU", "PL": "EU", "PT": "EU", "AT": "EU", "CH": "EU",
    "AU": "AU", "NZ": "AU",
    "JP": "AS", "CN": "AS", "KR": "AS", "TH": "AS", "SG": "AS", "PH": "AS", "VN": "AS",
    "ZA": "AF",
}
# domain TLD -> country fallback when the page doesn't state one.
_TLD_COUNTRY = {
    "au": "AU", "nz": "NZ", "uk": "GB", "de": "DE", "fr": "FR", "es": "ES", "it": "IT",
    "nl": "NL", "br": "BR", "ar": "AR", "uy": "UY", "ca": "CA", "mx": "MX", "za": "ZA",
    "jp": "JP", "cn": "CN",
}


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


def _pagination_links(html: str, base_url: str) -> list[str]:
    """Find same-domain pagination links (page 2, 3, ...) on a catalog page."""
    site = urlparse(base_url).netloc
    out: set[str] = set()
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html):
        href = m.group(1)
        low = href.lower()
        if not any(p in low for p in ("page=", "/page/", "?p=", "paged=", "offset=", "&p=")):
            continue
        absu = urljoin(base_url, href).split("#")[0]
        if urlparse(absu).netloc != site:
            continue
        if re.search(r"(page[=/]|[?&]p=|paged=|offset=)\d+", absu.lower()):
            out.add(absu)
    return list(out)[:MAX_PAGES_PER_SITE]


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = re.sub(r"&nbsp;|&amp;|&#39;|&quot;", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:14000]


_EXTRACT_SYSTEM = (
    "You extract structured facts about FROZEN WAGYU/AKAUSHI GENETICS for sale (semen straws, "
    "embryos, or cloning/cell-line rights) from a web page's text. Return ONLY a JSON array. "
    "Each element: {product_type: 'semen'|'embryo'|'clone_rights', animal_name, registration_no, "
    "bloodline, price (number or null), price_unit, currency, quantity, seller_name, location, "
    "country (ISO 2-letter), css_status ('css' if the page says CSS/Certified Semen Services or "
    "export-eligible; 'domestic' if it says domestic-only/non-CSS; else 'unknown'), "
    "export_regions (array from ['EU','AUS','CAN','MEX','BR','UK','CN','NZ','JP'] — only the "
    "destinations the page explicitly says it's export-eligible to; [] if unstated)}. "
    "Include ONLY genuine for-sale Wagyu/Akaushi genetics listings — skip live cattle, beef "
    "products, general info, and non-Wagyu. If the page has none, return []. "
    "Never invent data; use null/'unknown'/[] for anything not stated."
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


def _country_region(li: dict, source_site: str) -> tuple[str | None, str | None]:
    country = (li.get("country") or "").strip().upper()[:2] or None
    if not country:
        tld = source_site.rsplit(".", 1)[-1].lower()
        country = _TLD_COUNTRY.get(tld)
        if not country and (source_site.endswith(".com") or source_site.endswith(".org")):
            country = "US"  # default assumption for generic gTLDs
    region = _REGION_BY_COUNTRY.get(country or "", None)
    return country, region


def _css(li: dict) -> str:
    v = (li.get("css_status") or "unknown").strip().lower()
    return v if v in ("css", "domestic", "unknown") else "unknown"


def _export_regions(li: dict) -> list:
    allowed = {"EU", "AUS", "CAN", "MEX", "BR", "UK", "CN", "NZ", "JP"}
    return [r for r in (li.get("export_regions") or []) if isinstance(r, str) and r.upper() in allowed]


def _upsert(db, li: dict, source_url: str, source_site: str) -> bool:
    product = _product(li.get("product_type"))
    if not product:
        return False
    animal = (li.get("animal_name") or "").strip() or None
    price = li.get("price") if isinstance(li.get("price"), (int, float)) else None
    # Quality gate: a listing with neither an animal name nor a price is junk.
    if not animal and price is None and not (li.get("seller_name") or "").strip():
        return False
    key = _dedup_key(source_url, product.value, animal or "", price)
    row = db.query(AggregatedListing).filter(AggregatedListing.dedup_key == key).first()
    now = _now()
    css, regions = _css(li), _export_regions(li)
    country, region = _country_region(li, source_site)
    if row:
        row.last_seen_at = now
        row.status = "active" if not row.flagged else row.status
        row.price = price if price is not None else row.price
        if css != "unknown":
            row.css_status = css
        if regions:
            row.export_regions = regions
        if not row.region and region:      # backfill for rows created before region inference
            row.region = region
        if not row.country and country:
            row.country = country
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
        country=country, region=region,
        css_status=css, export_regions=regions,
        source_site=source_site, source_url=source_url,
        first_seen_at=now, last_seen_at=now, status="active",
    ))
    return True


_DISCOVERY_SKIP = (
    "wikipedia.org", "facebook.com", "youtube.com", "instagram.com", "reddit.com",
    "amazon.", "ebay.", "pinterest.", "linkedin.com", "twitter.com", "x.com",
    "wagyu.org", "americanwagyu", "wagyu.org.au", "akaushi.com", "tiktok.com",
    ".gov", "wagyutank.com", "duckduckgo.com", "google.", "bing.com", "yelp.com",
    "wikipedia", "quora.com", "beefcentral.com", "news",
)
_DISCOVERY_KEEP = ("wagyu", "akaushi", "semen", "embryo", "genetic", "sire", "cattle", "beef", "stud")


def _discover(queries: list[str] | None = None, per_query: int = 10) -> list[str]:
    """Best-effort web-search discovery (DuckDuckGo HTML) for new seller pages."""
    import re as _re
    from urllib.parse import unquote
    queries = queries or DISCOVERY_QUERIES
    found: dict[str, None] = {}
    for q in queries:
        try:
            r = httpx.get("https://html.duckduckgo.com/html/", params={"q": q},
                          headers={"User-Agent": SEARCH_UA}, timeout=20, follow_redirects=True)
            if r.status_code != 200:
                continue
            hrefs = _re.findall(r'href="([^"]+)"', r.text)
            n = 0
            for h in hrefs:
                if "uddg=" in h:
                    m = _re.search(r"uddg=([^&]+)", h)
                    if m:
                        h = unquote(m.group(1))
                if not h.startswith("http"):
                    continue
                host = urlparse(h).netloc.lower()
                if any(s in host or s in h for s in _DISCOVERY_SKIP):
                    continue
                if not any(k in h.lower() for k in _DISCOVERY_KEEP):
                    continue
                if h not in found:
                    found[h] = None
                    n += 1
                if n >= per_query:
                    break
        except Exception:
            continue
        time.sleep(1.5)
    return list(found)


def _crawl_source(db, start_url: str, visited: set, budget: list) -> tuple[int, int, int, bool]:
    """Crawl one catalog page and follow its pagination (bounded). Returns
    (added, seen, pages_fetched, ok). `budget` is a 1-element list = remaining
    global page budget (mutated in place)."""
    site = urlparse(start_url).netloc
    queue = [start_url]
    added = seen = pages = 0
    ok = False
    while queue and pages < MAX_PAGES_PER_SITE and budget[0] > 0:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            if not _robots_ok(url):
                continue
            html = _fetch(url)
            budget[0] -= 1
            pages += 1
            if not html:
                continue
            ok = True
            for li in _extract(_html_to_text(html), url):
                seen += 1
                if _upsert(db, li, url, site):
                    added += 1
            db.commit()
            if pages == 1:  # only fan out pagination from the first page
                for p in _pagination_links(html, url):
                    if p not in visited:
                        queue.append(p)
        except Exception:
            db.rollback()
        time.sleep(2)  # be polite
    return added, seen, pages, ok


def run(db, sources: list[str] | None = None, delist: bool = True,
        discover: bool = True, max_sources: int = 70,
        page_budget: int = DEFAULT_PAGE_BUDGET) -> dict:
    """Discover + crawl seller catalogs (with pagination), extract listings, upsert.
    Delist listings from successfully-fetched sources not seen this run."""
    started = _now()
    srcs = list(sources or SEED_SOURCES)
    discovered = 0
    if discover:
        extra = _discover()
        discovered = len(extra)
        seen_urls = set(srcs)
        for u in extra:
            if u not in seen_urls:
                srcs.append(u)
                seen_urls.add(u)
    srcs = srcs[:max_sources]
    added = seen = pages = 0
    visited: set = set()
    budget = [page_budget]
    ok_sites: set[str] = set()
    for url in srcs:
        if budget[0] <= 0:
            break
        a, s, p, ok = _crawl_source(db, url, visited, budget)
        added += a; seen += s; pages += p
        if ok:
            ok_sites.add(urlparse(url).netloc)
    delisted = 0
    if delist:
        from datetime import timedelta
        cutoff = started - timedelta(days=DELIST_AFTER_DAYS)
        stale = db.query(AggregatedListing).filter(
            AggregatedListing.last_seen_at < cutoff,
            AggregatedListing.status == "active",
        ).all()
        for row in stale:
            row.status = "delisted"
            delisted += 1
        db.commit()
    return {"sources": len(srcs), "discovered": discovered, "ok_sites": len(ok_sites),
            "pages": pages, "seen": seen, "added": added, "delisted": delisted}
