"""The daily WagyuTank watchdog — a 'state of the WagyuTank' health report.

Assesses every scheduled spider/job and the whole source fleet, then renders a
red/yellow/green executive summary emailed once a day (see jobs.watchdog). The
philosophy, learned from the live data:

  - JOB-level red is what matters (a spider genuinely stopped running). Weekly
    Windy-0 jobs report via record_run, so a sleeping Windy 0 shows up here.
  - SOURCE-level "never contributed" is benign noise (JS-SPA seed sites that
    render nothing) — counted, never alarmed on individually.
  - A source that WAS contributing and went quiet is a real regression — flagged.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ..models import JobRun, SourceHealth
from . import health

# job -> (human label, where it runs). Cadence comes from health.JOB_CADENCE_H.
EXPECTED_JOBS = {
    "news":           ("News aggregator (Wagyu Wire)", "VPS timer · ~3×/day"),
    "highlights":     ("News highlights synthesis", "VPS · with news"),
    "radar":          ("Sale radar (auto sales from news)", "VPS · with news"),
    "roundup":        ("Roundup static crawl", "VPS timer · daily"),
    "price_snapshot": ("Genetics price index snapshot", "VPS · daily"),
    "digest":         ("Wagyu Wire weekly digest", "VPS timer · weekly"),
    "roundup_crawl":  ("Roundup JS-render crawl", "Windy 0 · weekly Sun 4am"),
    "reaper":         ("Stale-link reaper", "Windy 0 · weekly Sun 4am"),
    "video_harvest":  ("Wagyu Theater video harvest", "Windy 0 · weekly Sun 6am"),
}

_STALE_SOURCE_H = 24 * 5   # a source that contributed within 5 days is "fresh"

_DOT = {"healthy": "#2e7d32", "stale": "#f39c12", "down": "#c0392b",
        "unknown": "#9aa0a6", "error": "#c0392b"}
_LABELWORD = {"healthy": "OK", "stale": "STALE", "down": "DOWN",
              "unknown": "NO DATA", "error": "ERROR"}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def assess(db) -> dict:
    """Build the structured health report (no I/O beyond the DB)."""
    now = _now()
    # latest run per job
    latest: dict[str, JobRun] = {}
    for r in db.query(JobRun).order_by(JobRun.started_at.desc()).all():
        latest.setdefault(r.job, r)

    jobs = []
    for job, (label, where) in EXPECTED_JOBS.items():
        r = latest.get(job)
        cad = health.JOB_CADENCE_H.get(job, 24)
        if not r:
            status = "unknown"
            hrs = None
        else:
            status = health.job_status(r.started_at, cad)
            if r.ok is False and status == "healthy":
                status = "error"   # ran on time but failed
            hrs = (now - r.started_at).total_seconds() / 3600
        jobs.append({
            "job": job, "label": label, "where": where, "status": status,
            "hours_ago": hrs, "added": (r.added if r else None),
            "ok": (r.ok if r else None), "error": (r.error if r else None),
        })

    # source fleet
    contributing = never = regressed = 0
    regressed_examples = []
    for s in db.query(SourceHealth).all():
        if not s.last_ok_at:
            never += 1
        else:
            hrs = (now - s.last_ok_at).total_seconds() / 3600
            if hrs <= _STALE_SOURCE_H:
                contributing += 1
            else:
                regressed += 1
                if len(regressed_examples) < 12:
                    regressed_examples.append({"label": s.label or s.key, "days": round(hrs / 24, 1)})
    total_sources = contributing + never + regressed

    reds = [j for j in jobs if j["status"] in ("down", "error")]
    yellows = [j for j in jobs if j["status"] in ("stale", "unknown")]
    if reds:
        verdict, verdict_word = "red", "Attention needed"
    elif yellows or regressed:
        verdict, verdict_word = "yellow", "Minor items"
    else:
        verdict, verdict_word = "green", "All systems go"

    return {
        "generated_at": now, "verdict": verdict, "verdict_word": verdict_word,
        "jobs": jobs, "reds": reds, "yellows": yellows,
        "sources": {"total": total_sources, "contributing": contributing,
                    "never": never, "regressed": regressed,
                    "regressed_examples": regressed_examples},
    }


def summary_line(report: dict) -> str:
    """One-sentence 'state of the WagyuTank' for the email subject/top."""
    v = report["verdict"]
    nj = len(report["jobs"])
    ok = sum(1 for j in report["jobs"] if j["status"] == "healthy")
    s = report["sources"]
    if v == "green":
        return f"All {nj} spiders healthy · {s['contributing']} sources contributing."
    if v == "yellow":
        bits = []
        if report["yellows"]:
            bits.append(", ".join(j["job"] for j in report["yellows"]) + " stale/no-data")
        if s["regressed"]:
            bits.append(f"{s['regressed']} sources went quiet")
        return f"{ok}/{nj} spiders healthy — watch: " + "; ".join(bits) + "."
    return (f"{ok}/{nj} spiders healthy — RED: "
            + ", ".join(j["job"] for j in report["reds"]) + " down/erroring.")


def _fmt_ago(hrs) -> str:
    if hrs is None:
        return "never"
    if hrs < 48:
        return f"{hrs:.0f}h ago"
    return f"{hrs / 24:.1f}d ago"


def render_html(report: dict, actions: list[str] | None = None) -> str:
    v = report["verdict"]
    banner = {"green": "#2e7d32", "yellow": "#f39c12", "red": "#c0392b"}[v]
    rows = ""
    for j in report["jobs"]:
        color = _DOT[j["status"]]
        word = _LABELWORD[j["status"]]
        added = "" if j["added"] is None else f"+{j['added']}"
        err = f"<div style='color:#c0392b;font-size:11px'>{(j['error'] or '')[:80]}</div>" if j["error"] else ""
        rows += (
            f"<tr>"
            f"<td style='padding:7px 8px;border-bottom:1px solid #eee'>"
            f"<span style='display:inline-block;width:9px;height:9px;border-radius:50%;"
            f"background:{color};margin-right:7px'></span>"
            f"<strong>{j['label']}</strong>{err}"
            f"<div style='color:#999;font-size:11px'>{j['where']}</div></td>"
            f"<td style='padding:7px 8px;border-bottom:1px solid #eee;color:{color};font-weight:600'>{word}</td>"
            f"<td style='padding:7px 8px;border-bottom:1px solid #eee;color:#666'>{_fmt_ago(j['hours_ago'])}</td>"
            f"<td style='padding:7px 8px;border-bottom:1px solid #eee;color:#666'>{added}</td>"
            f"</tr>"
        )
    s = report["sources"]
    tot = max(s["total"], 1)
    barw = lambda n: round(100 * n / tot)  # noqa: E731
    src_bar = (
        f"<div style='display:flex;height:14px;border-radius:7px;overflow:hidden;margin:6px 0'>"
        f"<div style='width:{barw(s['contributing'])}%;background:#2e7d32'></div>"
        f"<div style='width:{barw(s['regressed'])}%;background:#f39c12'></div>"
        f"<div style='width:{barw(s['never'])}%;background:#d5d5d5'></div></div>"
        f"<div style='font-size:12px;color:#666'>"
        f"<span style='color:#2e7d32'>&#9679;</span> {s['contributing']} contributing &nbsp; "
        f"<span style='color:#f39c12'>&#9679;</span> {s['regressed']} went quiet &nbsp; "
        f"<span style='color:#bbb'>&#9679;</span> {s['never']} never (JS-only / dead seeds — expected)</div>"
    )
    regressed = ""
    if s["regressed_examples"]:
        items = "".join(f"<li>{e['label']} — quiet {e['days']}d</li>" for e in s["regressed_examples"])
        regressed = (f"<p style='font-size:12px;color:#666;margin:10px 0 4px'><strong>Sources that "
                     f"went quiet</strong> (were contributing, now stale — worth a look):</p>"
                     f"<ul style='font-size:12px;color:#666;margin:0 0 8px'>{items}</ul>")
    act = ""
    if actions:
        items = "".join(f"<li>{a}</li>" for a in actions)
        act = (f"<p style='font-size:12px;color:#666;margin:12px 0 4px'><strong>Auto-heal actions "
               f"taken this run:</strong></p><ul style='font-size:12px;color:#2e7d32;margin:0'>{items}</ul>")
    gen = report["generated_at"].strftime("%A %b %-d, %Y · %H:%M UTC")
    return (
        f"<div style='font-family:-apple-system,Segoe UI,sans-serif;max-width:640px;margin:0 auto;color:#222'>"
        f"<div style='background:{banner};color:#fff;padding:16px 20px;border-radius:8px 8px 0 0'>"
        f"<div style='font-size:13px;opacity:.85;letter-spacing:.5px'>STATE OF THE WAGYUTANK</div>"
        f"<div style='font-size:22px;font-weight:700;margin-top:2px'>{report['verdict_word']}</div>"
        f"<div style='font-size:14px;margin-top:4px;opacity:.95'>{summary_line(report)}</div></div>"
        f"<div style='border:1px solid #eee;border-top:none;border-radius:0 0 8px 8px;padding:18px 20px'>"
        f"<table style='width:100%;border-collapse:collapse;font-size:13px'>"
        f"<thead><tr style='text-align:left;color:#999;font-size:11px'>"
        f"<th style='padding:0 8px 6px'>SPIDER / JOB</th><th style='padding:0 8px 6px'>STATUS</th>"
        f"<th style='padding:0 8px 6px'>LAST RUN</th><th style='padding:0 8px 6px'>YIELD</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
        f"<h3 style='font-size:14px;margin:20px 0 4px'>Source fleet ({s['total']} spiders)</h3>"
        f"{src_bar}{regressed}{act}"
        f"<p style='font-size:11px;color:#aaa;margin-top:18px'>Generated {gen} · WagyuTank daily watchdog. "
        f"You receive this every day; if it stops arriving, the watchdog itself may be down.</p>"
        f"</div></div>"
    )
