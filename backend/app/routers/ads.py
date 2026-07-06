"""Advertising — house promos + paid ranch/vendor ads placed around the site.

Public: fetch active ads for a placement (rotated client-side), record impressions,
and redirect+count clicks. Advertisers self-submit ads that start `pending` and go
live once approved. Payment is handled off-platform (invoiced) for now."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Ad
from ..schemas import AdOut, AdSubmit
from ..services import payments as pay
from ..services import settings_store

router = APIRouter(prefix="/api/ads", tags=["ads"])

PLACEMENTS = {"feed", "sidebar", "banner"}
TIER_PRICES = {"bronze": 4900, "silver": 9900, "gold": 19900}  # cents / month (regular)
TIER_NAMES = {"bronze": "Bronze", "silver": "Silver", "gold": "Gold"}


def _free_launch() -> bool:
    return bool(settings_store.get("ads_free_launch", settings.ads_free_launch))


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


@router.get("/pricing")
def pricing():
    """Current advertising pricing + whether we're in the free launch window."""
    return {
        "free_launch": _free_launch(),
        "tiers": [{"key": k, "name": TIER_NAMES[k], "price_cents": v,
                   "price_now_cents": 0 if _free_launch() else v}
                  for k, v in TIER_PRICES.items()],
    }


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
    if _free_launch():
        return {"ad_id": ad.id, "free": True, "status": "pending",
                "message": "Thanks! Advertising is free during our launch — your ad is in review "
                           "and we'll email you when it goes live. You're locking in a spot early."}
    return {"ad_id": ad.id, "free": False, "status": "pending",
            "message": "Submitted! Complete checkout to activate your first month."}


@router.post("/{ad_id}/checkout")
def checkout(ad_id: int, db: Session = Depends(get_db)):
    """Self-serve payment for an ad's first month. Free during the launch window;
    otherwise a Stripe PaymentIntent (dev/test-safe fallback when Stripe is off)."""
    ad = db.get(Ad, ad_id)
    if not ad:
        raise HTTPException(404, "Ad not found")
    if _free_launch():
        return {"free": True, "message": "Advertising is free during launch — no payment needed."}
    amount = TIER_PRICES.get(ad.tier or "", TIER_PRICES["bronze"])
    if not pay.stripe_enabled():
        return {"dev_mode": True, "amount_cents": amount, "tier": ad.tier}
    return pay.create_ad_intent(amount_cents=amount, ad_id=ad.id, tier=ad.tier or "bronze")
