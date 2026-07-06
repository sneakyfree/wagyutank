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
    return query.offset(offset).limit(limit).all()


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    base = db.query(AggregatedListing).filter(
        AggregatedListing.status == "active", AggregatedListing.flagged == False  # noqa: E712
    )
    sites = [s[0] for s in db.query(AggregatedListing.source_site).filter(
        AggregatedListing.status == "active").distinct()]
    return {"active": base.count(), "sources": len(sites), "sites": sorted(sites)}


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
