"""Enrich the Wagyu Theater: translate Japanese titles to English and write a
short, grounded WagyuTank editorial note for the most-watched videos.

Editorial notes are context/curation — grounded ONLY in the video's real
title, description, channel, and our registry data (we can't watch the video).
Safe to re-run; skips rows already enriched.

  python -m app.jobs.enrich_videos [--editorial-top N]
"""
import sys
import time

from ..db import SessionLocal
from ..models import Animal, WagyuVideo
from ..services.ai import chat
from ..services.translate import translate_batch

ED_SYS = (
    "You write 60-110 word editorial notes for WagyuTank, the Wagyu breed's "
    "knowledge hub. Given a YouTube video's title, channel, category, and "
    "description excerpt (plus registry facts when provided), write ONE short "
    "note telling a Wagyu breeder why this video is worth watching and what "
    "context matters. Ground every claim ONLY in the provided text — never "
    "invent scenes, numbers, or outcomes. No greetings, no 'this video', start "
    "mid-thought like a magazine deck. Plain text only."
)


def main():
    top_n = 120
    if "--editorial-top" in sys.argv:
        top_n = int(sys.argv[sys.argv.index("--editorial-top") + 1])
    db = SessionLocal()
    try:
        # ---- 1. Translate Japanese titles ----
        ja = (db.query(WagyuVideo)
              .filter(WagyuVideo.lang == "ja", WagyuVideo.title_en == None)  # noqa: E711
              .order_by(WagyuVideo.views.desc().nullslast()).limit(120).all())
        if ja:
            items = [{"id": v.id, "text": v.title} for v in ja]
            got = translate_batch(db, items, "en")
            n = 0
            for v in ja:
                t = got.get(v.id)
                if t:
                    v.title_en = t[:300]
                    n += 1
            db.commit()
            print(f"Translated {n}/{len(ja)} Japanese titles.")

        # ---- 2. Editorial notes for the most-watched ----
        rows = (db.query(WagyuVideo)
                .filter(WagyuVideo.status == "approved", WagyuVideo.editorial == None)  # noqa: E711
                .order_by(WagyuVideo.views.desc().nullslast()).limit(top_n).all())
        wrote = 0
        for v in rows:
            facts = [f"Title: {v.title_en or v.title}", f"Channel: {v.channel}",
                     f"Category: {v.category}"]
            if v.title_en and v.title_en != v.title:
                facts.append(f"Original Japanese title: {v.title}")
            if v.description:
                facts.append(f"Description excerpt: {v.description[:400]}")
            if v.matched_animal_reg:
                a = db.query(Animal).filter(Animal.registration_no == v.matched_animal_reg).first()
                if a:
                    facts.append(f"Registry: this video involves {a.name} ({a.registration_no}), "
                                 f"{a.bloodline or ''} bloodline foundation animal.")
            out = None
            for _ in range(2):
                try:
                    out = chat(ED_SYS, "\n".join(facts), max_tokens=220)
                except Exception:
                    out = None
                if out:
                    break
                time.sleep(5)
            if out and len(out.strip()) > 40:
                v.editorial = out.strip()[:900]
                wrote += 1
                db.commit()
            time.sleep(0.8)
        print(f"Wrote {wrote} editorial notes (top {top_n} by views).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
