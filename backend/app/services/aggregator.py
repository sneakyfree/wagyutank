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
import os
import re
import time
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

MAX_PAGES_PER_SITE = 6   # follow pagination up to this many pages per catalog
DEFAULT_PAGE_BUDGET = 220  # global cap on total page fetches per run (politeness + runtime)
DELIST_AFTER_DAYS = 10   # grace period — must exceed the WEEKLY JS-render crawl
                         # cycle (7d), or JS-only listings get aged out Fri/Sat and
                         # resurrected each Sunday (a sawtooth). 10d gives a full
                         # cycle plus slack. The reaper (jobs.reap_links) handles
                         # genuinely-dead links faster via direct HTTP checks.

import httpx

from ..models import AggregatedListing, ProductType
from .ai import chat
from .. import tank


def _breed_terms() -> list[str]:
    """Lowercased relevance words for THIS tank's breed — the words a seller page
    must mention to count as on-breed (wagyu: wagyu/akaushi; murray grey: murray
    grey; …). Built from the brand breed + vocab search terms."""
    b = tank.brand()
    words = set()
    breed = (b.get("breed") or "Wagyu")
    for part in breed.replace("&", "/").split("/"):
        part = part.strip().lower()
        # drop parenthetical qualifiers: "Akaushi (Japanese Red)" → "akaushi"
        part = part.split("(")[0].strip()
        if part:
            words.add(part)
    for term in (tank.vocab().get("news_search_terms") or []):
        term = term.strip().lower()
        if term:
            words.add(term)
    return sorted(words)


def _breed_short() -> str:
    return (tank.brand().get("breed") or "Wagyu").split(" & ")[0].strip()


def USER_AGENT() -> str:
    b = tank.brand()
    return f"{b.get('name', 'WagyuTank')}Bot/1.0 (+https://www.{b.get('domain', 'wagyutank.com')}/roundup; aggregator)"
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

# Extra seed URLs discovered offline (residential IP) and committed to the repo,
# because search engines block the VPS's datacenter IP. Refreshed periodically.
_SEED_FILE = os.path.join(os.path.dirname(__file__), "seed_sources.json")


def _load_seed_file() -> list[str]:
    try:
        with open(_SEED_FILE) as f:
            data = json.load(f)
        return [u for u in data if isinstance(u, str) and u.startswith("http")]
    except Exception:
        return []

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


def _parse_date(s) -> datetime | None:
    """Parse an ISO / HTTP-date / YYYY-MM string into a naive UTC datetime."""
    if not s or not isinstance(s, str):
        return None
    s = s.strip()
    # ISO 8601 (Shopify updated_at, schema.org dateModified)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        pass
    # HTTP Last-Modified (RFC 2822)
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt:
            return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y/%m/%d", "%m/%d/%Y", "%B %Y", "%b %Y", "%d %B %Y", "%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _robots_ok(url: str) -> bool:
    try:
        p = urlparse(url)
        rp = RobotFileParser()
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(USER_AGENT(), url)
    except Exception:
        # If robots is unreadable, be conservative but not blocking: allow.
        return True


def _fetch(url: str) -> tuple[str | None, datetime | None]:
    """Return (html, last_modified) — last_modified from the HTTP header if present."""
    try:
        r = httpx.get(url, headers={"User-Agent": USER_AGENT()},
                      timeout=25, follow_redirects=True)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            return r.text, _parse_date(r.headers.get("last-modified"))
    except Exception:
        pass
    return None, None


def _classify_product(text: str) -> str | None:
    t = (text or "").lower()
    if any(w in t for w in ("embryo", "ivf", "ivp")):
        return "embryo"
    if any(w in t for w in ("clone", "cloning", "cell line", "cell-line")):
        return "clone_rights"
    if any(w in t for w in ("semen", "straw", "sire", " ai ", "insemination")):
        return "semen"
    return None


