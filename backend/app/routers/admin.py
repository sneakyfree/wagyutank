"""Staff control panel API. The router is gated by require_staff (manager and
up); sensitive mutations add require_admin/require_super_admin per route.

Overview KPIs + time-series, member management + role assignment, owner
analytics (what sells, what drives traffic), the marketing email export,
Roundup + ad moderation, catalog submissions, live LLM-provider switching,
and runtime settings."""
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings as cfg
from ..db import get_db
from ..models import (
    Ad, AggregatedListing, AuditLog, Campaign, Event, JobRun, Listing, Order,
    SourceHealth, User,
)
from ..roles import ASSIGNABLE_ROLES, RANK, rank
from ..security import (
    create_unsubscribe_token, require_admin, require_staff, require_super_admin,
)
from ..services import ai, settings_store
from ..services import email as mail


def _audit(db: Session, admin: User, action: str, target_type: str | None = None,
           target_id=None, detail: dict | None = None):
    db.add(AuditLog(admin_id=admin.id, admin_email=admin.email, action=action,
                    target_type=target_type, target_id=(str(target_id) if target_id is not None else None),
                    detail=detail))
    db.commit()

# Panel visibility (analytics, members, moderation) is open to managers and up;
# individual mutating routes below add Depends(require_admin/require_super_admin).
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_staff)])


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _timeseries(db: Session, col, days: int = 30, where=None) -> list[dict]:
    """Daily counts for the last `days` days, gaps filled with 0."""
    start = (_now() - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    q = db.query(func.date(col).label("d"), func.count().label("n")).filter(col >= start)
    if where is not None:
        q = q.filter(where)
    rows = {str(r.d): r.n for r in q.group_by(func.date(col)).all()}
    out = []
    for i in range(days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        out.append({"date": d, "count": rows.get(d, 0)})
    return out


# ---------------------------------------------------------------- Overview
@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    now = _now()
    wk = now - timedelta(days=7)
    users = db.query(User).filter(User.account_status != "deleted")
    ad_agg = db.query(func.coalesce(func.sum(Ad.impressions), 0), func.coalesce(func.sum(Ad.clicks), 0)).first()
    paid = db.query(Order).filter(Order.status == "paid")
    return {
        "users": {
            "total": users.count(),
            "new_7d": users.filter(User.created_at >= wk).count(),
            "sellers": users.filter(User.stripe_account_id != None).count(),  # noqa: E711
            "suspended": db.query(User).filter(User.account_status == "suspended").count(),
            "marketing_opt_in": users.filter(User.marketing_opt_in == True).count(),  # noqa: E712
            "staff": {
                "managers": users.filter(User.role == "manager").count(),
                "admins": users.filter(User.role == "admin").count(),
                "super_admins": users.filter(User.role == "super_admin").count(),
            },
        },
        "listings": {
            "active": db.query(Listing).filter(Listing.status == "active").count(),
            "total": db.query(Listing).count(),
            "by_type": {k.value: v for k, v in
                        db.query(Listing.product_type, func.count()).group_by(Listing.product_type).all()},
        },
        "roundup": {
            "active": db.query(AggregatedListing).filter(AggregatedListing.status == "active").count(),
            "flagged": db.query(AggregatedListing).filter(AggregatedListing.flagged == True).count(),  # noqa: E712
            "css_eligible": db.query(AggregatedListing).filter(
                AggregatedListing.status == "active", AggregatedListing.css_status == "css").count(),
            "sources": db.query(AggregatedListing.source_site).filter(
                AggregatedListing.status == "active").distinct().count(),
            "total_clicks": db.query(func.coalesce(func.sum(AggregatedListing.outbound_clicks), 0)).scalar(),
        },
        "ads": {
            "active": db.query(Ad).filter(Ad.status == "active").count(),
            "pending": db.query(Ad).filter(Ad.status == "pending").count(),
            "impressions": ad_agg[0], "clicks": ad_agg[1],
        },
        "orders": {
            "paid": paid.count(),
            "gmv_cents": db.query(func.coalesce(func.sum(Order.amount_cents), 0)).filter(
                Order.status == "paid").scalar(),
        },
        "charts": {
            "signups": _timeseries(db, User.created_at),
            "listings": _timeseries(db, Listing.created_at),
            "roundup_indexed": _timeseries(db, AggregatedListing.first_seen_at),
            "orders": _timeseries(db, Order.created_at, where=(Order.status == "paid")),
        },
        "ai_provider": ai.active_provider_label(),
    }


# ---------------------------------------------------------------- System health
JOBS = [
    {"key": "news", "label": "News crawler", "detail": "38 feeds + Bing + GDELT", "cadence": "3×/day"},
    {"key": "highlights", "label": "News highlights (AI)", "detail": "world-Wagyu synthesis", "cadence": "3×/day"},
    {"key": "radar", "label": "Sale radar", "detail": "auto-detect auctions from news", "cadence": "3×/day"},
    {"key": "roundup", "label": "Roundup aggregator", "detail": "55 genetics-seller sources", "cadence": "daily"},
    {"key": "price_snapshot", "label": "Price index snapshot", "detail": "genetics price trend", "cadence": "daily"},
    {"key": "digest", "label": "Wagyu Wire digest", "detail": "weekly email", "cadence": "weekly"},
]


@router.get("/health")
def health(db: Session = Depends(get_db)):
    from ..services import health as h
    jobs = []
    for j in JOBS:
        last = (db.query(JobRun).filter(JobRun.job == j["key"])
                .order_by(JobRun.started_at.desc()).first())
        cad = h.JOB_CADENCE_H.get(j["key"], 30)
        status = h.job_status(last.started_at if last else None, cad)
        # last time this job actually contributed (added > 0)
        last_ok = (db.query(JobRun).filter(JobRun.job == j["key"], JobRun.added > 0)
                   .order_by(JobRun.started_at.desc()).first())
        jobs.append({**j, "status": status,
                     "last_run": last.started_at if last else None,
                     "last_ok": last.ok if last else None,
                     "last_added": last.added if last else None,
                     "last_seen": last.seen if last else None,
                     "last_error": last.error if last else None,
                     "last_contributed": last_ok.started_at if last_ok else None})
    # source-level health, worst (stalest) first
    srcs = db.query(SourceHealth).order_by(SourceHealth.last_ok_at.asc().nullsfirst()).all()
    now = _now()
    sources = []
    for s in srcs:
        run_h = ((now - s.last_run_at).total_seconds() / 3600) if s.last_run_at else None
        ok_h = ((now - s.last_ok_at).total_seconds() / 3600) if s.last_ok_at else None
        sources.append({"key": s.key, "type": s.type, "label": s.label,
                        "last_run": s.last_run_at, "last_contributed": s.last_ok_at,
                        "last_count": s.last_count, "runs": s.runs, "ok_runs": s.ok_runs,
                        "run_hours_ago": round(run_h, 1) if run_h is not None else None,
                        "never_contributed": s.ok_runs == 0})
    summary = {
        "jobs_total": len(jobs),
        "jobs_healthy": sum(1 for j in jobs if j["status"] == "healthy"),
        "jobs_stale": sum(1 for j in jobs if j["status"] in ("stale", "down")),
        "sources_total": len(sources),
        "sources_never_contributed": sum(1 for s in sources if s["never_contributed"]),
    }
    return {"jobs": jobs, "sources": sources, "summary": summary, "server_time": now}


# ---------------------------------------------------------------- Analytics
@router.get("/analytics")
def analytics(days: int = 30, db: Session = Depends(get_db)):
    now = _now()
    start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    pv = Event.type == "page_view"

    # daily unique visitors (distinct session)
    uniq_rows = {str(r[0]): r[1] for r in db.query(
        func.date(Event.created_at), func.count(func.distinct(Event.session_id))
    ).filter(pv, Event.created_at >= start).group_by(func.date(Event.created_at)).all()}
    visitors_series, pv_series = [], []
    pv_rows = {r["date"]: r["count"] for r in _timeseries(db, Event.created_at, days, where=pv)}
    for i in range(days):
        d = (start + timedelta(days=i)).strftime("%Y-%m-%d")
        visitors_series.append({"date": d, "count": uniq_rows.get(d, 0)})
        pv_series.append({"date": d, "count": pv_rows.get(d, 0)})

    top_pages = [{"path": p or "(none)", "views": n} for p, n in db.query(Event.path, func.count())
                 .filter(pv, Event.created_at >= start).group_by(Event.path)
                 .order_by(func.count().desc()).limit(10).all()]
    top_searches = [{"q": q, "n": n} for q, n in db.query(
        func.json_extract(Event.meta, "$.q"), func.count())
        .filter(Event.type == "search", Event.created_at >= start)
        .group_by(func.json_extract(Event.meta, "$.q")).order_by(func.count().desc()).limit(10).all() if q]
    referrers = [{"ref": r, "n": n} for r, n in db.query(Event.referrer, func.count())
                 .filter(pv, Event.referrer != None, Event.created_at >= start)  # noqa: E711
                 .group_by(Event.referrer).order_by(func.count().desc()).limit(8).all() if r]

    visitors = db.query(func.count(func.distinct(Event.session_id))).filter(pv, Event.created_at >= start).scalar() or 0
    signups = db.query(User).filter(User.created_at >= start).count()
    sellers = db.query(User).filter(User.created_at >= start, User.stripe_account_id != None).count()  # noqa: E711
    purchases = db.query(Order).filter(Order.created_at >= start, Order.status == "paid").count()

    # ---- What's selling: most-viewed native listings + best-selling by orders ----
    top_listings = [{"id": li.id, "title": li.title, "product_type": li.product_type.value,
                     "views": li.views, "price": li.unit_price,
                     "seller": li.seller.handle if li.seller else None}
                    for li in db.query(Listing)
                    .filter(Listing.status == "active", Listing.is_sample == False)  # noqa: E712
                    .order_by(Listing.views.desc()).limit(10).all()]
    best_sellers = [{"title": t or "(removed)", "orders": n, "gmv": (g or 0) / 100}
                    for t, n, g in db.query(Listing.title, func.count(Order.id),
                                            func.coalesce(func.sum(Order.amount_cents), 0))
                    .join(Order, Order.listing_id == Listing.id)
                    .filter(Order.status == "paid").group_by(Listing.id)
                    .order_by(func.count(Order.id).desc()).limit(10).all()]
    sales_by_type = [{"type": (pt.value if hasattr(pt, "value") else pt), "orders": n, "gmv": (g or 0) / 100}
                     for pt, n, g in db.query(Listing.product_type, func.count(Order.id),
                                              func.coalesce(func.sum(Order.amount_cents), 0))
                     .join(Order, Order.listing_id == Listing.id)
                     .filter(Order.status == "paid").group_by(Listing.product_type).all()]

    # ---- What draws the crowd: most-viewed animal/bloodline pages + Roundup demand ----
    top_animals = [{"path": p, "views": n} for p, n in db.query(Event.path, func.count())
                   .filter(pv, Event.path.like("/animal%"), Event.created_at >= start)
                   .group_by(Event.path).order_by(func.count().desc()).limit(10).all() if p]
    roundup_demand = [{"title": (r.animal_name or r.title or "")[:48], "source": r.source_site,
                       "clicks": r.outbound_clicks, "url": r.source_url}
                      for r in db.query(AggregatedListing)
                      .filter(AggregatedListing.outbound_clicks > 0)
                      .order_by(AggregatedListing.outbound_clicks.desc()).limit(10).all()]

    return {
        "days": days, "has_data": (db.query(Event).count() > 0),
        "charts": {"visitors": visitors_series, "page_views": pv_series},
        "top_pages": top_pages, "top_searches": top_searches, "referrers": referrers,
        "funnel": [{"step": "Visitors", "n": visitors}, {"step": "Signups", "n": signups},
                   {"step": "Sellers", "n": sellers}, {"step": "Purchases", "n": purchases}],
        "top_listings": top_listings, "best_sellers": best_sellers, "sales_by_type": sales_by_type,
        "top_animals": top_animals, "roundup_demand": roundup_demand,
    }


# ---------------------------------------------------------------- Users
def _user_row(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "handle": u.handle,
            "role": u.role, "account_status": u.account_status, "is_seller": u.is_seller,
            "stripe_account_id": u.stripe_account_id, "phone": u.phone, "country": u.country,
            "marketing_opt_in": u.marketing_opt_in, "created_at": u.created_at,
            "last_login_at": u.last_login_at,
            "listings": db_count_listings(u)}


def db_count_listings(u: User) -> int:
    from ..db import SessionLocal
    db = SessionLocal()
    try:
        return db.query(Listing).filter(Listing.seller_id == u.id).count()
    finally:
        db.close()


@router.get("/users")
def list_users(q: str | None = None, status: str | None = None, role: str | None = None,
               limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    query = db.query(User)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(func.lower(User.email).like(like) | func.lower(User.display_name).like(like))
    if status:
        query = query.filter(User.account_status == status)
    if role:
        query = query.filter(User.role == role)
    total = query.count()
    rows = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "users": [_user_row(u) for u in rows]}


def _can_act_on(actor: User, target: User) -> bool:
    """A staff member may act only on accounts strictly below their rank —
    except super admins, who can also manage each other (co-owners)."""
    ar, tr = rank(actor.role), rank(target.role)
    if ar < tr:
        return False
    if ar == tr and actor.role != "super_admin":
        return False
    return True


@router.post("/users/{user_id}/action")
def user_action(user_id: int, action: str = Body(..., embed=True),
                role: str | None = Body(None, embed=True),
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id:
        raise HTTPException(400, "You can't change your own role or status here.")
    if action in ("suspend", "activate", "delete", "set_role") and not _can_act_on(admin, u):
        raise HTTPException(403, "You can't act on an account at or above your own level.")

    if action == "suspend":
        u.account_status = "suspended"
    elif action == "activate":
        u.account_status = "active"
    elif action == "delete":  # soft delete — preserve FK integrity + audit trail
        u.account_status = "deleted"
        u.email = f"deleted+{u.id}@wagyutank.invalid"
        u.handle = None
    elif action == "set_role":
        if role not in ASSIGNABLE_ROLES:
            raise HTTPException(400, "Unknown role.")
        # Assigning or removing an admin/super-admin is reserved to super admins.
        touches_admin_tier = rank(role) >= RANK["admin"] or rank(u.role) >= RANK["admin"]
        if touches_admin_tier and admin.role != "super_admin":
            raise HTTPException(403, "Only a super admin can assign or remove admins.")
        # You can never grant a role above your own authority.
        if rank(role) > rank(admin.role):
            raise HTTPException(403, "You can't assign a role above your own level.")
        # Never demote the last remaining active super admin.
        if u.role == "super_admin" and role != "super_admin":
            others = db.query(User).filter(User.role == "super_admin",
                                           User.account_status == "active", User.id != u.id).count()
            if others == 0:
                raise HTTPException(400, "You can't remove the last super admin.")
        u.role = role
    else:
        raise HTTPException(400, "Unknown action")
    db.commit()
    detail = {"email": u.email}
    if action == "set_role":
        detail["role"] = role
    _audit(db, admin, f"user.{action}", "user", u.id, detail)
    return {"ok": True, "status": u.account_status, "role": u.role}


@router.post("/users/{user_id}/message")
def message_user(user_id: int, subject: str = Body(...), body: str = Body(...),
                 admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Send a one-off direct email to a single member (transactional, not marketing)."""
    u = db.get(User, user_id)
    if not u or u.account_status == "deleted":
        raise HTTPException(404, "User not found")
    safe = (body or "").replace("\n", "<br>")
    html = mail._shell(f"<p>{safe}</p><p style='color:#999;font-size:12px;margin-top:20px'>"
                       f"This is a direct message from the WagyuTank team. "
                       f"Reply to this email to reach us.</p>")
    ok = mail.send(u.email, subject[:200], html)
    _audit(db, admin, "user.message", "user", u.id, {"email": u.email, "subject": subject[:120]})
    return {"ok": ok, "sent_to": u.email}


@router.get("/email-list.csv", response_class=PlainTextResponse)
def email_list(opted_in_only: bool = True, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = db.query(User).filter(User.account_status == "active")
    if opted_in_only:
        q = q.filter(User.marketing_opt_in == True)  # noqa: E712
    lines = ["email,name,role,seller,country,joined"]
    for u in q.order_by(User.created_at.desc()).all():
        name = (u.display_name or "").replace(",", " ")
        lines.append(f"{u.email},{name},{u.role},{int(u.is_seller)},{u.country or ''},"
                     f"{u.created_at.date() if u.created_at else ''}")
    return "\n".join(lines)


@router.get("/catalog-export.csv", response_class=PlainTextResponse)
def catalog_export(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Semen listings opted into the printed catalog — the print-run worksheet."""
    from ..models import Listing, ListingStatus
    rows = (db.query(Listing).filter(Listing.catalog_opt_in == True,  # noqa: E712
                                     Listing.status == ListingStatus.ACTIVE)
            .order_by(Listing.created_at).all())
    lines = ["listing_id,title,seller,seller_email,animal_reg,price_usd,css_status,created"]
    for li in rows:
        title = (li.title or "").replace(",", " ")
        seller = (li.seller.display_name or "").replace(",", " ") if li.seller else ""
        email = li.seller.email if li.seller else ""
        lines.append(f"{li.id},{title},{seller},{email},{li.animal_reg or ''},"
                     f"{li.unit_price or ''},{li.css_status},{li.created_at.date()}")
    return "\n".join(lines)


# ---------------------------------------------------------------- Settings + AI
_SETTING_DEFAULTS = {
    "ai_provider": cfg.ai_provider,
    "anthropic_adcopy_model": cfg.anthropic_adcopy_model,
    "openai_adcopy_model": cfg.openai_adcopy_model,
    "windymind_adcopy_model": cfg.windymind_adcopy_model or "auto",
    "ads_free_launch": cfg.ads_free_launch,
    "platform_fee_bps": cfg.platform_fee_bps,
    "aggregator_enabled": True,
    "news_enabled": True,
    "digest_enabled": True,
    "require_admin_2fa": False,
    # Printed Semen Catalog — the current open edition (admin-editable, no redeploy).
    "catalog_edition_key": "2026-northern",
    "catalog_edition_label": "2026 Northern Hemisphere Edition",
    "catalog_deadline": "February 1, 2026",
    "catalog_mail_month": "March 2026",
    "catalog_submit_open": True,
}

# Every place the platform calls an LLM — surfaced so the admin knows what a swap affects.
AI_INSERTION_POINTS = [
    {"where": "Ad-copy generator", "detail": "Writes listing descriptions from a reg number (Sell flow).",
     "model_key": "adcopy"},
    {"where": "Roundup extractor", "detail": "Pulls structured listings from crawled seller pages (daily job).",
     "model_key": "adcopy"},
    {"where": "Pedigree vision (planned)", "detail": "Reads a registry screenshot into a pedigree.",
     "model_key": "vision"},
]


@router.get("/settings")
def get_settings():
    stored = settings_store.all()
    merged = {k: stored.get(k, v) for k, v in _SETTING_DEFAULTS.items()}
    return {
        "settings": merged,
        "providers": ["template", "anthropic", "openai", "windymind"],
        "provider_available": {
            "anthropic": bool(cfg.anthropic_api_key),
            "openai": bool(cfg.openai_api_key),
            "windymind": bool(cfg.windymind_api_key and cfg.windymind_base_url),
            "template": True,
        },
        "active_provider": ai.active_provider_label(),
        "ai_insertion_points": AI_INSERTION_POINTS,
        "stripe_mode": "live" if (cfg.stripe_secret_key or "").startswith("sk_live") else "test",
    }


@router.put("/settings")
def put_settings(updates: dict = Body(...), admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    allowed = set(_SETTING_DEFAULTS.keys())
    # self-lockout guard: can't enforce admin-2FA unless you personally have it on
    if updates.get("require_admin_2fa") and not admin.totp_enabled:
        raise HTTPException(400, "Enable 2FA on your own account first (Dashboard → Security) "
                                 "before requiring it for all admins.")
    applied = {k: v for k, v in updates.items() if k in allowed}
    for k, v in applied.items():
        settings_store.set(k, v)
    _audit(db, admin, "settings.update", detail=applied)
    return {"ok": True, "settings": {k: settings_store.get(k, _SETTING_DEFAULTS[k]) for k in allowed}}


@router.post("/ai/test")
def ai_test(prompt: str = Body("Say 'WagyuTank AI is online.' and nothing else.", embed=True)):
    label = ai.active_provider_label()
    try:
        out = ai.chat("You are a test probe. Answer in one short sentence.", prompt, max_tokens=60)
        return {"provider": label, "ok": bool(out), "response": out or "(template fallback — no LLM configured)"}
    except Exception as e:
        return {"provider": label, "ok": False, "error": f"{type(e).__name__}: {e}"[:300]}


# ---------------------------------------------------------------- Roundup moderation
@router.get("/roundup")
def admin_roundup(flagged: bool = False, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(AggregatedListing)
    if flagged:
        q = q.filter(AggregatedListing.flagged == True)  # noqa: E712
    rows = q.order_by(AggregatedListing.last_seen_at.desc()).limit(limit).all()
    return [{"id": r.id, "title": r.title, "animal_name": r.animal_name, "source_site": r.source_site,
             "country": r.country, "status": r.status, "flagged": r.flagged, "clicks": r.outbound_clicks,
             "source_url": r.source_url} for r in rows]


@router.post("/roundup/{listing_id}/action")
def roundup_action(listing_id: int, action: str = Body(..., embed=True),
                   admin: User = Depends(require_staff), db: Session = Depends(get_db)):
    r = db.get(AggregatedListing, listing_id)
    if not r:
        raise HTTPException(404, "Not found")
    if action == "unflag":
        r.flagged = False; r.status = "active"
    elif action == "hide":
        r.status = "hidden"
    elif action == "activate":
        r.status = "active"; r.flagged = False
    elif action == "delete":
        db.delete(r); db.commit(); _audit(db, admin, "roundup.delete", "roundup", listing_id)
        return {"ok": True, "deleted": True}
    else:
        raise HTTPException(400, "Unknown action")
    db.commit()
    _audit(db, admin, f"roundup.{action}", "roundup", listing_id)
    return {"ok": True, "status": r.status, "flagged": r.flagged}


@router.post("/roundup/run")
def roundup_run(admin: User = Depends(require_staff), db: Session = Depends(get_db)):
    """Kick off the aggregator as a detached background process."""
    try:
        subprocess.Popen([sys.executable, "-m", "app.jobs.aggregate"], start_new_session=True)
        _audit(db, admin, "roundup.crawl")
        return {"ok": True, "message": "Crawl started in the background (takes ~10-15 min)."}
    except Exception as e:
        raise HTTPException(500, f"Could not start crawl: {e}")


# ---------------------------------------------------------------- Ad moderation
@router.get("/ads")
def admin_ads(status: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Ad)
    if status:
        q = q.filter(Ad.status == status)
    rows = q.order_by(Ad.created_at.desc()).all()
    return [{"id": a.id, "advertiser_name": a.advertiser_name, "contact_email": a.contact_email,
             "headline": a.headline, "link_url": a.link_url, "placement": a.placement, "tier": a.tier,
             "status": a.status, "is_house": a.is_house, "impressions": a.impressions,
             "clicks": a.clicks, "created_at": a.created_at} for a in rows]


@router.post("/ads/{ad_id}/action")
def ad_action(ad_id: int, action: str = Body(..., embed=True),
              admin: User = Depends(require_staff), db: Session = Depends(get_db)):
    a = db.get(Ad, ad_id)
    if not a:
        raise HTTPException(404, "Not found")
    if action == "approve":
        a.status = "active"
    elif action == "reject":
        a.status = "expired"
    elif action == "pause":
        a.status = "paused"
    elif action == "delete":
        db.delete(a); db.commit(); _audit(db, admin, "ad.delete", "ad", ad_id)
        return {"ok": True, "deleted": True}
    else:
        raise HTTPException(400, "Unknown action")
    db.commit()
    _audit(db, admin, f"ad.{action}", "ad", ad_id, {"advertiser": a.advertiser_name})
    return {"ok": True, "status": a.status}


# ---------------------------------------------------------------- Audit log
@router.get("/audit")
def audit_log(limit: int = 100, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [{"id": r.id, "admin_email": r.admin_email, "action": r.action,
             "target_type": r.target_type, "target_id": r.target_id, "detail": r.detail,
             "created_at": r.created_at} for r in rows]


# ---------------------------------------------------------------- Campaigns
@router.get("/campaigns")
def list_campaigns(db: Session = Depends(get_db)):
    rows = db.query(Campaign).order_by(Campaign.created_at.desc()).limit(30).all()
    optin = db.query(User).filter(User.account_status == "active",
                                  User.marketing_opt_in == True).count()  # noqa: E712
    return {"opted_in": optin, "campaigns": [
        {"id": c.id, "subject": c.subject, "segment": c.segment, "recipients": c.recipients,
         "sent": c.sent, "status": c.status, "created_at": c.created_at} for c in rows]}


def _recipients(db: Session, segment: str) -> list[User]:
    q = db.query(User).filter(User.account_status == "active", User.marketing_opt_in == True)  # noqa: E712
    if segment == "sellers":
        q = q.filter(User.stripe_account_id != None)  # noqa: E711
    elif segment == "buyers":
        q = q.filter(User.stripe_account_id == None)  # noqa: E711
    return q.all()


@router.post("/campaign/test")
def campaign_test(subject: str = Body(...), body_html: str = Body(...),
                  admin: User = Depends(require_admin)):
    """Send the draft only to the admin, to preview it."""
    unsub = f"{cfg.app_base_url.replace('www.', 'api.')}/api/auth/unsubscribe?token={create_unsubscribe_token(admin.id)}"
    ok = mail.send(admin.email, f"[TEST] {subject}", mail.campaign_html(body_html, unsub))
    return {"ok": ok, "sent_to": admin.email}


@router.post("/digest/test")
def digest_test(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from ..services import digest
    from ..security import create_unsubscribe_token
    body = digest.build_body(db)
    unsub = f"{cfg.app_base_url.replace('www.', 'api.')}/api/auth/unsubscribe?token={create_unsubscribe_token(admin.id)}"
    ok = mail.send(admin.email, "[TEST] The Wagyu Wire", mail.campaign_html(body, unsub))
    return {"ok": ok, "sent_to": admin.email}


@router.post("/digest/send")
def digest_send(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Send the weekly digest now to all opted-in users (detached process)."""
    try:
        subprocess.Popen([sys.executable, "-m", "app.jobs.digest"], start_new_session=True)
        _audit(db, admin, "digest.send")
        return {"ok": True, "message": "Digest send started in the background."}
    except Exception as e:
        raise HTTPException(500, f"Could not start digest: {e}")


@router.post("/campaign/send")
def campaign_send(subject: str = Body(...), body_html: str = Body(...),
                  segment: str = Body("all"), admin: User = Depends(require_admin),
                  db: Session = Depends(get_db)):
    if segment not in ("all", "sellers", "buyers"):
        raise HTTPException(400, "segment must be all|sellers|buyers")
    users = _recipients(db, segment)
    camp = Campaign(subject=subject[:200], body_html=body_html, segment=segment,
                    recipients=len(users), status="sending", created_by=admin.id)
    db.add(camp); db.commit()
    api_base = cfg.app_base_url.replace("www.", "api.")
    messages = [{
        "to": u.email, "subject": subject,
        "html": mail.campaign_html(body_html,
                                   f"{api_base}/api/auth/unsubscribe?token={create_unsubscribe_token(u.id)}"),
        "unsubscribe_url": f"{api_base}/api/auth/unsubscribe?token={create_unsubscribe_token(u.id)}",
    } for u in users]
    sent = mail.send_bulk(messages)
    camp.sent = sent; camp.status = "sent"
    db.commit()
    _audit(db, admin, "campaign.send", "campaign", camp.id, {"segment": segment, "sent": sent})
    return {"ok": True, "recipients": len(users), "sent": sent, "campaign_id": camp.id}


# ---------------------------------------------------------------- Catalog submissions
@router.get("/catalog/submissions")
def catalog_submissions(edition: str | None = None, status: str | None = None,
                        db: Session = Depends(get_db)):
    from ..models import CatalogSubmission
    q = db.query(CatalogSubmission)
    if edition:
        q = q.filter(CatalogSubmission.edition == edition)
    if status:
        q = q.filter(CatalogSubmission.status == status)
    rows = q.order_by(CatalogSubmission.created_at.desc()).limit(500).all()
    editions = [e for (e,) in db.query(CatalogSubmission.edition).distinct().all()]
    return {"editions": editions, "submissions": [
        {"id": s.id, "edition": s.edition, "ranch_name": s.ranch_name,
         "animal_name": s.animal_name, "animal_reg": s.animal_reg, "bloodline": s.bloodline,
         "product_type": s.product_type, "price_note": s.price_note, "description": s.description,
         "contact_email": s.contact_email, "contact_phone": s.contact_phone, "website": s.website,
         "ship_city": s.ship_city, "ship_country": s.ship_country,
         "status": s.status, "created_at": s.created_at,
         "user_handle": (s.user.handle if s.user else None)} for s in rows]}


@router.post("/catalog/submissions/{sub_id}/action")
def catalog_submission_action(sub_id: int, action: str = Body(..., embed=True),
                              admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from ..models import CatalogSubmission
    s = db.get(CatalogSubmission, sub_id)
    if not s:
        raise HTTPException(404, "Submission not found")
    if action == "approve":
        s.status = "approved"
    elif action == "reject":
        s.status = "rejected"
    elif action == "mark_printed":
        s.status = "printed"
    elif action == "delete":
        db.delete(s); db.commit(); _audit(db, admin, "catalog.delete", "catalog_submission", sub_id)
        return {"ok": True, "deleted": True}
    else:
        raise HTTPException(400, "Unknown action")
    db.commit()
    _audit(db, admin, f"catalog.{action}", "catalog_submission", sub_id, {"ranch": s.ranch_name})
    return {"ok": True, "status": s.status}


@router.get("/catalog-submissions.csv", response_class=PlainTextResponse)
def catalog_submissions_csv(edition: str | None = None, _: User = Depends(require_admin),
                            db: Session = Depends(get_db)):
    """Print-run worksheet incl. mailing addresses for the paper copies."""
    from ..models import CatalogSubmission
    q = db.query(CatalogSubmission).filter(CatalogSubmission.status.in_(("approved", "printed")))
    if edition:
        q = q.filter(CatalogSubmission.edition == edition)
    rows = q.order_by(CatalogSubmission.ranch_name).all()

    def c(v):
        return (str(v).replace(",", " ").replace("\n", " ") if v is not None else "")
    lines = ["edition,ranch,animal,reg,bloodline,type,price_note,email,phone,website,"
             "ship_name,ship_address,ship_city,ship_region,ship_postal,ship_country,status"]
    for s in rows:
        lines.append(",".join(c(x) for x in [
            s.edition, s.ranch_name, s.animal_name, s.animal_reg, s.bloodline, s.product_type,
            s.price_note, s.contact_email, s.contact_phone, s.website,
            s.ship_name, s.ship_address, s.ship_city, s.ship_region, s.ship_postal, s.ship_country, s.status]))
    return "\n".join(lines)
