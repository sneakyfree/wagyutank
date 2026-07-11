"""System-health telemetry — records every spider run so the admin dashboard can
show, at a glance, whether the daily gathering machines are alive and contributing."""
from datetime import datetime, timezone

from ..models import JobRun, SourceHealth


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def record_job(db, job: str, *, started, ok: bool, seen: int = 0, added: int = 0,
               detail: dict | None = None, error: str | None = None):
    db.add(JobRun(job=job, started_at=started, finished_at=_now(), ok=ok,
                  seen=seen, added=added, detail=detail, error=(error or None)))
    # keep the log tidy — retain the newest 500 runs
    old = [r[0] for r in db.query(JobRun.id).order_by(JobRun.started_at.desc()).offset(500).all()]
    if old:
        db.query(JobRun).filter(JobRun.id.in_(old)).delete(synchronize_session=False)
    db.commit()


def record_source(db, key: str, type_: str, label: str, count: int):
    now = _now()
    row = db.get(SourceHealth, key)
    if not row:
        row = SourceHealth(key=key, type=type_, label=label, runs=0, ok_runs=0)
        db.add(row)
    row.type, row.label = type_, label
    row.last_run_at = now
    row.last_count = count
    row.runs += 1
    if count > 0:
        row.last_ok_at = now
        row.ok_runs += 1
    # caller commits in batch


# Expected max gap (hours) before a job is considered STALE/overdue. Weekly jobs
# get ~7.5 days so a normal Sunday run isn't flagged mid-week; missing a full
# week trips STALE, missing two trips DOWN. The Windy-0 jobs (roundup_crawl,
# video_harvest) "phone home" a run record so a sleeping Windy 0 surfaces here.
JOB_CADENCE_H = {"news": 10, "roundup": 30, "digest": 200, "radar": 10,
                 "highlights": 10, "price_snapshot": 30,
                 "roundup_crawl": 180, "video_harvest": 180, "reaper": 180}


def job_status(last_run: datetime | None, cadence_h: float) -> str:
    if not last_run:
        return "unknown"
    hrs = (_now() - last_run).total_seconds() / 3600
    if hrs > cadence_h * 2:
        return "down"       # way overdue
    if hrs > cadence_h:
        return "stale"      # overdue
    return "healthy"
