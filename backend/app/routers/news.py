"""Wagyu News — public aggregated headlines (with the translated Japanese feed)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import NewsArticle

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
def list_news(region: str | None = None, translated: bool | None = None,
              limit: int = Query(40, le=100), offset: int = 0, db: Session = Depends(get_db)):
    q = db.query(NewsArticle).filter(NewsArticle.status == "active")
    if region:
        q = q.filter(NewsArticle.region == region.upper())
    if translated is not None:
        q = q.filter(NewsArticle.is_translated == translated)
    q = q.order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.first_seen_at.desc())
    rows = q.offset(offset).limit(limit).all()
    return [{"id": r.id, "title": r.title, "original_title": r.original_title,
             "summary": r.summary, "source_name": r.source_name, "region": r.region,
             "language": r.language, "is_translated": r.is_translated,
             "published_at": r.published_at} for r in rows]


@router.get("/regions")
def regions(db: Session = Depends(get_db)):
    from sqlalchemy import func
    rows = dict(db.query(NewsArticle.region, func.count()).filter(NewsArticle.status == "active")
                .group_by(NewsArticle.region).all())
    return {"counts": rows, "total": sum(rows.values()),
            "translated": db.query(NewsArticle).filter(NewsArticle.status == "active",
                                                       NewsArticle.is_translated == True).count()}  # noqa: E712


@router.get("/{article_id}/go")
def go(article_id: int, db: Session = Depends(get_db)):
    a = db.get(NewsArticle, article_id)
    if not a:
        raise HTTPException(404, "Article not found")
    a.clicks += 1
    db.commit()
    return RedirectResponse(a.source_url, status_code=302)
