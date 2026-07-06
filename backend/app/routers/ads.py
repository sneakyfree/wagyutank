"""Advertising — house promos + paid ranch/vendor ads placed around the site.

Public: fetch active ads for a placement (rotated client-side), record impressions,
and redirect+count clicks. Advertisers self-submit ads that start `pending` and go
live once approved. Payment is handled off-platform (invoiced) for now."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Ad
from ..schemas import AdOut, AdSubmit

router = APIRouter(prefix="/api/ads", tags=["ads"])

PLACEMENTS = {"feed", "sidebar", "banner"}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


@router.get("", response_model=list[AdOut])
def active_ads(placement: str = "feed", limit: int = 6, db: Session = Depends(get_db)):
    """Active ads for a placement (house + paid). Frontend rotates among them."""
    now = _now()
    q = db.query(Ad).filter(
        Ad.status == "active",
        Ad.placement == placement,
        or_(Ad.starts_at == None, Ad.starts_at <= now),   # noqa: E711
        or_(Ad.ends_at == None, Ad.ends_at >= now),       # noqa: E711
    ).order_by(Ad.weight.desc())
    return q.limit(limit).all()


@router.post("/{ad_id}/impression")
def impression(ad_id: int, db: Session = Depends(get_db)):
    ad = db.get(Ad, ad_id)
    if ad:
        ad.impressions += 1
        db.commit()
    return {"ok": True}


@router.get("/{ad_id}/go")
def go(ad_id: int, db: Session = Depends(get_db)):
    ad = db.get(Ad, ad_id)
    if not ad:
        raise HTTPException(404, "Ad not found")
    ad.clicks += 1
    db.commit()
    return RedirectResponse(ad.link_url, status_code=302)


@router.post("/submit")
def submit(payload: AdSubmit, db: Session = Depends(get_db)):
    """Advertiser self-submission — starts pending, reviewed before going live."""
    if payload.placement not in PLACEMENTS:
        raise HTTPException(400, f"placement must be one of {sorted(PLACEMENTS)}")
    ad = Ad(
        advertiser_name=payload.advertiser_name.strip()[:160],
        contact_email=payload.contact_email.strip()[:160],
        headline=payload.headline.strip()[:120],
        body=(payload.body or "").strip()[:300] or None,
        image_url=(payload.image_url or "").strip() or None,
        link_url=payload.link_url.strip()[:600],
        placement=payload.placement,
        tier=payload.tier,
        is_house=False,
        status="pending",
        weight={"gold": 5, "silver": 3, "bronze": 2}.get(payload.tier or "", 1),
    )
    db.add(ad)
    db.commit()
    return {"status": "pending",
            "message": "Thanks! Your ad was submitted for review. We'll email you to confirm "
                       "placement and invoicing before it goes live."}