def _clean_animal_name(title: str) -> str | None:
    breed_alt = "|".join(re.escape(w) for w in _breed_terms()) or "wagyu"
    name = re.sub(r"(?i)\b(frozen|" + breed_alt + r"|red|fullblood|full[- ]?blood|semen|straws?|"
                  r"embryos?|ivf|for sale|genetics?|sexed|conventional|per|each|unit)\b", " ", title)
    name = re.sub(r"[\-–|•,/]+", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -–|")
    return name or None


def _shopify_products(base_url: str) -> list[dict] | None:
    """Fast-path for Shopify stores: /products.json is structured — no LLM needed.
    Returns listing dicts (each with a `_url`), or None if the site isn't Shopify."""
    p = urlparse(base_url)
    root = f"{p.scheme}://{p.netloc}"
    tld = p.netloc.rsplit(".", 1)[-1].lower()
    country = _TLD_COUNTRY.get(tld)
    listings: list[dict] = []
    for page in range(1, 6):
        try:
            r = httpx.get(f"{root}/products.json", params={"limit": 250, "page": page},
                          headers={"User-Agent": USER_AGENT()}, timeout=20, follow_redirects=True)
            if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
                return None if page == 1 else listings
            prods = r.json().get("products", [])
        except Exception:
            return None if page == 1 else listings
        if not prods:
            break
        for pr in prods:
            title = (pr.get("title") or "").strip()
            title_l = title.lower()
            tags = " ".join(pr.get("tags", []) if isinstance(pr.get("tags"), list) else [str(pr.get("tags", ""))])
            body = re.sub(r"<[^>]+>", " ", pr.get("body_html") or "")
            # relevance can look at the body; classification must not (avoids false positives)
            if not any(w in f"{title_l} {tags} {body}".lower() for w in _breed_terms()):
                continue
            # hard-exclude live-animal listings even if the title also mentions embryo/semen
            if any(p in title_l for p in ("cows & heifers", "cows and heifers", "heifers for sale",
                                          "cows for sale", "bulls for sale", "cattle for sale",
                                          "live cattle", "bred heifer", "bred cow")):
                continue
            # exclude live animals + beef/meat unless the title itself names a genetics product
            has_genetics_word = any(g in title_l for g in ("semen", "embryo", "straw", "ivf", "clone"))
            if not has_genetics_word and any(w in title_l for w in (
                    "heifer", "cow", "calf", "steer", "bull for sale", "bred female", "live ",
                    "beef", "meat", "brisket", "ribeye", "steak", "ground", "roast", "freezer")):
                continue
            # classify from title + tags + shopify's product_type only (never the body)
            ptype = _classify_product(f"{title_l} {tags} {pr.get('product_type', '')}")
            if not ptype:
                continue
            price = None
            for v in (pr.get("variants") or []):
                try:
                    price = float(v.get("price"))
                    break
                except (TypeError, ValueError):
                    continue
            listings.append({
                "product_type": ptype, "title": title, "animal_name": _clean_animal_name(title),
                "registration_no": None, "bloodline": None, "price": price,
                "price_unit": "straw" if ptype == "semen" else ("embryo" if ptype == "embryo" else None),
                "currency": "USD", "quantity": None, "seller_name": pr.get("vendor") or None,
                "location": None, "country": country, "css_status": "unknown", "export_regions": [],
                "_url": f"{root}/products/{pr.get('handle')}",
                "_updated_at": _parse_date(pr.get("updated_at")), "_date_type": "shopify",
            })
        time.sleep(1)
    return listings


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
    return text[:9000]


def _extract_system() -> str:
    breed_u = " / ".join(w.upper() for w in _breed_terms()) or "WAGYU"
    pkeys = "|".join(f"'{k}'" for k in sorted(tank.product_keys())) or "'semen'|'embryo'"
    plabels = ", ".join(p.get("label", "").lower() for p in tank.products() if p.get("label"))
    return (
    f"You extract structured facts about FROZEN {breed_u} GENETICS for sale ({plabels or 'semen straws, embryos'}) "
    "from a web page's text. Return ONLY a JSON array. "
    "Each element: {product_type: " + pkeys + ", animal_name, registration_no, "
    "bloodline, price (number or null), price_unit, currency, quantity, seller_name, location, "
    "country (ISO 2-letter), css_status ('css' if the page says CSS/Certified Semen Services or "
    "export-eligible; 'domestic' if it says domestic-only/non-CSS; else 'unknown'), "
    "export_regions (array from ['EU','AUS','CAN','MEX','BR','UK','CN','NZ','JP'] — only the "
    "destinations the page explicitly says it's export-eligible to; [] if unstated), "
    "listing_date (if the ad states when it was posted/updated, as ISO 'YYYY-MM-DD' or "
    "'YYYY-MM'; else null — do NOT guess)}. "
    f"Include ONLY genuine for-sale {_breed_short()} genetics listings — skip live animals, meat "
    f"products, general info, and non-{_breed_short()} breeds. If the page has none, return []. "
    "Never invent data; use null/'unknown'/[] for anything not stated."
    )


_LAST_LLM = [0.0]      # global throttle — free-tier LLMs cap tokens/minute
MIN_LLM_GAP = 5.0      # min seconds between extraction calls


def _extract(text: str, source_url: str) -> list[dict]:
    if not text:
        return []
    out = None
    for attempt in range(2):  # free-tier LLMs rate-limit under load; back off once
        gap = MIN_LLM_GAP - (time.monotonic() - _LAST_LLM[0])
        if gap > 0:
            time.sleep(gap)
        try:
            out = chat(_extract_system(), f"Page URL: {source_url}\n\nPage text:\n{text}", max_tokens=3200)
            _LAST_LLM[0] = time.monotonic()
            break
        except Exception:
            _LAST_LLM[0] = time.monotonic()
            if attempt == 0:
                time.sleep(15)
            else:
                return []
    if not out:
        return []
    # Pull the first JSON array out of the response.
    m = re.search(r"\[.*\]", out, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    for item in data:
        if not isinstance(item, dict):
            continue
        # LLMs sometimes return a scalar text field as a list (e.g. bloodline
        # ["Tajima","Fujiyoshi"]) — SQLite can't bind a list, so coerce every
        # free-text field to a plain string before it reaches the ORM.
        for f in ("animal_name", "registration_no", "bloodline", "seller_name",
                  "location", "price_unit", "currency", "title", "quantity", "product_type"):
            v = item.get(f)
            if isinstance(v, list):
                item[f] = ", ".join(str(x).strip() for x in v if x not in (None, "")) or None
            elif isinstance(v, dict):
                item[f] = None
        if item.get("listing_date"):
            dt = _parse_date(item["listing_date"])
            if dt:
                item["_updated_at"] = dt
                item["_date_type"] = "stated"
    return data


def _product(pt: str | None) -> ProductType | None:
    try:
        return ProductType((pt or "").strip().lower())
    except ValueError:
        return None


def _dedup_key(source_url: str, product: str, animal: str, price) -> str:
    raw = f"{source_url}|{product}|{(animal or '').lower().strip()}|{price}"
    return hashlib.sha1(raw.encode()).hexdigest()[:40]


def _title(animal: str | None, product: ProductType, seller: str | None) -> str:
    name = animal or _breed_short()
    label = _PRODUCT_LABEL[product.value]
    return f"{name} {label}" + (f" — {seller}" if seller else "")


def _summary(li: dict, animal: str | None, product: ProductType) -> str:
    bits = []
    qty = li.get("quantity")
    try:
        qn = int(float(qty)) if qty not in (None, "") else None
    except (TypeError, ValueError):
        qn = None
    singular = {"semen": "semen straw", "embryo": "embryo", "clone_rights": "cloning right"}[product.value]
    plural = {"semen": "semen straws", "embryo": "embryos", "clone_rights": "cloning rights"}[product.value]
    noun = singular if qn == 1 else plural
    lead = f"{qn} " if qn else ""
    reg = f" ({li['registration_no']})" if li.get("registration_no") else ""
    bits.append(f"{lead}{noun} from {animal or f'a {_breed_short()} sire'}{reg}.")
    if li.get("bloodline"):
        bits.append(f"{li['bloodline']} bloodline.")
    if li.get("seller_name"):
        loc = f" in {li['location']}" if li.get("location") else ""
        bits.append(f"Listed by {li['seller_name']}{loc}.")
    price = li.get("price")
    if price not in (None, "", 0):
        cur = li.get("currency") or "USD"
        unit = f" {li['price_unit']}" if li.get("price_unit") else ""
        bits.append(f"Asking {cur} {price}{unit}.")
    return " ".join(bits)


_COUNTRY_ALIAS = {"UK": "GB", "EN": "GB", "UAE": "AE"}


def _country_region(li: dict, source_site: str) -> tuple[str | None, str | None]:
    country = (li.get("country") or "").strip().upper()[:2] or None
    country = _COUNTRY_ALIAS.get(country, country)
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
    updated_at = li.get("_updated_at") if isinstance(li.get("_updated_at"), datetime) else None
    date_type = li.get("_date_type")
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
        if updated_at and (not row.source_updated_at or updated_at > row.source_updated_at):
            row.source_updated_at = updated_at
            row.source_date_type = date_type
        return False
    db.add(AggregatedListing(
        dedup_key=key, product_type=product,
        title=(li.get("title") or _title(animal, product, li.get("seller_name")))[:240],
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
        source_updated_at=updated_at, source_date_type=date_type,
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
    added = seen = pages = 0
    ok = False

    # Fast-path: Shopify stores expose structured /products.json — no LLM, no rate limit.
    try:
        if _robots_ok(start_url):
            shop = _shopify_products(start_url)
            budget[0] -= 1
            if shop is not None:  # confirmed Shopify
                ok = True
                for li in shop:
                    seen += 1
                    url = li.pop("_url", start_url)
                    if _upsert(db, li, url, site):
                        added += 1
                db.commit()
                time.sleep(1.5)
                return added, seen, 1, ok
    except Exception:
        db.rollback()

    queue = [start_url]
    while queue and pages < MAX_PAGES_PER_SITE and budget[0] > 0:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            if not _robots_ok(url):
                continue
            html, last_mod = _fetch(url)
            budget[0] -= 1
            pages += 1
            if not html:
                continue
            ok = True
            for li in _extract(_html_to_text(html), url):
                seen += 1
                # freshness: prefer a date stated in the ad, else the page's Last-Modified
                if not li.get("_updated_at") and last_mod:
                    li["_updated_at"] = last_mod
                    li["_date_type"] = "page-header"
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


def ingest_rendered_pages(db, pages: list[dict]) -> dict:
    """Ingest pages already rendered by the JS crawler (Playwright on Windy 0).

    Each page = {source_url, source_site, text}. The crawler renders the
    JavaScript that static fetch can't see; here we reuse the same LLM
    extraction + upsert path (facts + our neutral summary + link-back — never
    the seller's ad copy or images), so SPA seller catalogs finally flow into
    the Roundup. Sources touched this run are recorded so delisting still works.
    """
    from sqlalchemy.exc import IntegrityError

    from . import health
    added = seen = 0
    touched_sites: dict[str, int] = {}
    for pg in pages:
        url = (pg.get("source_url") or "").strip()
        site = (pg.get("source_site") or urlparse(url).netloc).strip()
        text = pg.get("text") or ""
        if not url or len(text) < 60:
            continue
        for li in _extract(text[:16000], url):
            seen += 1
            # A savepoint per listing: if the LLM repeats a listing (identical
            # dedup_key) the collision rolls back only this row, never the whole
            # job — one dup used to abort the entire ingest mid-run.
            try:
                with db.begin_nested():
                    created = _upsert(db, li, url, site)
                if created:
                    added += 1
                    touched_sites[site] = touched_sites.get(site, 0) + 1
            except Exception:
                # Any malformed row (dup dedup_key, bad LLM data type, …) rolls
                # back only this savepoint — never aborts the whole batch.
                pass
        db.commit()
    for site, n in touched_sites.items():
        try:
            health.record_source(db, f"roundup:{site}", "roundup_source", f"{site} (JS)", n)
        except Exception:
            pass
    return {"pages": len(pages), "seen": seen, "added": added, "sites": len(touched_sites)}


def run(db, sources: list[str] | None = None, delist: bool = True,
        discover: bool = True, max_sources: int = 70,
        page_budget: int = DEFAULT_PAGE_BUDGET) -> dict:
    """Discover + crawl seller catalogs (with pagination), extract listings, upsert.
    Delist listings from successfully-fetched sources not seen this run."""
    started = _now()
    if sources is not None:
        srcs = list(sources)
    else:
        srcs = list(dict.fromkeys(SEED_SOURCES + _load_seed_file()))  # dedupe, keep order
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
    from . import health
    ok_sites: set[str] = set()
    for url in srcs:
        if budget[0] <= 0:
            break
        a, s, p, ok = _crawl_source(db, url, visited, budget)
        added += a; seen += s; pages += p
        site = urlparse(url).netloc
        if ok:
            ok_sites.add(site)
        try:
            health.record_source(db, f"roundup:{site}", "roundup_source", site, s)
        except Exception:
            pass
    delisted = 0
    if delist and ok_sites:
        # Only age out listings from sources we SUCCESSFULLY fetched this run. A
        # site we couldn't reach (JS-only site on the static daily run, or one
        # that was simply down) must never have its listings delisted — otherwise
        # every source this crawler can't see would vanish. Scoping to ok_sites
        # is what makes "delisted = the listing genuinely disappeared from a live
        # source" true, and is the other half (with the 10d cutoff) of the
        # sawtooth fix.
        from datetime import timedelta
        cutoff = started - timedelta(days=DELIST_AFTER_DAYS)
        stale = db.query(AggregatedListing).filter(
            AggregatedListing.last_seen_at < cutoff,
            AggregatedListing.status == "active",
            AggregatedListing.source_site.in_(ok_sites),
        ).all()
        for row in stale:
            row.status = "delisted"
            delisted += 1
        db.commit()
    return {"sources": len(srcs), "discovered": discovered, "ok_sites": len(ok_sites),
            "pages": pages, "seen": seen, "added": added, "delisted": delisted}
