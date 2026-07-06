"""Daily aggregation job — run by a systemd timer / cron.

  python -m app.jobs.aggregate

Fetches the curated Roundup sources, extracts + upserts public Wagyu-genetics
listings, and delists ones that have vanished. Safe to run repeatedly.
"""
from ..db import Base, SessionLocal, engine
from ..services import aggregator


def main():
    Base.metadata.create_all(bind=engine)  # ensure aggregated_listings exists
    db = SessionLocal()
    try:
        stats = aggregator.run(db)
        print(f"Roundup: sources={stats['sources']} ok={stats['ok_sites']} "
              f"seen={stats['seen']} added={stats['added']} delisted={stats['delisted']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
