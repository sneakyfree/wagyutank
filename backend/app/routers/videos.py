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
        "title": v.title, "title_en": v.title_en, "channel": v.channel, "channel_id": v.channel_id,
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
    d["editorial"] = v.editorial
    if v.channel_id:
        d["claimed_by_handle"] = _claimed_map(db, [v.channel_id]).get(v.channel_id)
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


# ---------------------------------------------------------------- Native upload
# The gradient's step 3: members upload directly to WagyuTank (R2, presigned
# browser PUT — the file never touches our server). Same table, same pages.
from fastapi import Body  # noqa: E402
from ..config import settings as _cfg  # noqa: E402
from ..models import ChannelClaim, User  # noqa: E402
from ..security import get_current_user  # noqa: E402

ALLOWED_VIDEO_TYPES = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024  # 500 MB


def _r2():
    if not (_cfg.r2_access_key_id and _cfg.r2_secret_access_key and _cfg.r2_endpoint):
        raise HTTPException(503, "Native uploads aren't configured on this server yet.")
    import boto3
    return boto3.client("s3", endpoint_url=_cfg.r2_endpoint, region_name="auto",
                        aws_access_key_id=_cfg.r2_access_key_id,
                        aws_secret_access_key=_cfg.r2_secret_access_key)


@router.post("/upload-intent")
def upload_intent(content_type: str = Body(...), size: int = Body(...),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ext = ALLOWED_VIDEO_TYPES.get(content_type)
    if not ext:
        raise HTTPException(400, "Please upload an MP4, WebM, or MOV file.")
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "Videos are capped at 500 MB for now — trim or compress and retry.")
    import secrets
    key = f"native/{user.id}/{secrets.token_urlsafe(9)}{ext}"
    url = _r2().generate_presigned_url(
        "put_object", Params={"Bucket": _cfg.r2_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=3600)
    return {"upload_url": url, "key": key}


@router.post("/upload-complete")
def upload_complete(key: str = Body(...), title: str = Body(...),
                    animal_reg: str | None = Body(None), description: str | None = Body(None),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not key.startswith(f"native/{user.id}/"):
        raise HTTPException(403, "That upload doesn't belong to you.")
    s3 = _r2()
    try:
        head = s3.head_object(Bucket=_cfg.r2_bucket, Key=key)
    except Exception:
        raise HTTPException(400, "Upload not found — did the file transfer finish?")
    if head.get("ContentLength", 0) > MAX_UPLOAD_BYTES:
        s3.delete_object(Bucket=_cfg.r2_bucket, Key=key)
        raise HTTPException(400, "File exceeds the 500 MB cap.")
    title = (title or "").strip()[:300]
    if not title:
        raise HTTPException(400, "Give your video a title.")
    import re as _re
    regs = [m.replace(" ", "").upper() for m in
            _re.findall(r"\b(?:FB|TF|PB|AF|EAF)\s?\d{2,7}\b|\b[A-Z]{4,8}[FMS]\d{4,6}\b", f"{title} {animal_reg or ''}")]
    v = WagyuVideo(
        source="native", file_url=f"{_cfg.r2_public_base}/{key}",
        title=title, description=(description or "")[:1200],
        channel=user.display_name or user.handle, lang="en",
        matched_regs=list(dict.fromkeys(regs)),
        matched_animal_reg=(animal_reg or "").strip().upper() or None,
        submitted_by=user.id, status="approved", embeddable=True, query="native-upload",
    )
    db.add(v)
    db.commit(); db.refresh(v)
    return {"id": v.id, "file_url": v.file_url, "title": v.title}


# ---------------------------------------------------------------- Claim your channel
@router.post("/channels/claim")
def claim_channel(channel_id: str = Body(...), channel: str | None = Body(None),
                  note: str | None = Body(None),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not channel_id:
        raise HTTPException(400, "Missing channel id.")
    existing = db.query(ChannelClaim).filter(ChannelClaim.channel_id == channel_id,
                                             ChannelClaim.status != "rejected").first()
    if existing:
        if existing.user_id == user.id:
            return {"ok": True, "status": existing.status,
                    "message": "You've already claimed this channel — it's " + existing.status + "."}
        raise HTTPException(409, "This channel has already been claimed.")
    c = ChannelClaim(channel_id=channel_id, channel=channel, user_id=user.id, note=(note or "")[:300])
    db.add(c)
    db.commit()
    return {"ok": True, "status": "pending",
            "message": "Claim submitted! The WagyuTank team will verify and link this channel to your profile."}


def _claimed_map(db: Session, channel_ids: list) -> dict:
    if not channel_ids:
        return {}
    rows = (db.query(ChannelClaim, User.handle).join(User, ChannelClaim.user_id == User.id)
            .filter(ChannelClaim.status == "approved", ChannelClaim.channel_id.in_(channel_ids)).all())
    return {c.channel_id: h for c, h in rows}
