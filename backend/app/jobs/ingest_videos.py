"""Ingest harvested video candidates (from scripts/harvest_videos.py) into the
Wagyu Theater. Dedupes by video_id, resolves extracted registration numbers
against our Animal spine, matches sale recordings to SaleEvent rows, and
classifies heuristically. Idempotent — re-running refreshes views/status.

  python -m app.jobs.ingest_videos videos.json
"""
import json
import re
import sys

from ..db import Base, SessionLocal, engine
from ..models import Animal, SaleEvent, WagyuVideo, utcnow

JP_RE = re.compile(r"[぀-ヿ一-鿿]")


def classify(item: dict) -> tuple[str, str]:
    """(category, lang) from the harvest hint + title heuristics."""
    title = item.get("title") or ""
    hay = f"{title} {item.get('description') or ''}".lower()
    lang = "ja" if JP_RE.search(title) else "en"
    hint = item.get("category_hint") or "general"
    if item.get("extracted_regs") or hint == "sire":
        cat = "sire"
    elif any(k in hay for k in ("auction", "sale results", "lot ", "bidding", "セリ")):
        cat = "sale"
    elif any(k in hay for k in ("recipe", "cook", "steak", "chef", "butcher", "cutting")):
        cat = "cooking"
    elif any(k in hay for k in ("how to", "insemination", "embryo transfer", "feeding", "grading", "getting started")):
        cat = "education"
    elif lang == "ja":
        cat = "japan"
    else:
        cat = hint if hint in ("sale", "ranch", "education", "japan", "cooking") else "general"
    if lang == "ja":
        cat = "japan" if cat in ("general", "ranch") else cat
    return cat, lang


def main(path: str):
    Base.metadata.create_all(bind=engine)
    items = json.load(open(path))
    db = SessionLocal()
    try:
        # Registry lookup: reg -> canonical reg; name -> reg (for query-matched sires)
        reg_map = {}
        name_map = {}
        for a in db.query(Animal).all():
            if a.registration_no:
                reg_map[a.registration_no.replace(" ", "").upper()] = a.registration_no
            name_map[a.name.lower()] = a.registration_no
        sales = [(s.id, (s.sale_name or "").lower(), s.year) for s in db.query(SaleEvent).all()]

        added = updated = 0
        for it in items:
            vid = it.get("video_id")
            if not vid:
                continue
            cat, lang = classify(it)
            # Resolve the primary animal: extracted reg in our registry, else the query's animal
            primary = None
            for r in it.get("extracted_regs") or []:
                if r in reg_map:
                    primary = reg_map[r]
                    break
            if not primary and it.get("query_animal_name"):
                qn = it["query_animal_name"].lower()
                title_l = (it.get("title") or "").lower()
                if qn.split()[0] in title_l:
                    primary = it.get("query_animal_reg") or name_map.get(qn)
            # Sale matching: our sale name tokens + year in the title
            sale_id = None
            title_l = (it.get("title") or "").lower()
            for sid, sname, syear in sales:
                token = sname.split(" 2")[0].strip()
                if len(token) > 8 and token in title_l and (not syear or str(syear) in title_l):
                    sale_id = sid
                    break

            row = db.query(WagyuVideo).filter(WagyuVideo.video_id == vid).first()
            if row:
                row.views_prev = row.views
                row.views = it.get("views") or row.views
                row.refreshed_at = utcnow()
                if row.status == "dead" and it.get("embeddable"):
                    row.status = "approved"
                updated += 1
                continue
            db.add(WagyuVideo(
                source="youtube", video_id=vid, title=(it.get("title") or "")[:300],
                description=it.get("description"), channel=it.get("channel"),
                channel_id=it.get("channel_id"), duration=it.get("duration"),
                views=it.get("views"), category=cat, lang=lang,
                matched_regs=it.get("extracted_regs") or [],
                matched_animal_reg=primary, matched_sale_id=sale_id,
                query=it.get("query"), embeddable=bool(it.get("embeddable", True)),
                status="approved" if it.get("embeddable", True) else "hidden",
                refreshed_at=utcnow(),
            ))
            added += 1
        db.commit()
        total = db.query(WagyuVideo).count()
        matched = db.query(WagyuVideo).filter(WagyuVideo.matched_animal_reg != None).count()  # noqa: E711
        by_cat = {}
        for (c, n) in db.execute(
                __import__("sqlalchemy").text("SELECT category, COUNT(*) FROM wagyu_videos GROUP BY category")):
            by_cat[c] = n
        print(f"Ingested +{added} new, {updated} refreshed. Library: {total} videos, "
              f"{matched} matched to registry animals. By category: {by_cat}")
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "videos.json")
