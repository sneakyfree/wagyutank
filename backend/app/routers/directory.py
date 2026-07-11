"""The Wagyu Atlas — a public, international directory of genetics sellers.

Aggregates the Roundup's active listings by seller (one entry per source site):
name, country/region, the product lines they offer, how many listings we've
indexed, and a link straight to their own website. Same ethos as the rest of the
Roundup — public facts + attribution + link-back, and NEVER scraped contact info
(no emails/phones). A learner can see who's out there worldwide and click through
to reach them the way each seller intends."""
from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AggregatedListing

router = APIRouter(prefix="/api/directory", tags=["directory"])

_GENERIC = {"www", "shop", "store", "listing", "product", "collections", "en", "us"}


def _pretty(site: str, seller_name: str | None) -> str:
    if seller_name and seller_name.strip():
        return seller_name.strip()
    host = (site or "").lower()
    if host.startswith("www."):
        host = host[4:]
    label = host.split(".")[0] if "." in host else host
    if label in _GENERIC and "." in host:
        label = host.split(".")[1]
    return label.replace("-", " ").replace("_", " ").title() or host


def _sellers(db: Session):
    """One aggregated record per seller (source_site), from active public listings."""
    rows = db.query(AggregatedListing).filter(
        AggregatedListing.status == "active",
        AggregatedListing.flagged == False,  # noqa: E712
    ).all()
    by_site: dict[str, list] = {}
    for r in rows:
        by_site.setdefault(r.source_site, []).append(r)

    out = []
    for site, items in by_site.items():
        countries = Counter(i.country for i in items if i.country)
        regions = Counter(i.region for i in items if i.region)
        names = Counter((i.seller_name or "").strip() for i in items if (i.seller_name or "").strip())
        products = sorted({i.product_type.value for i in items})
        css = any(i.css_status == "css" for i in items)
        sires = []
        for i in items:
            n = (i.animal_name or "").strip()
            if n and n not in sires:
                sires.append(n)
        seller_name = names.most_common(1)[0][0] if names else None
        out.append({
            "site": site,
            "name": _pretty(site, seller_name),
            "url": f"https://{site}",
            "country": countries.most_common(1)[0][0] if countries else None,
            "region": regions.most_common(1)[0][0] if regions else None,
            "products": products,
            "listings": len(items),
            "css_eligible": css,
            "sires": sires[:6],
        })
    out.sort(key=lambda s: s["name"].lower())
    return out


@router.get("")
def directory(
    country: str | None = None,
    region: str | None = None,
    product: str | None = Query(None, description="semen | embryo | clone_rights"),
    q: str | None = None,
    limit: int = Query(60, le=500),
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
    if q:
        ql = q.lower()
        sellers = [s for s in sellers
                   if ql in s["name"].lower() or ql in s["site"].lower()
                   or any(ql in x.lower() for x in s["sires"])]
    total = len(sellers)
    return {"total": total, "sellers": sellers[offset:offset + limit]}


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Facet counts for the Atlas — total sellers, and sellers per country/region."""
    sellers = _sellers(db)
    countries = Counter(s["country"] for s in sellers if s["country"])
    regions = Counter(s["region"] for s in sellers if s["region"])
    products = Counter(p for s in sellers for p in s["products"])
    return {
        "total_sellers": len(sellers),
        "countries": dict(sorted(countries.items())),
        "regions": dict(regions.most_common()),
        "products": dict(products),
        "total_listings": sum(s["listings"] for s in sellers),
    }
