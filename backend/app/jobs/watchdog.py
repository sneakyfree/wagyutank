"""Daily WagyuTank watchdog — the 'daily manager' that checks every spider.

  python -m app.jobs.watchdog [--dry]

Runs once a day (VPS cron). It:
  1. Self-heals VPS timers that have fallen inactive/failed (restart), and
     triggers a catch-up run for any VPS job that's gone DOWN.
  2. Assesses every job + the source fleet (services.watchdog).
  3. Emails a red/yellow/green 'State of the WagyuTank' report to the owner —
     EVERY day, green or not, so silence is never mistaken for health.
  4. Records its own run, so the watchdog is itself watched.
"""
import subprocess
import sys
from datetime import datetime, timezone

from ..config import settings
from ..db import SessionLocal
from ..services import email as email_service
from ..services import health, watchdog

# VPS systemd units the watchdog may restart / trigger. Windy-0 jobs are NOT here
# (another machine) — they can only be reported, which is exactly right.
_TIMERS = ["wagyutank-news.timer", "wagyutank-aggregate.timer", "wagyutank-digest.timer"]
_JOB_SERVICE = {  # job name -> service to `systemctl start` for a catch-up run
    "news": "wagyutank-news.service",
    "roundup": "wagyutank-aggregate.service",
    "digest": "wagyutank-digest.service",
}


def _sh(*args) -> tuple[int, str]:
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return 1, str(e)


def _self_heal(report: dict) -> list[str]:
    """Restart any timer that isn't armed; trigger a catch-up for DOWN VPS jobs.
    Best-effort — records what it did; never raises."""
    actions = []
    # 1. re-arm dead/failed timers
    for t in _TIMERS:
        rc, out = _sh("systemctl", "is-active", t)
        if out != "active":
            rc2, _ = _sh("systemctl", "restart", t)
            actions.append(f"Timer {t} was '{out or 'unknown'}' → restart "
                           f"{'ok' if rc2 == 0 else 'FAILED'}")
    # 2. catch-up run for a VPS job that's DOWN (way overdue)
    down = {j["job"] for j in report["reds"] if j["status"] == "down"}
    for job in down:
        svc = _JOB_SERVICE.get(job)
        if svc:
            rc, _ = _sh("systemctl", "start", svc)
            actions.append(f"Job '{job}' was DOWN → triggered catch-up run of {svc} "
                           f"({'started' if rc == 0 else 'FAILED'})")
    return actions


def _recipients() -> list[str]:
    raw = f"{settings.super_admin_emails},{settings.admin_emails}"
    seen, out = set(), []
    for e in raw.split(","):
        e = e.strip().lower()
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def main():
    dry = "--dry" in sys.argv
    db = SessionLocal()
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        report = watchdog.assess(db)
        actions = [] if dry else _self_heal(report)
        if actions:  # re-assess so the email reflects post-heal state
            report = watchdog.assess(db)
        html = watchdog.render_html(report, actions)
        subject = f"[{report['verdict'].upper()}] State of the WagyuTank — {watchdog.summary_line(report)}"

        if dry:
            print(subject)
            print(f"(dry run — not emailing) verdict={report['verdict']} "
                  f"jobs={len(report['jobs'])} reds={len(report['reds'])} "
                  f"actions={actions}")
        else:
            sent = 0
            for to in _recipients():
                if email_service.send(to, subject[:180], html):
                    sent += 1
            print(f"Watchdog: verdict={report['verdict']} emailed={sent} actions={len(actions)}")
            health.record_job(db, "watchdog", started=started, ok=True,
                              added=len(actions),
                              detail={"verdict": report["verdict"],
                                      "reds": [j["job"] for j in report["reds"]]})
    finally:
        db.close()


if __name__ == "__main__":
    main()
