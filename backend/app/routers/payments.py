from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Listing, ListingStatus, Order, SaleType, User
from ..security import get_current_user
from ..services import payments as pay

router = APIRouter(prefix="/api/payments", tags=["payments"])

# Flat featured prices in cents (MASTER_PLAN §15 placeholders).
FEATURE_PRICES = {7: 1900, 14: 3400, 30: 6500}


@router.get("/config")
def config():
    return {
        "stripe_enabled": pay.stripe_enabled(),
        "publishable_key": settings.stripe_publishable_key,
        "platform_fee_bps": settings.platform_fee_bps,
        "feature_prices_cents": FEATURE_PRICES,
    }


@router.get("/quote/{listing_id}")
def quote(listing_id: int, db: Session = Depends(get_db)):
    """Show the buyer the grossed-up total before they commit."""
    li = db.get(Listing, listing_id)
    if not li or li.unit_price is None:
        raise HTTPException(404, "Listing not found or has no price.")
    return pay.compute_amounts(round(li.unit_price * 100))


@router.post("/connect/onboard")
def onboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Create/continue Stripe Connect Express onboarding (payout + KYC)."""
    if not pay.stripe_enabled():
        # Dev fallback so the flow works without Stripe configured.
        if not user.stripe_account_id:
            user.stripe_account_id = f"acct_dev_{user.id}"
            db.commit()
        return {"onboarding_url": None, "dev_mode": True, "account_id": user.stripe_account_id}
    if not user.stripe_account_id:
        user.stripe_account_id = pay.create_express_account(user.email, user.country or "US")
        db.commit()
    base = settings.frontend_origin
    url = pay.create_onboarding_link(
        user.stripe_account_id,
        return_url=f"{base}/dashboard?onboarded=1",
        refresh_url=f"{base}/dashboard?refresh=1",
    )
    return {"onboarding_url": url, "account_id": user.stripe_account_id}


def _reject_if_beef(li: Listing) -> None:
    """Beef is discovery-only — no on-platform checkout (avoids USDA/food-safety
    liability). Enforced server-side so it can't be bypassed by a crafted request."""
    from .. import tank
    if tank.product_family(getattr(li.product_type, "value", li.product_type)) == "beef":
        raise HTTPException(400, "Beef listings are contact-the-producer only — reach out to the seller directly to buy.")


@router.post("/buy/{listing_id}")
def buy(listing_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    li = db.get(Listing, listing_id)
    if not li or li.status != ListingStatus.ACTIVE:
        raise HTTPException(404, "Listing not available.")
    _reject_if_beef(li)
    if li.is_sample:
        raise HTTPException(400, "This is a sample listing — it shows what your ad will look like and can't be purchased.")
    if li.sale_type != SaleType.FIXED or li.unit_price is None:
        raise HTTPException(400, "This listing is not a fixed-price purchase.")
    if li.seller_id == user.id:
        raise HTTPException(400, "You can't buy your own listing.")
    seller = db.get(User, li.seller_id)

    price_cents = round(li.unit_price * 100)
    if not pay.stripe_enabled():
        amounts = pay.compute_amounts(price_cents)
        # Test mode has no real payment confirmation — mark the order complete so the
        # post-purchase rating flow works end to end.
        order = Order(listing_id=li.id, buyer_id=user.id, seller_id=li.seller_id,
                      amount_cents=amounts["buyer_total_cents"], application_fee_cents=amounts["application_fee_cents"],
                      currency=li.currency, status="paid")
        db.add(order); db.commit()
        return {"dev_mode": True, "order_id": order.id, **amounts}

    if not seller.stripe_account_id or not pay.account_charges_enabled(seller.stripe_account_id):
        raise HTTPException(400, "Seller has not completed payout onboarding yet.")

    res = pay.create_buy_intent(
        price_cents=price_cents, currency=li.currency,
        seller_account=seller.stripe_account_id, listing_id=li.id, buyer_id=user.id,
    )
    order = Order(listing_id=li.id, buyer_id=user.id, seller_id=li.seller_id,
                  amount_cents=res["buyer_total_cents"], application_fee_cents=res["application_fee_cents"],
                  currency=li.currency, stripe_payment_intent=res["payment_intent"], status="pending")
    db.add(order); db.commit()
    return res


@router.post("/feature/{listing_id}")
def feature_checkout(listing_id: int, days: int = 7, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    li = db.get(Listing, listing_id)
    if not li or li.seller_id != user.id:
        raise HTTPException(404, "Listing not found.")
    amount = FEATURE_PRICES.get(days)
    if amount is None:
        raise HTTPException(400, "Choose 7, 14, or 30 days.")
    if not pay.stripe_enabled():
        return {"dev_mode": True, "amount_cents": amount, "days": days}
    return pay.create_feature_intent(amount_cents=amount, listing_id=li.id, days=days)


@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    import stripe
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    if settings.stripe_webhook_secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
        except Exception:
            raise HTTPException(400, "Invalid signature")
    else:
        import json
        event = json.loads(payload or b"{}")  # dev: accept unsigned

    etype = event.get("type") if isinstance(event, dict) else event["type"]
    obj = (event.get("data", {}) or {}).get("object", {}) if isinstance(event, dict) else event["data"]["object"]

    if etype == "payment_intent.succeeded":
        pi = obj.get("id")
        order = db.query(Order).filter(Order.stripe_payment_intent == pi).first()
        if order:
            order.status = "paid"
            li = db.get(Listing, order.listing_id)
            meta = obj.get("metadata", {}) or {}
            if meta.get("kind") == "feature" and li:
                from datetime import datetime, timedelta, timezone
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                base = li.featured_until if (li.featured_until and li.featured_until > now) else now
                li.featured_until = base + timedelta(days=int(meta.get("days", 7)))
            elif li:
                li.status = ListingStatus.SOLD
            db.commit()
    return {"received": True}
