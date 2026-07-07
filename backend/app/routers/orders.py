"""Orders + the dual buyer/seller rating flow (eBay-style reputation)."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Feedback, Listing, Order, User
from ..security import get_current_user

router = APIRouter(prefix="/api/orders", tags=["orders"])


def _recompute(db: Session, ratee_id: int, role: str):
    fbs = db.query(Feedback).filter(Feedback.ratee_id == ratee_id, Feedback.ratee_role == role).all()
    avg = round(sum(f.score for f in fbs) / len(fbs), 2) if fbs else 0.0
    u = db.get(User, ratee_id)
    if not u:
        return
    if role == "seller":
        u.seller_rating, u.seller_rating_count = avg, len(fbs)
    else:
        u.buyer_rating, u.buyer_rating_count = avg, len(fbs)
    db.commit()


@router.get("/mine")
def my_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    orders = (db.query(Order)
              .filter(or_(Order.buyer_id == user.id, Order.seller_id == user.id),
                      Order.status == "paid", Order.kind == "purchase")
              .order_by(Order.created_at.desc()).limit(50).all())
    out = []
    for o in orders:
        is_buyer = o.buyer_id == user.id
        counter_id = o.seller_id if is_buyer else o.buyer_id
        counter = db.get(User, counter_id)
        listing = db.get(Listing, o.listing_id)
        rated = db.query(Feedback).filter_by(
            rater_id=user.id, ratee_id=counter_id, listing_id=o.listing_id).first() is not None
        out.append({
            "order_id": o.id, "role": "buyer" if is_buyer else "seller",
            "counterparty": counter.display_name if counter else "—",
            "counterparty_handle": counter.handle if counter else None,
            "rate_role": "seller" if is_buyer else "buyer",  # what you'd be rating them as
            "listing_title": listing.title if listing else "Listing",
            "amount_cents": o.amount_cents, "currency": o.currency,
            "created_at": o.created_at, "rated": rated,
        })
    return out


@router.post("/{order_id}/rate")
def rate(order_id: int, score: int = Body(..., embed=True), comment: str | None = Body(None),
         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o or o.status != "paid":
        raise HTTPException(404, "Order not found or not complete.")
    if user.id not in (o.buyer_id, o.seller_id):
        raise HTTPException(403, "Not your order.")
    if not (1 <= score <= 5):
        raise HTTPException(400, "Score must be 1–5.")
    is_buyer = user.id == o.buyer_id
    ratee_id = o.seller_id if is_buyer else o.buyer_id
    ratee_role = "seller" if is_buyer else "buyer"
    if db.query(Feedback).filter_by(rater_id=user.id, ratee_id=ratee_id, listing_id=o.listing_id).first():
        raise HTTPException(400, "You've already rated this order.")
    db.add(Feedback(listing_id=o.listing_id, rater_id=user.id, ratee_id=ratee_id,
                    ratee_role=ratee_role, score=score, comment=(comment or "").strip() or None))
    db.commit()
    _recompute(db, ratee_id, ratee_role)
    return {"ok": True}


@router.get("/user/{handle}/reviews")
def user_reviews(handle: str, db: Session = Depends(get_db)):
    """Public recent reviews for a seller/buyer profile."""
    u = db.query(User).filter(User.handle == handle.lower()).first()
    if not u:
        raise HTTPException(404, "Not found")
    rows = (db.query(Feedback).filter(Feedback.ratee_id == u.id)
            .order_by(Feedback.created_at.desc()).limit(20).all())
    reviews = []
    for f in rows:
        rater = db.get(User, f.rater_id)
        reviews.append({"score": f.score, "comment": f.comment, "role": f.ratee_role,
                        "rater": rater.handle or rater.display_name if rater else "user",
                        "created_at": f.created_at})
    return reviews
