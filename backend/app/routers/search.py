from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import tank
from ..db import get_db
from ..models import Animal, Listing, ListingStatus, ProductType, SaleType
from ..schemas import ListingOut
from .listings import to_listing_out

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=list[ListingOut])
def search(
    q: str | None = None,
    product_type: ProductType | None = None,
    bloodline: str | None = None,
    breed: str | None = None,
    sale_type: SaleType | None = None,
    export: str | None = Query(None, description="Export-eligibility code e.g. AUS/EU/CAN"),
    state: str | None = Query(None, description="State/region filter (live/beef tanks)"),
    near_postal: str | None = Query(None, description="Center a radius search on this postal code"),
    radius_miles: int = Query(100, ge=10, le=2000),
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = Query("newest", pattern="^(newest|price_asc|price_desc|ending_soon|nearest)$"),
    limit: int = Query(30, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Faceted marketplace search (§11). Bloodline/breed facets join the canonical
    Animal; state/near_postal power the location search on live-cattle/beef tanks."""
    query = db.query(Listing).filter(Listing.status == ListingStatus.ACTIVE)

    if product_type:
        query = query.filter(Listing.product_type == product_type)
    if sale_type:
        query = query.filter(Listing.sale_type == sale_type)
    if state:
        query = query.filter(func.lower(Listing.state_region) == state.lower())
    if min_price is not None:
        query = query.filter(Listing.unit_price >= min_price)
    if max_price is not None:
        query = query.filter(Listing.unit_price <= max_price)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(func.lower(Listing.title).like(like))

    # Bloodline / breed live on the canonical Animal — join by registration number.
    if bloodline or breed:
        query = query.join(Animal, func.lower(Animal.registration_no) == func.lower(Listing.animal_reg))
        if bloodline:
            query = query.filter(Animal.bloodline == bloodline)
        if breed:
            query = query.filter(Animal.breed == breed)

    # Radius search: resolve the center postal → centroid, bounding-box prefilter in
    # SQL, then exact haversine + distance-sort in Python on the small candidate set.
    center = _postal_centroid(db, near_postal) if near_postal else None
    if center:
        clat, clng = center
        dlat = radius_miles / 69.0
        dlng = radius_miles / max(1.0, 69.0 * _cos_deg(clat))
        query = query.filter(
            Listing.lat.isnot(None),
            Listing.lat.between(clat - dlat, clat + dlat),
            Listing.lng.between(clng - dlng, clng + dlng),
        )

    if sort == "price_asc":
        query = query.order_by(Listing.unit_price.asc().nullslast())
    elif sort == "price_desc":
        query = query.order_by(Listing.unit_price.desc().nullslast())
    elif sort == "ending_soon":
        query = query.order_by(Listing.ends_at.asc().nullslast())
    elif sort == "nearest" and center:
        pass  # sorted below by computed distance
    else:
        query = query.order_by(Listing.featured_until.desc().nullslast(), Listing.created_at.desc())

    if center:
        # pull candidates within the bbox, compute exact distance, filter to radius, sort
        cands = query.limit(2000).all()
        scored = []
        for r in cands:
            d = _haversine_miles(center[0], center[1], r.lat, r.lng)
            if d <= radius_miles:
                scored.append((d, r))
        scored.sort(key=lambda x: x[0])
        outs = []
        for d, r in scored[offset:offset + limit]:
            o = to_listing_out(r)
            o.distance_miles = round(d, 1)
            outs.append(o)
        if export:
            outs = [o for o, (_, r) in zip(outs, scored[offset:offset + limit]) if export in (r.export_eligibility or [])]
        return outs

    rows = query.offset(offset).limit(limit).all()
    if export:
        rows = [r for r in rows if export in (r.export_eligibility or [])]
    return [to_listing_out(x) for x in rows]


def _postal_centroid(db: Session, postal: str) -> tuple[float, float] | None:
    from ..models import GeoPostal
    p = (postal or "").strip()
    if not p:
        return None
    row = db.query(GeoPostal).filter(GeoPostal.postal == p).first()
    return (row.lat, row.lng) if row else None


def _cos_deg(deg: float) -> float:
    import math
    return max(0.01, abs(math.cos(math.radians(deg))))


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math
    r = 3958.8  # earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(min(1.0, math.sqrt(a)))


@router.get("/facets")
def facets(db: Session = Depends(get_db)):
    """Available facet values for the search UI."""
    bloodlines = [b[0] for b in db.query(Animal.bloodline).distinct() if b[0]]
    # Only THIS tank's product types — the full enum would leak other verticals'
    # families (live_animal/beef) into every genetics tank's browse UI.
    tank_keys = tank.product_keys()
    return {
        "product_types": [p.value for p in ProductType if p.value in tank_keys],
        "bloodlines": sorted(bloodlines),
        "sale_types": [s.value for s in SaleType],
        "export_regions": ["AUS", "EU", "CAN", "US"],
        "sorts": ["newest", "price_asc", "price_desc", "ending_soon"],
    }
