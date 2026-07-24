"""Wagyu News — public aggregated headlines (with the translated Japanese feed)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import NewsArticle

router = APIRouter(prefix="/api/news", tags=["news"])


_WINDOW_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


@router.get("")
def list_news(region: str | None = None, translated: bool | None = None, q: str | None = None,
              window: str | None = None, year: int | None = None, sort: str = "recent",
              limit: int = Query(40, le=100), offset: int = 0, db: Session = Depends(get_db)):
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func, or_
    query = db.query(NewsArticle).filter(NewsArticle.status == "active")
    if region:
        query = query.filter(NewsArticle.region == region.upper())
    if translated is not None:
        query = query.filter(NewsArticle.is_translated == translated)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(NewsArticle.title).like(like),
                                 func.lower(NewsArticle.original_title).like(like)))
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if window in _WINDOW_DAYS:
        query = query.filter(NewsArticle.published_at >= now - timedelta(days=_WINDOW_DAYS[window]))
    if year:
        query = query.filter(func.strftime("%Y", NewsArticle.published_at) == str(year))
    if sort == "trending":
        # hottest = most clicked, then most recent
        query = query.order_by(NewsArticle.clicks.desc(),
                               NewsArticle.published_at.desc().nullslast())
    else:
        query = query.order_by(NewsArticle.published_at.desc().nullslast(),
                               NewsArticle.first_seen_at.desc())
    rows = query.offset(offset).limit(limit).all()
    return [{"id": r.id, "title": r.title, "original_title": r.original_title,
             "summary": r.summary, "source_name": r.source_name, "region": r.region,
             "country": r.country, "language": r.language, "is_translated": r.is_translated,
             "clicks": r.clicks, "published_at": r.published_at} for r in rows]


@router.get("/highlights")
def highlights(db: Session = Depends(get_db)):
    """Auto-generated 'state of world Wagyu' bullet synthesis (cached; refreshed daily)."""
    from ..services import settings_store
    data = settings_store.get("news_highlights", None)
    return data or {"bullets": [], "generated": None}


@router.get("/years")
def years(db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = db.query(func.strftime("%Y", NewsArticle.published_at)).filter(
        NewsArticle.status == "active", NewsArticle.published_at != None).distinct().all()  # noqa: E711
    ys = sorted({int(r[0]) for r in rows if r[0] and r[0].isdigit()}, reverse=True)
    return {"years": ys}


@router.get("/regions")
def regions(db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = dict(db.query(NewsArticle.region, func.count()).filter(NewsArticle.status == "active")
                .group_by(NewsArticle.region).all())
    return {"counts": rows, "total": sum(rows.values()),
            "translated": db.query(NewsArticle).filter(NewsArticle.status == "active",
                                                       NewsArticle.is_translated == True).count()}  # noqa: E712


@router.get("/{article_id}")
def get_article(article_id: int, lang: str = "en", db: Session = Depends(get_db)):
    """On-site article view — headline + our summary, translatable to any of the
    site languages, with a clear link to the original source. This is what the
    reader lands on (instead of an immediate bounce) so a language selector has
    somewhere to live."""
    a = db.get(NewsArticle, article_id)
    if not a or a.status not in ("active", "archived"):
        raise HTTPException(404, "Article not found")
    title = a.title
    summary = a.summary
    translated = False
    if lang and lang != "en":
        from ..services import translate
        title, t1 = translate.translate_one(db, a.title, lang)
        if a.summary:
            summary, t2 = translate.translate_one(db, a.summary, lang)
        translated = t1
    return {
        "id": a.id, "title": title, "original_title": a.original_title,
        "english_title": a.title, "summary": summary, "source_name": a.source_name,
        "source_url": a.source_url, "region": a.region, "country": a.country, "language": a.language,
        "is_translated": a.is_translated, "published_at": a.published_at,
        "lang": lang, "translated": translated, "clicks": a.clicks,
    }


@router.get("/{article_id}/go")
def go(article_id: int, db: Session = Depends(get_db)):
    a = db.get(NewsArticle, article_id)
    if not a:
        raise HTTPException(404, "Article not found")
    a.clicks += 1
    db.commit()
    return RedirectResponse(a.source_url, status_code=302)
