"""The Wagyu Genetics Price Index — computed from Roundup aggregated listings.

A defensible, ownable data product: nobody else publishes a live semen price
index. `compute()` reads current listings; `snapshot()` (called by the daily job)
records values so the ticker can show a real trend over time."""
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import AggregatedListing, PriceSnapshot, ProductType

# --- price hygiene -----------------------------------------------------------
# The Roundup crawl is high-volume and noisy: it scrapes ownership shares, bull
# packages, embryo (ET) lots and prices in many currencies, all of which used to
# pollute a naive mean and blow the semen index up to nonsense ($1,100+/straw).
# The index now normalizes to USD, keeps only genuine per-straw prices, guards
# outliers, and reports the MEDIAN (robust to the few that slip through).

# Approximate FX to USD — a directional market gauge, not an FX desk. Refresh
# occasionally; being off a few % never changes the story a median tells.
_FX_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "AUD": 0.66, "CAD": 0.73,
           "JPY": 0.0067, "NZD": 0.61, "BRL": 0.18, "MXN": 0.055, "ZAR": 0.055}

# A "price" that is NOT a single sellable unit of ANY genetics product: ownership
# shares, "% interest", packages/lots, or subscriptions.
_NON_UNIT = re.compile(
    r"interest|%|ownership|\bshare\b|package|\blot\b|\bflush\b|per\s*month|per\s*year|"
    r"/mo\b|/yr\b|\bpair\b", re.I)
# Embryo/IVF markers — reject these from the SEMEN index only (they belong to the
# embryo index). Passing reject_embryo=True to _clean_prices applies this.
_EMBRYO_MARK = re.compile(r"\bembryos?\b|\bivf\b|\bivp\b|\(et\)|embryo transfer|implant", re.I)

_STRAW_CEILING_USD = 5000.0    # a single conventional straw above this is a mis-parse
_STRAW_FLOOR_USD = 12.0        # below this is a deposit / shipping / per-something mis-parse
_EMBRYO_CEILING_USD = 60000.0  # embryos legitimately run high, but guard the wild ones
_EMBRYO_FLOOR_USD = 100.0


def _to_usd(price, currency):
    return price * _FX_USD.get((currency or "USD").strip().upper(), 1.0)


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2


def _clean_prices(rows, ceiling, floor=0.0, reject_embryo=False):
    """rows: (price, currency, price_unit, title, animal_name). Returns clean USD list.
    reject_embryo drops embryo/ET rows (used for the semen index, not the embryo one)."""
    out = []
    for price, cur, unit, title, name in rows:
        if not price or price <= 0:
            continue
        blob = " ".join(str(x or "") for x in (unit, title, name))
        if _NON_UNIT.search(blob):
            continue
        if reject_embryo and _EMBRYO_MARK.search(blob):
            continue
        usd = _to_usd(price, cur)
        if usd < floor or usd > ceiling:
            continue
        out.append(round(usd, 2))
    return out

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


_SEMEN_COLS = (AggregatedListing.price, AggregatedListing.currency,
               AggregatedListing.price_unit, AggregatedListing.title,
               AggregatedListing.animal_name)


def _sire_stats(db: Session, fragments: list[str]):
    q = _semen_q(db)
    clause = None
    for f in fragments:
        c = func.lower(AggregatedListing.animal_name).like(f"%{f}%")
        clause = c if clause is None else (clause | c)
    rows = q.filter(clause).with_entities(*_SEMEN_COLS).all()
    prices = _clean_prices(rows, _STRAW_CEILING_USD, _STRAW_FLOOR_USD, reject_embryo=True)
    if not prices:
        return None
    return {"count": len(prices), "avg": _median(prices),
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
    # Semen index: per-straw USD prices only, outliers guarded, reported as MEDIAN.
    semen = _clean_prices(_semen_q(db).with_entities(*_SEMEN_COLS).all(), _STRAW_CEILING_USD, _STRAW_FLOOR_USD, reject_embryo=True)
    embryo_rows = db.query(*_SEMEN_COLS).filter(
        AggregatedListing.status == "active",
        AggregatedListing.product_type == ProductType.EMBRYO,
        AggregatedListing.price != None).all()  # noqa: E711
    embryo = _clean_prices(embryo_rows, _EMBRYO_CEILING_USD, _EMBRYO_FLOOR_USD)
    market_avg = _median(semen)

    # Foundation-sire prices come from the CURATED reference table — NOT scrape
    # averages, which conflate a foundation bull with cheap namesake descendants
    # (the "$85 Rueshaw" bug). These are human-verified, sourced reference prices.
    from ..models import FoundationReferencePrice
    refs = (db.query(FoundationReferencePrice)
            .filter(FoundationReferencePrice.semen_usd != None)  # noqa: E711
            .order_by(FoundationReferencePrice.semen_usd.desc()).all())
    sires = []
    for r in refs:
        key = f"ref:{r.registration_no or r.sire}"
        sires.append({
            "sire": r.sire, "registration_no": r.registration_no,
            "slug": r.registration_no or r.sire.lower().replace(" ", "-"),
            "avg": r.semen_usd, "min": r.semen_low, "max": r.semen_high,
            "embryo": r.embryo_usd, "as_of": r.as_of_year, "availability": r.availability,
            "confidence": r.confidence, "source": r.source_name, "verified": True,
            "trend": _trend(db, key, r.semen_usd),
        })
    return {
        "market": {
            # semen_avg is the MEDIAN per-straw price in USD (robust to scrape outliers).
            "semen_avg": market_avg, "semen_min": round(min(semen), 2) if semen else None,
            "semen_max": round(max(semen), 2) if semen else None, "semen_count": len(semen),
            "semen_mean": round(sum(semen) / len(semen), 2) if semen else None,
            "embryo_avg": _median(embryo), "embryo_count": len(embryo),
            "currency": "USD", "basis": "median per straw",
            "trend": _trend(db, "market:semen", market_avg),
        },
        "sires": sires,
        "updated_at": _now().isoformat(),
    }


def snapshot(db: Session) -> int:
    """Record today's index values (idempotent-ish; one row per key per run).

    The index is semen/embryo-shaped; on a live-cattle/beef tank it would produce
    nonsense, so it no-ops unless the tank sells a genetics-family product. (The
    hatchery already gates its cron behind features.price_index; this guards a
    direct run.)"""
    from .. import tank
    if not tank.has_family("genetics"):
        return 0
    data = compute(db)
    n = 0
    m = data["market"]
    if m["semen_avg"] is not None:
        db.add(PriceSnapshot(key="market:semen", avg_price=m["semen_avg"], count=m["semen_count"])); n += 1
    for s in data["sires"]:
        key = f"ref:{s.get('registration_no') or s['sire']}"
        db.add(PriceSnapshot(key=key, avg_price=s["avg"], count=1)); n += 1
    db.commit()
    return n
