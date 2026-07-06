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
    db = SessionLocal()
    try:
        stats = aggregator.run(db)
        print(f"Roundup: sources={stats['sources']} discovered={stats['discovered']} "
              f"ok={stats['ok_sites']} pages={stats['pages']} seen={stats['seen']} "
              f"added={stats['added']} delisted={stats['delisted']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
