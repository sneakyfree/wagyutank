"""Beef Market Data Center — commodity cattle/beef prices (USDA AMS, public domain)
plus Wagyu premium benchmarks and our own genetics price index."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import MarketQuote

router = APIRouter(prefix="/api/market", tags=["market"])

CATEGORIES = [
    {"key": "feeder", "label": "Feeder Cattle", "icon": "🐮"},
    {"key": "fed", "label": "Fed / Live Cattle", "icon": "🥩"},
    {"key": "cutout", "label": "Boxed Beef Cutout", "icon": "📦"},
    {"key": "wagyu", "label": "Wagyu Premiums", "icon": "⭐"},
    {"key": "context", "label": "Market Context", "icon": "🌎"},
]


def _q(m: MarketQuote) -> dict:
    return {"label": m.label, "value": m.value, "value_text": m.value_text, "unit": m.unit,
            "change": m.change, "as_of": m.as_of, "source": m.source, "source_url": m.source_url,
            "note": m.note}


@router.get("")
def market(db: Session = Depends(get_db)):
    rows = db.query(MarketQuote).order_by(MarketQuote.sort_order.asc()).all()
    grouped: dict[str, list] = {c["key"]: [] for c in CATEGORIES}
    for m in rows:
        grouped.setdefault(m.category, []).append(_q(m))
    latest = max((m.updated_at for m in rows), default=None)
    return {
        "categories": CATEGORIES,
        "data": grouped,
        "updated_at": latest,
        "disclaimer": "Commodity figures compiled from USDA AMS public-domain market reports; "
                      "Wagyu benchmarks from published producer and retail pricing. Indicative, "
                      "not a trading quote.",
    }
