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
    from datetime import datetime, timezone
    from ..services import health
    db = SessionLocal()
    try:
        t0 = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            stats = news.run(db)
            print(f"News: feeds={stats['feeds']} seen={stats['seen']} added={stats['added']}")
            health.record_job(db, "news", started=t0, ok=True, seen=stats["seen"], added=stats["added"],
                              detail={"feeds": stats["feeds"]})
        except Exception as e:
            health.record_job(db, "news", started=t0, ok=False, error=str(e)); raise
        t1 = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            b = news.generate_highlights(db)
            print(f"News highlights: {len(b)} bullets generated.")
            health.record_job(db, "highlights", started=t1, ok=bool(b), added=len(b))
        except Exception as e:
            print(f"Highlights skipped: {e}")
            health.record_job(db, "highlights", started=t1, ok=False, error=str(e))
        t2 = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            from ..services import sale_radar
            r = sale_radar.scan(db)
            print(f"Sale radar: {r['candidates']} candidates, {r['added']} auto-added.")
            health.record_job(db, "radar", started=t2, ok=True, seen=r["candidates"], added=r["added"])
        except Exception as e:
            print(f"Sale radar skipped: {e}")
            health.record_job(db, "radar", started=t2, ok=False, error=str(e))
    finally:
        db.close()


if __name__ == "__main__":
    main()
