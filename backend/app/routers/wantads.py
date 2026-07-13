"""Want-ads — the reverse marketplace. A buyer (rancher looking for bred heifers,
or a chef/restaurant sourcing Wagyu beef) posts WHAT THEY NEED; sellers browse the
demand and reach out. This is the chef-sourcing surface on WagyuSale (and works on
any tank). Public list is read-only; posting needs a login.

Criteria ride the model's free-form JSON `criteria` field, so different verticals
carry different shapes without schema churn:
  live_animal → {animal_class, count, bred_status, state, radius_postal, budget}
  beef        → {cut, monthly_lbs, state, delivery, budget}
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import tank
from ..db import get_db
from ..models import ProductType, User, WantAd
from ..security import get_current_user

router = APIRouter(prefix="/api/wantads", tags=["wantads"])


class WantAdCreate(BaseModel):
    product_type: ProductType
    criteria: dict = {}
    note: str | None = None


def _out(w: WantAd, buyer: User | None) -> dict:
    return {
        "id": w.id,
        "product_type": w.product_type.value if w.product_type else None,
        "criteria": w.criteria or {},
        "note": w.note,
        "active": w.active,
        "created_at": w.created_at,
        "buyer_handle": buyer.handle if buyer else None,
        "buyer_name": (buyer.display_name if buyer else None),
        "buyer_location": (buyer.location if buyer else None),
    }


@router.post("")
def post_want_ad(payload: WantAdCreate, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Post a 'wanted' ad. Gated to the tank's product types (a genetics tank
    won't accept a beef want-ad, and vice-versa)."""
    if payload.product_type.value not in tank.product_keys():
        raise HTTPException(400, f"This marketplace doesn't handle {payload.product_type.value} requests.")
    w = WantAd(buyer_id=user.id, product_type=payload.product_type,
               criteria=payload.criteria or {}, note=payload.note, active=True)
    db.add(w); db.commit(); db.refresh(w)
    return _out(w, user)


@router.get("")
def list_want_ads(product_type: ProductType | None = None,
                  state: str | None = Query(None, description="Match criteria.state"),
                  limit: int = Query(50, le=100), offset: int = 0,
                  db: Session = Depends(get_db)):
    """Browse active demand — sellers scan this to find buyers to reach out to."""
    q = db.query(WantAd).filter(WantAd.active == True)  # noqa: E712
    if product_type:
        q = q.filter(WantAd.product_type == product_type)
    rows = q.order_by(WantAd.created_at.desc()).offset(offset).limit(limit).all()
    if state:
        s = state.lower()
        rows = [w for w in rows if str((w.criteria or {}).get("state", "")).lower() == s]
    buyers = {u.id: u for u in db.query(User).filter(
        User.id.in_([w.buyer_id for w in rows] or [0]))}
    return [_out(w, buyers.get(w.buyer_id)) for w in rows]


@router.get("/mine")
def my_want_ads(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(WantAd).filter(WantAd.buyer_id == user.id).order_by(WantAd.created_at.desc()).all()
    return [_out(w, user) for w in rows]


@router.post("/{want_id}/close")
def close_want_ad(want_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    w = db.get(WantAd, want_id)
    if not w or w.buyer_id != user.id:
        raise HTTPException(404, "Want-ad not found.")
    w.active = False
    db.commit()
    return {"ok": True}
