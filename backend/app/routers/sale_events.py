"""The forensic Wagyu Sale Reports database — every auction we can find, charted."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SaleEvent, UpcomingSale

router = APIRouter(prefix="/api/sale-events", tags=["sale-events"])
upcoming_router = APIRouter(prefix="/api/upcoming-sales", tags=["upcoming-sales"])


@upcoming_router.get("")
def upcoming(continent: str | None = None, db: Session = Depends(get_db)):
    """Future Wagyu sales calendar, soonest first. Past-dated entries drop off."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    q = db.query(UpcomingSale).filter((UpcomingSale.sort_date >= today) | (UpcomingSale.sort_date == None))  # noqa: E711
    if continent:
        q = q.filter(UpcomingSale.continent == continent.upper())
    rows = q.order_by(UpcomingSale.sort_date.asc().nullslast()).all()
    return [{"id": s.id, "sale_name": s.sale_name, "date": s.date, "sort_date": s.sort_date,
             "country": s.country, "continent": s.continent, "venue": s.venue, "host": s.host,
             "url": s.url, "notes": s.notes} for s in rows]

USD_RATE = {"USD": 1.0, "AUD": 0.66, "NZD": 0.60, "GBP": 1.27, "EUR": 1.08,
            "BRL": 0.18, "JPY": 0.0067}
CONTINENTS = [{"key": "OC", "label": "Australia / NZ"}, {"key": "NA", "label": "North America"},
              {"key": "EU", "label": "Europe"}, {"key": "AS", "label": "Asia / Japan"},
              {"key": "SA", "label": "South America"}]


def _out(s: SaleEvent) -> dict:
    return {"id": s.id, "sale_name": s.sale_name, "date": s.date, "year": s.year,
            "country": s.country, "continent": s.continent, "venue": s.venue, "currency": s.currency,
            "gross_total": s.gross_total, "lots_sold": s.lots_sold, "top_price": s.top_price,
            "top_price_item": s.top_price_item,
            "bull_avg": s.bull_avg, "bull_top": s.bull_top, "female_avg": s.female_avg,
            "female_top": s.female_top, "heifer_avg": s.heifer_avg, "heifer_top": s.heifer_top,
            "semen_avg": s.semen_avg, "semen_top": s.semen_top, "embryo_avg": s.embryo_avg,
            "embryo_top": s.embryo_top, "source_url": s.source_url, "source_name": s.source_name,
            "notes": s.notes}


@router.get("")
def list_events(continent: str | None = None, country: str | None = None,
                year: int | None = None, q: str | None = None,
                sort: str = Query("recent", pattern="^(recent|oldest|top)$"),
                limit: int = Query(200, le=500), db: Session = Depends(get_db)):
    query = db.query(SaleEvent)
    if continent:
        query = query.filter(SaleEvent.continent == continent.upper())
    if country:
        query = query.filter(SaleEvent.country == country.upper())
    if year:
        query = query.filter(SaleEvent.year == year)
    if q:
        query = query.filter(func.lower(SaleEvent.sale_name).like(f"%{q.lower()}%"))
    if sort == "oldest":
        query = query.order_by(SaleEvent.year.asc().nullslast(), SaleEvent.date.asc().nullslast())
    elif sort == "top":
        query = query.order_by(SaleEvent.top_price.desc().nullslast())
    else:
        query = query.order_by(SaleEvent.year.desc().nullslast(), SaleEvent.date.desc().nullslast())
    return [_out(s) for s in query.limit(limit).all()]


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    active = db.query(SaleEvent)
    by_continent = dict(db.query(SaleEvent.continent, func.count()).group_by(SaleEvent.continent).all())
    countries = sorted(c[0] for c in db.query(SaleEvent.country).distinct() if c[0])
    yr = db.query(func.min(SaleEvent.year), func.max(SaleEvent.year)).first()
    return {"total": active.count(), "by_continent": by_continent, "countries": countries,
            "year_min": yr[0], "year_max": yr[1], "continents": CONTINENTS}


@router.get("/chart")
def chart(series: str = Query("elite", pattern="^(elite|matsusaka|global)$"),
          db: Session = Depends(get_db)):
    """Time-series data for the sale-reports charts."""
    if series == "elite":
        # The AWA Elite Wagyu Sale — the consistent annual genetics series (AUD).
        rows = (db.query(SaleEvent)
                .filter(SaleEvent.sale_name.like("%Elite Wagyu%"), SaleEvent.country == "AU")
                .order_by(SaleEvent.year.asc()).all())
        return {"currency": "AUD", "unit": "avg price / lot",
                "points": [{"year": r.year, "bull": r.bull_avg, "female": r.female_avg,
                            "semen": r.semen_avg, "embryo": r.embryo_avg,
                            "top": r.top_price} for r in rows]}
    if series == "matsusaka":
        rows = (db.query(SaleEvent)
                .filter(SaleEvent.sale_name.like("%Matsusaka%"))
                .order_by(SaleEvent.year.asc()).all())
        return {"currency": "JPY", "unit": "champion cow price",
                "points": [{"year": r.year, "champion": r.top_price} for r in rows]}
    # global: USD-normalized genetics category averages across all genetics sales, by year
    rows = (db.query(SaleEvent).filter(SaleEvent.continent != "AS").order_by(SaleEvent.year.asc()).all())
    buckets: dict[int, dict] = {}
    for r in rows:
        rate = USD_RATE.get(r.currency, 1.0)
        b = buckets.setdefault(r.year, {"bull": [], "female": [], "semen": [], "embryo": []})
        if r.bull_avg: b["bull"].append(r.bull_avg * rate)
        if r.female_avg: b["female"].append(r.female_avg * rate)
        if r.semen_avg: b["semen"].append(r.semen_avg * rate)
        if r.embryo_avg: b["embryo"].append(r.embryo_avg * rate)
    pts = []
    for yr in sorted(k for k in buckets if k):
        b = buckets[yr]
        pts.append({"year": yr, **{k: (round(sum(v) / len(v)) if v else None) for k, v in b.items()}})
    return {"currency": "USD", "unit": "avg price / lot (USD-normalized)", "points": pts}


@router.get("/ticker")
def ticker(db: Session = Depends(get_db)):
    """Latest genetics-sale category averages for the sale-data ticker."""
    latest = (db.query(SaleEvent)
              .filter(SaleEvent.female_avg != None)  # noqa: E711
              .order_by(SaleEvent.year.desc()).limit(6).all())
    items = []
    for r in latest:
        sym = {"AUD": "A$", "USD": "$", "EUR": "€", "GBP": "£"}.get(r.currency, "$")
        for cat, val in (("Heifers", r.female_avg), ("Bulls", r.bull_avg),
                         ("Embryos", r.embryo_avg), ("Semen", r.semen_avg)):
            if val:
                items.append({"label": f"{cat} · {r.sale_name.split(' 20')[0][:22]}",
                              "value": f"{sym}{val:,.0f}", "year": r.year})
    # de-dup category labels, keep freshest
    seen, out = set(), []
    for it in items:
        k = it["label"].split(" · ")[0]
        if k not in seen or len(out) < 8:
            seen.add(k); out.append(it)
    return {"items": out[:12]}
