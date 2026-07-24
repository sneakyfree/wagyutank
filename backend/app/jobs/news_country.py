"""One-off: resolve the real country for existing news articles and correct
their macro-region. New crawls classify at ingest (news._upsert); this cleans
the backlog that was stamped with a coarse feed region.

  python -m app.jobs.news_country
"""
from sqlalchemy import text

from ..db import SessionLocal, engine
from ..models import NewsArticle
from ..services.news_geo import classify_country, region_for_country


def _ensure_column():
    with engine.begin() as conn:
        cols = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(news_articles)")}
        if "country" not in cols:
            conn.exec_driver_sql("ALTER TABLE news_articles ADD COLUMN country VARCHAR(2)")
            print("  added column news_articles.country")


def main():
    _ensure_column()
    db = SessionLocal()
    try:
        rows = db.query(NewsArticle).all()
        set_country = fixed_region = 0
        for r in rows:
            cc = classify_country(r.source_name, r.language, r.region)
            if cc:
                if r.country != cc:
                    r.country = cc
                    set_country += 1
                newr = region_for_country(cc)
                if newr and newr != r.region:
                    r.region = newr
                    fixed_region += 1
        db.commit()
        print(f"Country resolved on {set_country} articles; {fixed_region} macro-regions corrected.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
