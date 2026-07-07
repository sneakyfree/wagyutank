from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Follow, Listing, ListingStatus, User
from ..schemas import StorefrontUpdate, UserPublic
from ..security import get_current_user, get_optional_user
from .listings import to_listing_out

router = APIRouter(prefix="/api/users", tags=["users", "storefronts"])


class Storefront(BaseModel):
    seller: UserPublic
    listing_count: int
    listings: list
    follower_count: int = 0
    is_following: bool = False
    member_since: str | None = None


def _seller_follows(db: Session, handle: str):
    return db.query(Follow).filter(Follow.target_type == "seller", Follow.target_key == handle)


@router.patch("/me", response_model=UserPublic)
def update_me(payload: StorefrontUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    data = payload.model_dump(exclude_unset=True)
    if "handle" in data and data["handle"]:
        h = data["handle"].lower().strip()
        clash = db.query(User).filter(User.handle == h, User.id != user.id).first()
        if clash:
            raise HTTPException(400, "That handle is taken.")
        data["handle"] = h
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/become-seller", response_model=UserPublic)
def become_seller(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mark the account seller-ready. Creates a real Stripe Connect Express account when
    Stripe is configured (payout URL is fetched separately via /api/payments/connect/onboard);
    falls back to a dev stub otherwise so listing works without Stripe."""
    from ..services import payments as pay
    if not user.stripe_account_id:
        if pay.stripe_enabled():
            try:
                user.stripe_account_id = pay.create_express_account(user.email, user.country or "US")
            except Exception:
                user.stripe_account_id = f"acct_dev_{user.id}"
        else:
            user.stripe_account_id = f"acct_dev_{user.id}"
        db.commit()
        db.refresh(user)
    return user


@router.get("/{handle}", response_model=Storefront)
def storefront(handle: str, viewer: User | None = Depends(get_optional_user),
               db: Session = Depends(get_db)):
    seller = db.query(User).filter(User.handle == handle.lower()).first()
    if not seller:
        raise HTTPException(404, "Storefront not found")
    rows = (
        db.query(Listing)
        .filter(Listing.seller_id == seller.id, Listing.status == ListingStatus.ACTIVE)
        .order_by(Listing.featured_until.desc().nullslast(), Listing.created_at.desc())
        .all()
    )
    follower_count = _seller_follows(db, seller.handle).count() if seller.handle else 0
    is_following = bool(
        viewer and seller.handle
        and _seller_follows(db, seller.handle).filter(Follow.follower_id == viewer.id).first()
    )
    return Storefront(
        seller=UserPublic.model_validate(seller, from_attributes=True),
        listing_count=len(rows),
        listings=[to_listing_out(x).model_dump() for x in rows],
        follower_count=follower_count,
        is_following=is_following,
        member_since=(seller.created_at.strftime("%B %Y") if seller.created_at else None),
    )


# ---- Follow graph (§8 retention) ----
class FollowIn(BaseModel):
    target_type: str  # seller | bloodline | animal
    target_key: str


@router.post("/me/follow")
def follow(payload: FollowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    exists = db.query(Follow).filter_by(
        follower_id=user.id, target_type=payload.target_type, target_key=payload.target_key
    ).first()
    if exists:
        return {"status": "already_following"}
    db.add(Follow(follower_id=user.id, target_type=payload.target_type, target_key=payload.target_key))
    db.commit()
    return {"status": "following"}


@router.post("/me/unfollow")
def unfollow(payload: FollowIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(Follow).filter_by(
        follower_id=user.id, target_type=payload.target_type, target_key=payload.target_key
    ).delete()
    db.commit()
    return {"status": "unfollowed" if n else "not_following"}


@router.get("/me/following")
def following(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Follow).filter(Follow.follower_id == user.id).all()
    return [{"target_type": r.target_type, "target_key": r.target_key} for r in rows]
