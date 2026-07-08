"""The WagyuTank Semen Catalog — a printed edition mailed to breeders twice a
year (Northern & Southern hemispheres, timed to breeding season). Members submit
their bulls / semen / ranch to appear; everyone on the list gets an e-copy, and
submitters can receive a printed copy at the mailing address they provide."""
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import CatalogSubmission, User
from ..security import get_current_user
from ..services import settings_store

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

_DEFAULTS = {
    "catalog_edition_key": "2026-northern",
    "catalog_edition_label": "2026 Northern Hemisphere Edition",
    "catalog_deadline": "February 1, 2026",
    "catalog_mail_month": "March 2026",
    "catalog_submit_open": True,
}


def _edition() -> dict:
    return {k: settings_store.get(k, v) for k, v in _DEFAULTS.items()}


@router.get("/info")
def info(db: Session = Depends(get_db)):
    """Public — current edition details + how many entries are in so far."""
    ed = _edition()
    count = db.query(CatalogSubmission).filter(
        CatalogSubmission.edition == ed["catalog_edition_key"],
        CatalogSubmission.status != "rejected").count()
    return {**ed, "submission_count": count}


@router.post("/submit")
def submit(payload: dict = Body(...), user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    ed = _edition()
    if not ed.get("catalog_submit_open"):
        raise HTTPException(400, "Submissions for the current edition are closed.")
    ranch = (payload.get("ranch_name") or user.display_name or "").strip()
    if not ranch:
        raise HTTPException(400, "A ranch or seller name is required.")
    if not (payload.get("animal_name") or payload.get("description")):
        raise HTTPException(400, "Tell us which bull/semen you're submitting (name or description).")
    sub = CatalogSubmission(
        user_id=user.id, edition=ed["catalog_edition_key"], ranch_name=ranch[:160],
        animal_name=(payload.get("animal_name") or None), animal_reg=(payload.get("animal_reg") or None),
        bloodline=(payload.get("bloodline") or None),
        product_type=(payload.get("product_type") or "semen")[:20],
        price_note=(payload.get("price_note") or None), description=(payload.get("description") or None),
        photo_url=(payload.get("photo_url") or None),
        contact_email=(payload.get("contact_email") or user.email)[:255],
        contact_phone=(payload.get("contact_phone") or user.phone or None),
        website=(payload.get("website") or None),
        ship_name=(payload.get("ship_name") or None), ship_address=(payload.get("ship_address") or None),
        ship_city=(payload.get("ship_city") or None), ship_region=(payload.get("ship_region") or None),
        ship_postal=(payload.get("ship_postal") or None), ship_country=(payload.get("ship_country") or None),
        listing_id=(payload.get("listing_id") or None),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {"ok": True, "id": sub.id, "edition": sub.edition,
            "message": f"You're in for the {ed['catalog_edition_label']}! We'll be in touch before print."}


@router.get("/my-submissions")
def my_submissions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(CatalogSubmission).filter(CatalogSubmission.user_id == user.id)
            .order_by(CatalogSubmission.created_at.desc()).all())
    return [{"id": s.id, "edition": s.edition, "ranch_name": s.ranch_name,
             "animal_name": s.animal_name, "product_type": s.product_type,
             "status": s.status, "created_at": s.created_at} for s in rows]
