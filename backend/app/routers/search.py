from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

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
    min_price: float | None = None,
    max_price: float | None = None,
    sort: str = Query("newest", pattern="^(newest|price_asc|price_desc|ending_soon)$"),
    limit: int = Query(30, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Faceted marketplace search (§11). Bloodline/breed facets join the canonical Animal."""
    query = db.query(Listing).filter(Listing.status == ListingStatus.ACTIVE)

    if product_type:
        query = query.filter(Listing.product_type == product_type)
    if sale_type:
        query = query.filter(Listing.sale_type == sale_type)
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

    if sort == "price_asc":
        query = query.order_by(Listing.unit_price.asc().nullslast())
    elif sort == "price_desc":
        query = query.order_by(Listing.unit_price.desc().nullslast())
    elif sort == "ending_soon":
        query = query.order_by(Listing.ends_at.asc().nullslast())
    else:
        query = query.order_by(Listing.featured_until.desc().nullslast(), Listing.created_at.desc())

    rows = query.offset(offset).limit(limit).all()
    if export:
        rows = [r for r in rows if export in (r.export_eligibility or [])]
    return [to_listing_out(x) for x in rows]


@router.get("/facets")
def facets(db: Session = Depends(get_db)):
    """Available facet values for the search UI."""
    bloodlines = [b[0] for b in db.query(Animal.bloodline).distinct() if b[0]]
    return {
        "product_types": [p.value for p in ProductType],
        "bloodlines": sorted(bloodlines),
        "sale_types": [s.value for s in SaleType],
        "export_regions": ["AUS", "EU", "CAN", "US"],
        "sorts": ["newest", "price_asc", "price_desc", "ending_soon"],
    }
