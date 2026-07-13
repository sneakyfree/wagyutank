"""Ingest JS-rendered seller pages (from scripts/crawl_listings.cjs, which runs
on VERON 1 — residential IP; see deploy/tank-crawl.sh) into the Roundup. Reuses the aggregator's extraction + upsert (facts + our own
neutral summary + link-back only).

  python -m app.jobs.ingest_rendered rendered_pages.json
"""
import json
import sys
from datetime import datetime, timezone

from ..db import Base, SessionLocal, engine
from ..services import aggregator, health


def main(path: str):
    Base.metadata.create_all(bind=engine)
    pages = json.load(open(path))
    db = SessionLocal()
    try:
        t0 = datetime.now(timezone.utc).replace(tzinfo=None)
        stats = aggregator.ingest_rendered_pages(db, pages)
        print(f"Rendered ingest: pages={stats['pages']} seen={stats['seen']} "
              f"added={stats['added']} sites={stats['sites']}")
        health.record_job(db, "roundup", started=t0, ok=True,
                          seen=stats["seen"], added=stats["added"],
                          detail={"source": "js-crawler", "sites": stats["sites"]})
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "rendered_pages.json")
