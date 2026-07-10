"""One-off: clean the existing news feed — archive off-topic articles and
collapse cross-source duplicates. New crawls stay clean via news._upsert.

  python -m app.jobs.repair_news
"""
from ..db import SessionLocal
from ..models import NewsArticle
from ..services.news import _relevant, _title_key


def main():
    db = SessionLocal()
    try:
        rows = (db.query(NewsArticle).filter(NewsArticle.status == "active")
                .order_by(NewsArticle.first_seen_at.desc()).all())
        seen_titles: set[str] = set()
        off = dup = 0
        for r in rows:
            item = {"title": r.title, "original_title": r.original_title, "summary": r.summary}
            if not _relevant(item):
                r.status = "archived"; off += 1
                continue
            tk = _title_key(r.original_title or r.title)
            if tk and len(tk) > 12:
                if tk in seen_titles:
                    r.status = "archived"; dup += 1
                    continue
                seen_titles.add(tk)
        db.commit()
        remaining = db.query(NewsArticle).filter(NewsArticle.status == "active").count()
        print(f"Archived {off} off-topic + {dup} duplicate articles. {remaining} clean articles remain.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
