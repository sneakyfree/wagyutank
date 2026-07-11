"""The Wagyu Atlas — a public, international directory of Wagyu/Akaushi operations.

Two data layers merged by domain:
  1. The REGISTRY (DirectorySeller) — every identified operation with a website,
     seeded from the curated Roundup seed list and enriched from each site's own
     homepage (what they do, breed focus, one-line blurb). This is the full map:
     an operation belongs on the Atlas even when our crawler can't machine-read a
     listings page off its site.
  2. LIVE LISTINGS (AggregatedListing) — sellers whose catalogs we can extract
     get product badges, listing counts, CSS flags, and sample sires on top.

Same ethos as the Roundup: public facts + attribution + link-back, and NEVER
scraped contact info."""
from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AggregatedListing, DirectorySeller

router = APIRouter(prefix="/api/directory", tags=["directory"])

_GENERIC = {"www", "shop", "store", "listing", "product", "collections", "en", "us"}


def _reg(host: str) -> str:
    host = (host or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _pretty(site: str, seller_name: str | None) -> str:
    if seller_name and seller_name.strip():
        return seller_name.strip()
    host = _reg(site)
    label = host.split(".")[0] if "." in host else host
    if label in _GENERIC and "." in host:
        label = host.split(".")[1]
    return label.replace("-", " ").replace("_", " ").title() or host


def _listing_layer(db: Session) -> dict[str, dict]:
    """Aggregate active listings by registrable domain."""
    rows = db.query(AggregatedListing).filter(
        AggregatedListing.status == "active",
        AggregatedListing.flagged == False,  # noqa: E712
    ).all()
    by_dom: dict[str, list] = {}
    for r in rows:
        by_dom.setdefault(_reg(r.source_site), []).append(r)
    out = {}
    for dom, items in by_dom.items():
        countries = Counter(i.country for i in items if i.country)
        regions = Counter(i.region for i in items if i.region)
        names = Counter((i.seller_name or "").strip() for i in items if (i.seller_name or "").strip())
        sires = []
        for i in items:
            n = (i.animal_name or "").strip()
            if n and n not in sires:
                sires.append(n)
        out[dom] = {
            "products": sorted({i.product_type.value for i in items}),
            "listings": len(items),
            "css_eligible": any(i.css_status == "css" for i in items),
            "sires": sires[:6],
            "country": countries.most_common(1)[0][0] if countries else None,
            "region": regions.most_common(1)[0][0] if regions else None,
            "seller_name": names.most_common(1)[0][0] if names else None,
        }
    return out


def _sellers(db: Session) -> list[dict]:
    listings = _listing_layer(db)
    registry = {r.site: r for r in db.query(DirectorySeller)
                .filter(DirectorySeller.status == "active").all()}
    doms = set(listings) | set(registry)
    out = []
    for dom in doms:
        reg = registry.get(dom)
        li = listings.get(dom)
        cats = list(reg.categories or []) if reg else []
        if li and "genetics" not in cats:
            cats = ["genetics"] + cats  # extracted listings = proof they sell genetics
        out.append({
            "site": dom,
            "name": (reg.name if reg and reg.name and not reg.name.islower() else None)
                    or _pretty(dom, (li or {}).get("seller_name") or (reg.name if reg else None)),
            "url": (reg.url if reg else f"https://{dom}"),
            "country": (li or {}).get("country") or (reg.country if reg else None),
            "region": (li or {}).get("region") or (reg.region if reg else None),
            "categories": cats,
            "breeds": list(reg.breeds or []) if reg else [],
            "blurb": (reg.blurb if reg else None),
            "products": (li or {}).get("products", []),
            "listings": (li or {}).get("listings", 0),
            "css_eligible": (li or {}).get("css_eligible", False),
            "sires": (li or {}).get("sires", []),
        })
    out.sort(key=lambda s: ((s["name"] or "").lower(), s["site"]))
    return out


@router.get("")
def directory(
    country: str | None = None,
    region: str | None = None,
    product: str | None = Query(None, description="semen | embryo | clone_rights"),
    category: str | None = Query(None, description="genetics | live_cattle | beef | feedlot | stud_services"),
    breed: str | None = Query(None, description="black_wagyu | akaushi"),
    q: str | None = None,
    limit: int = Query(60, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    sellers = _sellers(db)
    if country:
        sellers = [s for s in sellers if s["country"] == country.upper()]
    if region:
        sellers = [s for s in sellers if s["region"] == region.upper()]
    if product:
        sellers = [s for s in sellers if product in s["products"]]
    if category:
        sellers = [s for s in sellers if category in s["categories"]]
    if breed:
        sellers = [s for s in sellers if breed in s["breeds"]]
    if q:
        ql = q.lower()
        sellers = [s for s in sellers
                   if ql in (s["name"] or "").lower() or ql in s["site"].lower()
                   or ql in (s["blurb"] or "").lower()
                   or any(ql in x.lower() for x in s["sires"])]
    total = len(sellers)
    return {"total": total, "sellers": sellers[offset:offset + limit]}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    sellers = _sellers(db)
    countries = Counter(s["country"] for s in sellers if s["country"])
    regions = Counter(s["region"] for s in sellers if s["region"])
    products = Counter(p for s in sellers for p in s["products"])
    categories = Counter(c for s in sellers for c in s["categories"])
    return {
        "total_sellers": len(sellers),
        "with_listings": sum(1 for s in sellers if s["listings"]),
        "countries": dict(sorted(countries.items())),
        "regions": dict(regions.most_common()),
        "products": dict(products),
        "categories": dict(categories),
        "total_listings": sum(s["listings"] for s in sellers),
    }
