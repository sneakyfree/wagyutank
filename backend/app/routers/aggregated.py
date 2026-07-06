"""The Roundup — public, attributed aggregation of Wagyu-genetics listings found
elsewhere on the web. These are NOT WagyuTank vendor listings; every response
links back to the original source, and there is no on-site checkout."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AggregatedListing, ProductType
from ..schemas import AggregatedOut

router = APIRouter(prefix="/api/roundup", tags=["roundup"])


@router.get("", response_model=list[AggregatedOut])
def browse(
    product_type: ProductType | None = None,
    bloodline: str | None = None,
    region: str | None = Query(None, description="NA/SA/CAM/EU/AU/AS"),
    country: str | None = None,
    css: str | None = Query(None, description="css | domestic"),
    export_to: str | None = Query(None, description="EU/AUS/CAN/... export destination"),
    animal: str | None = Query(None, description="match sire name or registration number"),
    q: str | None = None,
    sort: str = Query("recent", pattern="^(recent|price_asc|price_desc)$"),
    limit: int = Query(40, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(AggregatedListing).filter(
        AggregatedListing.status == "active", AggregatedListing.flagged == False  # noqa: E712
    )
    if product_type:
        query = query.filter(AggregatedListing.product_type == product_type)
    if bloodline:
        query = query.filter(AggregatedListing.bloodline == bloodline)
    if region:
        query = query.filter(AggregatedListing.region == region.upper())
    if country:
        query = query.filter(AggregatedListing.country == country.upper())
    if css in ("css", "domestic"):
        query = query.filter(AggregatedListing.css_status == css)
    if animal:
        like = f"%{animal.lower()}%"
        query = query.filter(or_(
            func.lower(AggregatedListing.animal_name).like(like),
            func.lower(AggregatedListing.animal_reg).like(like),
        ))
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(
            func.lower(AggregatedListing.title).like(like),
            func.lower(AggregatedListing.seller_name).like(like),
        ))
    if sort == "price_asc":
        query = query.order_by(AggregatedListing.price.asc().nullslast())
    elif sort == "price_desc":
        query = query.order_by(AggregatedListing.price.desc().nullslast())
    else:
        query = query.order_by(AggregatedListing.last_seen_at.desc())
    rows = query.offset(offset).limit(limit if not export_to else 200).all()
    if export_to:
        dest = export_to.upper()
        rows = [r for r in rows if dest in (r.export_regions or [])][:limit]
    return rows


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    active = AggregatedListing.status == "active"
    base = db.query(AggregatedListing).filter(active, AggregatedListing.flagged == False)  # noqa: E712
    sites = [s[0] for s in db.query(AggregatedListing.source_site).filter(active).distinct()]
    regions = dict(
        db.query(AggregatedListing.region, func.count())
        .filter(active, AggregatedListing.region != None)  # noqa: E711
        .group_by(AggregatedListing.region).all()
    )
    countries = sorted(c[0] for c in db.query(AggregatedListing.country)
                       .filter(active, AggregatedListing.country != None).distinct() if c[0])  # noqa: E711
    css_export = base.filter(AggregatedListing.css_status == "css").count()
    return {"active": base.count(), "sources": len(sites), "sites": sorted(sites),
            "regions": regions, "countries": countries, "css_export_eligible": css_export}


@router.get("/{listing_id}/go")
def go(listing_id: int, db: Session = Depends(get_db)):
    """Count the outbound click and redirect to the original listing."""
    row = db.get(AggregatedListing, listing_id)
    if not row:
        raise HTTPException(404, "Listing not found")
    row.outbound_clicks += 1
    db.commit()
    return RedirectResponse(row.source_url, status_code=302)


@router.post("/{listing_id}/flag")
def flag(listing_id: int, db: Session = Depends(get_db)):
    """Opt-out / removal request — a seller (or anyone) can flag a Roundup listing
    to have it hidden pending review."""
    row = db.get(AggregatedListing, listing_id)
    if not row:
        raise HTTPException(404, "Listing not found")
    row.flagged = True
    row.status = "hidden"
    db.commit()
    return {"status": "flagged", "message": "Listing hidden pending review. Thank you."}
