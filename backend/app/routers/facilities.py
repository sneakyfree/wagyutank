from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Facility, User
from ..schemas import FacilityCreate, FacilityOut
from ..security import get_current_user

router = APIRouter(prefix="/api/facilities", tags=["facilities"])


@router.get("", response_model=list[FacilityOut])
def list_facilities(
    q: str | None = None,
    service: str | None = None,
    country: str | None = None,
    has_logo: bool | None = None,
    limit: int = 25,
    db: Session = Depends(get_db),
):
    """Typeahead directory. `q` matches the start of a facility name (e.g. 'Ha' -> Hawkeye).

    Each row carries `logo_url` -- the mark captured from the facility's own site
    by scripts/capture_ranch_marks.py -- or null when we found nothing usable.
    `has_logo=true` narrows to the rows that have one, for card grids that would
    look ragged with holes in them."""
    query = db.query(Facility)
    if q:
        query = query.filter(func.lower(Facility.name).like(f"{q.lower()}%"))
    if country:
        query = query.filter(Facility.country == country)
    if has_logo is True:
        query = query.filter(Facility.logo_url.isnot(None), Facility.logo_url != "")
    elif has_logo is False:
        query = query.filter((Facility.logo_url.is_(None)) | (Facility.logo_url == ""))
    rows = query.order_by(Facility.name).limit(min(limit, 100)).all()
    if service:
        rows = [f for f in rows if service in (f.services or [])]
    return rows


@router.post("", response_model=FacilityOut)
def add_facility(payload: FacilityCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Sellers can add a facility that's missing (light moderation flag)."""
    f = Facility(
        name=payload.name, city=payload.city, state=payload.state,
        country=payload.country, services=payload.services, seller_added=True,
    )
    db.add(f)
    db.commit()
    db.refresh(f)
    return f
