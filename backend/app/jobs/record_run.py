"""Phone-home a job run to the health dashboard.

  python -m app.jobs.record_run <job> [added]

Called at the END of the Windy-0 weekly scripts (roundup crawl, video harvest)
so the VPS health dashboard knows they actually ran. If Windy 0 is asleep or a
cron silently dies, the script never reaches this line -> no record -> the daily
watchdog flags the job as stale/down. That's the whole point: these harvesters
live on another machine, so "did it phone home?" is how we know they're alive.
"""
import sys
from datetime import datetime, timezone

from ..db import SessionLocal
from ..services import health


def main():
    if len(sys.argv) < 2:
        print("usage: python -m app.jobs.record_run <job> [added]")
        return
    job = sys.argv[1]
    added = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 0
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        health.record_job(db, job, started=now, ok=True, added=added)
        print(f"recorded run: {job} (added={added})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
