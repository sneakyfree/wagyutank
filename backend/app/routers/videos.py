"""The Wagyu Theater API — browse, charts, search-by-reg, and detail pages for
the video library. Source-agnostic: YouTube embeds today, native uploads later
render through the same endpoints."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SaleEvent, WagyuVideo

router = APIRouter(prefix="/api/videos", tags=["videos"])

CATEGORIES = [
    {"key": "sire", "label": "Bulls & Bloodlines", "icon": "🐂"},
    {"key": "sale", "label": "Sales & Auctions", "icon": "🏆"},
    {"key": "japan", "label": "Japan", "icon": "🇯🇵"},
    {"key": "education", "label": "Learn", "icon": "🎓"},
    {"key": "ranch", "label": "Ranch Life", "icon": "🤠"},
    {"key": "cooking", "label": "Beef & Cooking", "icon": "🥩"},
]


def _out(v: WagyuVideo) -> dict:
    return {
        "id": v.id, "source": v.source, "video_id": v.video_id,
        "title": v.title, "title_en": v.title_en, "channel": v.channel,
        "duration": v.duration, "views": v.views, "views_prev": v.views_prev,
        "published_at": v.published_at, "category": v.category, "lang": v.lang,
        "matched_regs": v.matched_regs or [], "matched_animal_reg": v.matched_animal_reg,
        "matched_sale_id": v.matched_sale_id,
        "embed_url": v.embed_url, "thumbnail_url": v.thumbnail_url,
        "first_seen_at": v.first_seen_at,
    }


def _base(db: Session):
    return db.query(WagyuVideo).filter(WagyuVideo.status == "approved",
                                       WagyuVideo.embeddable == True)  # noqa: E712


@router.get("")
def browse(category: str | None = None, q: str | None = None, reg: str | None = None,
           lang: str | None = None, sort: str = "views",
           limit: int = Query(48, le=120), offset: int = 0, db: Session = Depends(get_db)):
    query = _base(db)
    if category:
        query = query.filter(WagyuVideo.category == category)
    if lang:
        query = query.filter(WagyuVideo.lang == lang)
    if reg:
        # the pedigree video registry: exact reg in matched list (JSON contains)
        like = f'%"{reg.upper().replace(" ", "")}"%'
        query = query.filter(or_(func.upper(WagyuVideo.matched_animal_reg) == reg.upper(),
                                 func.upper(func.cast(WagyuVideo.matched_regs, __import__("sqlalchemy").String)).like(like.upper())))
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(func.lower(WagyuVideo.title).like(like),
                                 func.lower(WagyuVideo.channel).like(like),
                                 func.upper(func.cast(WagyuVideo.matched_regs, __import__("sqlalchemy").String)).like(f"%{q.upper()}%")))
    total = query.count()
    if sort == "recent":
        query = query.order_by(WagyuVideo.published_at.desc().nullslast(), WagyuVideo.first_seen_at.desc())
    else:
        query = query.order_by(WagyuVideo.views.desc().nullslast())
    rows = query.offset(offset).limit(limit).all()
    return {"total": total, "videos": [_out(v) for v in rows], "categories": CATEGORIES}


@router.get("/charts")
def charts(db: Session = Depends(get_db)):
    """Top-100 all-time + category leaders — the Billboard of Wagyu."""
    top = _base(db).order_by(WagyuVideo.views.desc().nullslast()).limit(100).all()
    by_cat = {}
    for c in CATEGORIES:
        rows = (_base(db).filter(WagyuVideo.category == c["key"])
                .order_by(WagyuVideo.views.desc().nullslast()).limit(8).all())
        if rows:
            by_cat[c["key"]] = [_out(v) for v in rows]
    stats = {
        "total": _base(db).count(),
        "matched_animals": _base(db).filter(WagyuVideo.matched_animal_reg != None).count(),  # noqa: E711
        "japanese": _base(db).filter(WagyuVideo.lang == "ja").count(),
        "channels": db.query(func.count(func.distinct(WagyuVideo.channel))).filter(
            WagyuVideo.status == "approved").scalar(),
    }
    return {"top100": [_out(v) for v in top], "by_category": by_cat,
            "categories": CATEGORIES, "stats": stats}


@router.get("/{video_id}")
def detail(video_id: int, db: Session = Depends(get_db)):
    v = db.get(WagyuVideo, video_id)
    if not v or v.status not in ("approved", "pending"):
        raise HTTPException(404, "Video not found")
    d = _out(v)
    d["description"] = (v.description or "")[:800]
    if v.matched_sale_id:
        s = db.get(SaleEvent, v.matched_sale_id)
        if s:
            d["sale"] = {"id": s.id, "sale_name": s.sale_name, "year": s.year}
    # related: same animal first, then same category
    rel = []
    if v.matched_animal_reg:
        rel = (_base(db).filter(WagyuVideo.matched_animal_reg == v.matched_animal_reg,
                                WagyuVideo.id != v.id)
               .order_by(WagyuVideo.views.desc().nullslast()).limit(6).all())
    if len(rel) < 6:
        more = (_base(db).filter(WagyuVideo.category == v.category, WagyuVideo.id != v.id,
                                 ~WagyuVideo.id.in_([r.id for r in rel] or [0]))
                .order_by(WagyuVideo.views.desc().nullslast()).limit(6 - len(rel)).all())
        rel.extend(more)
    d["related"] = [_out(r) for r in rel]
    return d
