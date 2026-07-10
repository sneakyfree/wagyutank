"""The Art of Feeding Wagyu — WagyuTank's educational hub on finishing Wagyu for
marbling, with the documented science translated into every site language. All
original, sourced explainer content (never a reproduction of copyrighted papers);
honest about where verified knowledge ends and proprietary craft begins."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import WagyuVideo

router = APIRouter(prefix="/api/feeding", tags=["feeding"])

DATA = Path(__file__).resolve().parent.parent / "seed" / "data" / "feeding.json"
_cache: dict = {}

# Title keywords that mark a video as feeding/finishing-related (EN + JP).
FEED_KEYS = ["feed", "feeding", "finish", "ration", "fatten", "marbl", "nutrition",
             "肥育", "飼料", "餌", "稲わら", "ビタミン"]


def _load() -> dict:
    if not _cache:
        try:
            _cache.update(json.loads(DATA.read_text()))
        except Exception:
            _cache.update({"intro": "", "topics": [], "japanese_note": "", "video_search_terms": []})
    return _cache


def _feeding_videos(db: Session, limit: int = 12):
    clause = None
    for k in FEED_KEYS:
        c = func.lower(WagyuVideo.title).like(f"%{k.lower()}%")
        clause = c if clause is None else or_(clause, c)
    rows = (db.query(WagyuVideo)
            .filter(WagyuVideo.status == "approved", WagyuVideo.embeddable == True, clause)  # noqa: E712
            .order_by(WagyuVideo.views.desc().nullslast()).limit(limit).all())
    return [{"id": v.id, "title": v.title_en or v.title, "channel": v.channel,
             "thumbnail_url": v.thumbnail_url, "views": v.views, "lang": v.lang} for v in rows]


@router.get("")
def feeding(lang: str = "en", db: Session = Depends(get_db)):
    d = _load()
    videos = _feeding_videos(db)
    if not lang or lang == "en":
        return {**d, "videos": videos}
    from ..services import translate as tr
    out = {
        "intro": tr.translate(db, d.get("intro", ""), lang),
        "japanese_note": tr.translate(db, d.get("japanese_note", ""), lang),
        "video_search_terms": d.get("video_search_terms", []),
        "sources": d.get("sources", []),
        "videos": videos,
        "topics": [],
    }
    for t in d.get("topics", []):
        tt = dict(t)
        if t.get("title"):
            tt["title"], _ = tr.translate_one(db, t["title"], lang)
        if t.get("body"):
            tt["body"] = tr.translate(db, t["body"], lang)
        if t.get("key_points"):
            got = tr.translate_batch(db, [{"id": i, "text": p} for i, p in enumerate(t["key_points"])], lang)
            tt["key_points"] = [got.get(i, p) for i, p in enumerate(t["key_points"])]
        out["topics"].append(tt)
    return out
