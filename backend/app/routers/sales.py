"""Notable Sales tracker — record-setting Wagyu genetics and cattle sales."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import NotableSale

router = APIRouter(prefix="/api/sales", tags=["sales"])

CATEGORIES = [
    {"key": "semen", "label": "Semen", "icon": "💉"},
    {"key": "embryo", "label": "Embryos", "icon": "🧬"},
    {"key": "female", "label": "Females", "icon": "🐄"},
    {"key": "bull", "label": "Bulls", "icon": "🐂"},
    {"key": "carcass", "label": "Beef & Whole Cattle", "icon": "🥩"},
]


def _out(s: NotableSale) -> dict:
    return {"id": s.id, "category": s.category, "animal_name": s.animal_name, "headline": s.headline,
            "price": s.price, "currency": s.currency, "usd_approx": s.usd_approx, "unit": s.unit,
            "country": s.country, "sale_venue": s.sale_venue, "date_label": s.date_label,
            "buyer": s.buyer, "seller": s.seller, "note": s.note, "source": s.source,
            "source_url": s.source_url, "is_record": s.is_record}


@router.get("")
def sales(window: str | None = None, db: Session = Depends(get_db)):
    from datetime import datetime, timezone
    q = db.query(NotableSale)
    now_year = datetime.now(timezone.utc).year
    if window == "year":
        q = q.filter(NotableSale.year == now_year)
    elif window == "decade":
        q = q.filter(NotableSale.year >= now_year - 10)
    rows = q.order_by(NotableSale.sort_order.asc()).all()
    grouped: dict[str, list] = {c["key"]: [] for c in CATEGORIES}
    for s in rows:
        grouped.setdefault(s.category, []).append(_out(s))
    records = sorted([_out(s) for s in rows if s.is_record],
                     key=lambda x: x["usd_approx"] or 0, reverse=True)
    return {"categories": CATEGORIES, "data": grouped, "records": records}
