"""The Wagyu Genetics Price Index — computed from Roundup aggregated listings.

A defensible, ownable data product: nobody else publishes a live semen price
index. `compute()` reads current listings; `snapshot()` (called by the daily job)
records values so the ticker can show a real trend over time."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import AggregatedListing, PriceSnapshot, ProductType

# Marquee sires people actually trade — matched by name fragment (case-insensitive).
MARQUEE = [
    ("Michifuku", ["michifuku"]),
    ("Itoshigenami", ["itoshigenami", "shigenami"]),
    ("Shigeshigenami", ["shigeshige"]),
    ("Fukutsuru", ["fukutsuru"]),
    ("Kitaguni Jr", ["kitaguni"]),
    ("Yasufuku Jr", ["yasufuku"]),
    ("Sanjirou", ["sanjirou", "sanjiro"]),
    ("Haruki 2", ["haruki"]),
    ("Kikuyasu", ["kikuyasu"]),
    ("Mt. Fuji", ["mt fuji", "mt. fuji", "fuji "]),
    ("Rueshaw", ["rueshaw"]),
    ("Big Al / Akaushi", ["akaushi", "big al", "mitsuaki"]),
]


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _semen_q(db: Session):
    return db.query(AggregatedListing).filter(
        AggregatedListing.status == "active",
        AggregatedListing.product_type == ProductType.SEMEN,
        AggregatedListing.price != None,  # noqa: E711
    )


def _sire_stats(db: Session, fragments: list[str]):
    q = _semen_q(db)
    clause = None
    for f in fragments:
        c = func.lower(AggregatedListing.animal_name).like(f"%{f}%")
        clause = c if clause is None else (clause | c)
    rows = q.filter(clause).with_entities(AggregatedListing.price).all()
    prices = [r[0] for r in rows if r[0]]
    if not prices:
        return None
    return {"count": len(prices), "avg": round(sum(prices) / len(prices), 2),
            "min": round(min(prices), 2), "max": round(max(prices), 2)}


def _trend(db: Session, key: str, current_avg: float | None):
    """% change vs the oldest snapshot in the last ~10 days."""
    if current_avg is None:
        return None
    since = _now() - timedelta(days=10)
    old = (db.query(PriceSnapshot).filter(PriceSnapshot.key == key, PriceSnapshot.created_at >= since,
                                          PriceSnapshot.avg_price != None)  # noqa: E711
           .order_by(PriceSnapshot.created_at.asc()).first())
    if not old or not old.avg_price:
        return None
    return round((current_avg - old.avg_price) / old.avg_price * 100, 1)


def compute(db: Session) -> dict:
    semen = [r[0] for r in _semen_q(db).with_entities(AggregatedListing.price).all() if r[0]]
    embryo = [r[0] for r in db.query(AggregatedListing.price).filter(
        AggregatedListing.status == "active", AggregatedListing.product_type == ProductType.EMBRYO,
        AggregatedListing.price != None).all() if r[0]]  # noqa: E711
    market_avg = round(sum(semen) / len(semen), 2) if semen else None
    sires = []
    for label, frags in MARQUEE:
        st = _sire_stats(db, frags)
        if st:
            sires.append({"sire": label, **st, "trend": _trend(db, f"sire:{label}", st["avg"])})
    sires.sort(key=lambda s: s["count"], reverse=True)
    return {
        "market": {
            "semen_avg": market_avg, "semen_min": round(min(semen), 2) if semen else None,
            "semen_max": round(max(semen), 2) if semen else None, "semen_count": len(semen),
            "embryo_avg": round(sum(embryo) / len(embryo), 2) if embryo else None,
            "embryo_count": len(embryo),
            "trend": _trend(db, "market:semen", market_avg),
        },
        "sires": sires,
        "updated_at": _now().isoformat(),
    }


def snapshot(db: Session) -> int:
    """Record today's index values (idempotent-ish; one row per key per run)."""
    data = compute(db)
    n = 0
    m = data["market"]
    if m["semen_avg"] is not None:
        db.add(PriceSnapshot(key="market:semen", avg_price=m["semen_avg"], count=m["semen_count"])); n += 1
    for s in data["sires"]:
        db.add(PriceSnapshot(key=f"sire:{s['sire']}", avg_price=s["avg"], count=s["count"])); n += 1
    db.commit()
    return n
