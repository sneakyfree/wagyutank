"""Fetch + translate Wagyu news. Run by a timer several times a day.

  python -m app.jobs.news
"""
from .. import models  # noqa: F401
from ..db import Base, SessionLocal, engine
from ..services import news, settings_store


def main():
    Base.metadata.create_all(bind=engine)
    if not settings_store.get("news_enabled", True):
        print("News: disabled by admin — skipping.")
        return
    db = SessionLocal()
    try:
        stats = news.run(db)
        print(f"News: feeds={stats['feeds']} seen={stats['seen']} added={stats['added']}")
        try:
            b = news.generate_highlights(db)
            print(f"News highlights: {len(b)} bullets generated.")
        except Exception as e:
            print(f"Highlights skipped: {e}")
        try:
            from ..services import sale_radar
            r = sale_radar.scan(db)
            print(f"Sale radar: {r['candidates']} candidates, {r['added']} auto-added.")
        except Exception as e:
            print(f"Sale radar skipped: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
