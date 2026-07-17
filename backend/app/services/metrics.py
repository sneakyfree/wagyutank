"""Comprehensive platform metrics with historical trend deltas for the daily report.

The trick: every row carries a creation/first-seen timestamp, so we can reconstruct
what each total *was* N days ago and show a real delta today — no waiting to
accumulate snapshots. Roundup "active" counts use first_seen/last_seen to know what
was live at a past instant. Everything is defensive: a metric that errors (missing
column on an older clone DB) is simply skipped, never breaks the report.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func

from .. import models

# (key, label, days) — the trend windows shown as columns
WINDOWS = [("1d", 1), ("7d", 7), ("30d", 30), ("1y", 365)]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _count_created_le(db, model, cutoff, ts_attr="created_at", *filters) -> int:
    ts = getattr(model, ts_attr)
    q = db.query(func.count()).select_from(model).filter(ts <= cutoff)
    for f in filters:
        q = q.filter(f)
    return int(q.scalar() or 0)


def _roundup_active_asof(db, cutoff) -> int:
    """A web listing was live at instant `cutoff` if it was first seen by then and
    still being seen at/after then (last_seen_at is bumped every crawl it survives)."""
    A = models.AggregatedListing
    return int(db.query(func.count()).select_from(A).filter(
        A.first_seen_at <= cutoff, A.last_seen_at >= cutoff).scalar() or 0)


def _roundup_sources_asof(db, cutoff) -> int:
    A = models.AggregatedListing
    return int(db.query(func.count(func.distinct(A.source_site))).filter(
        A.first_seen_at <= cutoff, A.last_seen_at >= cutoff).scalar() or 0)


def _roundup_countries_asof(db, cutoff) -> int:
    A = models.AggregatedListing
    return int(db.query(func.count(func.distinct(A.country))).filter(
        A.first_seen_at <= cutoff, A.last_seen_at >= cutoff,
        A.country.isnot(None)).scalar() or 0)


def _sellers_asof(db, cutoff) -> int:
    """Distinct users who had posted a marketplace listing by `cutoff`."""
    L = models.Listing
    return int(db.query(func.count(func.distinct(L.seller_id))).filter(
        L.created_at <= cutoff).scalar() or 0)


def _price_index_asof(db, cutoff):
    """The Genetics Price Index semen average ($/straw) at the snapshot nearest
    on-or-before `cutoff`. Returns None if no snapshot that old exists."""
    P = models.PriceSnapshot
    row = (db.query(P).filter(P.key == "market:semen", P.created_at <= cutoff,
                              P.avg_price.isnot(None))
           .order_by(P.created_at.desc()).first())
    return row.avg_price if row else None


def snapshot(db) -> dict:
    """Return {generated_at, windows, metrics:[{label, now, unit, deltas:{1d,7d,...}}]}.

    Count metrics show a signed delta (grew/shrank). Value metrics (price) show the
    absolute then-vs-now. Rows that are all-zero AND have no history are dropped so a
    fresh clone's report isn't cluttered with empty lines.
    """
    now = _now()
    cuts = {k: now - timedelta(days=d) for k, d in WINDOWS}
    metrics: list[dict] = []

    def add_count(label, now_fn, asof_fn, unit=""):
        try:
            nv = now_fn()
        except Exception:
            return
        deltas = {}
        for k, cut in cuts.items():
            try:
                deltas[k] = nv - asof_fn(cut)
            except Exception:
                deltas[k] = None
        if nv == 0 and all((d or 0) == 0 for d in deltas.values()):
            return
        metrics.append({"label": label, "now": nv, "unit": unit,
                        "kind": "count", "deltas": deltas})

    def add_value(label, now_val, asof_fn, unit="", fmt="{:,.0f}"):
        if now_val is None:
            return
        deltas = {}
        for k, cut in cuts.items():
            try:
                past = asof_fn(cut)
                deltas[k] = (now_val - past) if past is not None else None
            except Exception:
                deltas[k] = None
        metrics.append({"label": label, "now": now_val, "unit": unit,
                        "kind": "value", "fmt": fmt, "deltas": deltas})

    A = models.AggregatedListing
    L = models.Listing

    # ---- The Roundup (web aggregation) ----
    add_count("Roundup web listings (live)",
              lambda: int(db.query(func.count()).select_from(A).filter(A.status == "active").scalar() or 0),
              lambda c: _roundup_active_asof(db, c))
    add_count("Roundup source websites",
              lambda: int(db.query(func.count(func.distinct(A.source_site))).filter(A.status == "active").scalar() or 0),
              lambda c: _roundup_sources_asof(db, c))
    add_count("Countries covered",
              lambda: int(db.query(func.count(func.distinct(A.country))).filter(A.status == "active", A.country.isnot(None)).scalar() or 0),
              lambda c: _roundup_countries_asof(db, c))

    # ---- Directory / Atlas ----
    add_count("Directory sellers (Atlas)",
              lambda: _count_created_le(db, models.DirectorySeller, now),
              lambda c: _count_created_le(db, models.DirectorySeller, c))

    # ---- Marketplace + community ----
    add_count("Marketplace listings (total posted)",
              lambda: _count_created_le(db, L, now),
              lambda c: _count_created_le(db, L, c))
    add_count("Registered members",
              lambda: _count_created_le(db, models.User, now),
              lambda c: _count_created_le(db, models.User, c))
    add_count("Active sellers",
              lambda: _sellers_asof(db, now),
              lambda c: _sellers_asof(db, c))
    add_count("Buyer want-ads",
              lambda: _count_created_le(db, models.WantAd, now),
              lambda c: _count_created_le(db, models.WantAd, c))
    add_count("Discussion posts",
              lambda: _count_created_le(db, models.Comment, now),
              lambda c: _count_created_le(db, models.Comment, c))
    add_count("Breeder videos",
              lambda: _count_created_le(db, models.AnimalVideo, now),
              lambda c: _count_created_le(db, models.AnimalVideo, c))

    # ---- Knowledge base ----
    add_count("Foundation animals",
              lambda: _count_created_le(db, models.Animal, now),
              lambda c: _count_created_le(db, models.Animal, c))
    add_count("News articles (Wagyu Wire)",
              lambda: _count_created_le(db, models.NewsArticle, now, "first_seen_at"),
              lambda c: _count_created_le(db, models.NewsArticle, c, "first_seen_at"))
    add_count("Auction sale records",
              lambda: _count_created_le(db, models.SaleEvent, now),
              lambda c: _count_created_le(db, models.SaleEvent, c))
    add_count("Upcoming sales listed",
              lambda: _count_created_le(db, models.UpcomingSale, now),
              lambda c: _count_created_le(db, models.UpcomingSale, c))

    # ---- Price index (value metric — signed $ move) ----
    add_value("Genetics Price Index (semen $/straw)",
              _price_index_asof(db, now), lambda c: _price_index_asof(db, c),
              unit="$", fmt="${:,.0f}")

    return {"generated_at": now, "windows": WINDOWS, "metrics": metrics}
