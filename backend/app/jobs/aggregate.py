"""Daily aggregation job — run by a systemd timer / cron.

  python -m app.jobs.aggregate

Fetches the curated Roundup sources, extracts + upserts public Wagyu-genetics
listings, and delists ones that have vanished. Safe to run repeatedly.
"""
from ..db import Base, SessionLocal, engine
from ..services import aggregator


def main():
    Base.metadata.create_all(bind=engine)  # ensure aggregated_listings exists
    from ..services import settings_store
    if not settings_store.get("aggregator_enabled", True):
        print("Roundup: aggregator disabled by admin — skipping.")
        return
    from datetime import datetime, timezone
    from ..services import health
    db = SessionLocal()
    try:
        t0 = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            stats = aggregator.run(db)
            print(f"Roundup: sources={stats['sources']} discovered={stats['discovered']} "
                  f"ok={stats['ok_sites']} pages={stats['pages']} seen={stats['seen']} "
                  f"added={stats['added']} delisted={stats['delisted']}")
            health.record_job(db, "roundup", started=t0, ok=True, seen=stats["seen"], added=stats["added"],
                              detail={"sources": stats["sources"], "ok_sites": stats["ok_sites"]})
        except Exception as e:
            health.record_job(db, "roundup", started=t0, ok=False, error=str(e)); raise
        t1 = datetime.now(timezone.utc).replace(tzinfo=None)
        try:
            from ..services import price_index
            n = price_index.snapshot(db)
            print(f"Price index: {n} snapshot(s) recorded.")
            health.record_job(db, "price_snapshot", started=t1, ok=True, added=n)
        except Exception as e:
            print(f"Price index snapshot skipped: {e}")
            health.record_job(db, "price_snapshot", started=t1, ok=False, error=str(e))
    finally:
        db.close()


if __name__ == "__main__":
    main()
