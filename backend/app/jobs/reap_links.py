"""Weekly stale-link reaper — direct HTTP-checks every active Roundup listing's
source URL and delists dead ones (see services.reaper).

  python -m app.jobs.reap_links

Wired into the weekly Roundup crawl (scripts/roundup_crawl.sh) after ingest, so
stale/removed listings age out without any LLM cost.
"""
from datetime import datetime, timezone

from ..db import SessionLocal
from ..services import reaper


def main():
    db = SessionLocal()
    try:
        t0 = datetime.now(timezone.utc).replace(tzinfo=None)
        stats = reaper.reap(db)
        print(f"Reaper: checked={stats['checked']} alive={stats['alive']} "
              f"hard_dead={stats['hard_dead']} soft_dead={stats['soft_dead']} "
              f"delisted={stats['delisted']} skipped={stats['skipped']}")
        try:
            from ..services import health
            health.record_job(db, "reaper", started=t0, ok=True,
                              seen=stats["checked"], added=stats["delisted"],
                              detail={k: stats[k] for k in ("hard_dead", "soft_dead", "skipped")})
        except Exception:
            pass
    finally:
        db.close()


if __name__ == "__main__":
    main()
