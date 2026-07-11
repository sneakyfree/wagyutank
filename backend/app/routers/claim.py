"""Claim-your-listings — the inbound, action-triggered onboarding flow.

When someone signs up with an email on their ranch's own domain (jane@wagyuhof.com)
and we've already indexed listings from wagyuhof.com in the Roundup, the dashboard
offers: "These look like yours — add them to your store?" One click imports them as
native seller listings and retires the Roundup copies.

Deliberately PULL, not push: nothing is ever emailed to non-members, nobody is
contacted — the offer only appears to a person who already chose to create an
account. Security: the import requires a VERIFIED email (the same domain-control
principle as the Roundup takedown flow), so you can't register with a domain you
don't own and scoop up someone else's listings. Free-mail domains never match."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AggregatedListing, Listing, ListingStatus, ProductType, SaleType, User
from ..security import get_current_user
from .aggregated import _registrable

router = APIRouter(prefix="/api/users/me", tags=["claim"])

# Free/shared mail providers can never establish domain ownership of a seller site.
_FREEMAIL = {
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "live.com", "icloud.com",
    "me.com", "aol.com", "protonmail.com", "proton.me", "gmx.com", "gmx.de", "mail.com",
    "msn.com", "yandex.com", "zoho.com", "qq.com", "163.com", "web.de", "t-online.de",
    "bigpond.com", "yahoo.co.jp", "docomo.ne.jp", "ezweb.ne.jp",
}


def _email_domain(user: User) -> str | None:
    email = (user.email or "").lower()
    if "@" not in email:
        return None
    dom = _registrable(email.rsplit("@", 1)[1])
    return None if (not dom or dom in _FREEMAIL) else dom


def _matches(db: Session, dom: str) -> list[AggregatedListing]:
    rows = db.query(AggregatedListing).filter(
        AggregatedListing.status == "active",
        AggregatedListing.flagged == False,  # noqa: E712
    ).all()
    return [r for r in rows if _registrable(r.source_site) == dom]


@router.get("/claimable")
def claimable(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Do we have Roundup listings from this member's own domain?"""
    dom = _email_domain(user)
    if not dom:
        return {"domain": None, "verified": user.is_email_verified, "count": 0, "listings": []}
    rows = _matches(db, dom)
    return {
        "domain": dom,
        "verified": user.is_email_verified,
        "count": len(rows),
        "listings": [{"id": r.id, "title": r.title, "product_type": r.product_type.value,
                      "animal_name": r.animal_name, "price": r.price, "currency": r.currency}
                     for r in rows[:25]],
    }


class ClaimBody(BaseModel):
    listing_ids: list[int] | None = None  # omit = claim all matches


def _qty(text: str | None) -> int:
    try:
        return max(1, int(float(text)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 1


@router.post("/claim")
def claim(payload: ClaimBody, user: User = Depends(get_current_user),
          db: Session = Depends(get_db)):
    """Import matching Roundup listings as this seller's own native listings."""
    dom = _email_domain(user)
    if not dom:
        raise HTTPException(400, "Your account email isn't on a seller-website domain.")
    if not user.is_email_verified:
        raise HTTPException(403, "Verify your email first — we need to confirm you control "
                                 f"an address at {dom} before importing its listings.")
    rows = _matches(db, dom)
    if payload.listing_ids:
        wanted = set(payload.listing_ids)
        rows = [r for r in rows if r.id in wanted]
    if not rows:
        return {"created": 0, "message": "No matching listings to import."}

    # Seller-ready stub (same fallback become-seller uses) so the store works
    # immediately; real Stripe onboarding happens whenever they want payouts.
    if not user.stripe_account_id:
        user.stripe_account_id = f"acct_dev_{user.id}"

    created = 0
    for r in rows:
        db.add(Listing(
            seller_id=user.id,
            product_type=ProductType(r.product_type.value),
            title=r.title[:240],
            description=(r.summary or None),
            animal_reg=(r.animal_reg or None),
            quantity_available=_qty(r.quantity_text),
            sale_type=SaleType.FIXED,
            unit_price=r.price,
            currency=(r.currency or "USD")[:3].upper(),
            css_status=(r.css_status or "unknown"),
            status=ListingStatus.ACTIVE,
        ))
        r.status = "claimed"   # retire the Roundup copy — the native listing replaces it
        created += 1
    db.commit()
    return {"created": created,
            "message": f"Imported {created} listing(s) from {dom} into your store. "
                       f"You can edit prices and details from your dashboard."}
