"""Super-admin control panel API. Every route is gated by require_admin.

Overview KPIs + time-series, account management, the marketing email export,
Roundup + ad moderation, live LLM-provider switching, and runtime settings."""
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings as cfg
from ..db import get_db
from ..models import Ad, AggregatedListing, AuditLog, Campaign, Event, Listing, Order, User
from ..security import create_unsubscribe_token, require_admin
from ..services import ai, settings_store
from ..services import email as mail


def _audit(db: Session, admin: User, action: str, target_type: str | None = None,
           target_id=None, detail: dict | None = None):
    db.add(AuditLog(admin_id=admin.id, admin_email=admin.email, action=action,
                    target_type=target_type, target_id=(str(target_id) if target_id is not None else None),
                    detail=detail))
    db.commit()

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


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
    return {
        "days": days, "has_data": (db.query(Event).count() > 0),
        "charts": {"visitors": visitors_series, "page_views": pv_series},
        "top_pages": top_pages, "top_searches": top_searches, "referrers": referrers,
        "funnel": [{"step": "Visitors", "n": visitors}, {"step": "Signups", "n": signups},
                   {"step": "Sellers", "n": sellers}, {"step": "Purchases", "n": purchases}],
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


@router.post("/users/{user_id}/action")
def user_action(user_id: int, action: str = Body(..., embed=True),
                admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, "User not found")
    if u.id == admin.id and action in ("suspend", "delete", "remove_admin"):
        raise HTTPException(400, "You can't do that to your own admin account.")
    if action == "suspend":
        u.account_status = "suspended"
    elif action == "activate":
        u.account_status = "active"
    elif action == "delete":  # soft delete — preserve FK integrity + audit trail
        u.account_status = "deleted"
        u.email = f"deleted+{u.id}@wagyutank.invalid"
        u.handle = None
    elif action == "make_admin":
        u.role = "admin"
    elif action == "remove_admin":
        u.role = "user"
    else:
        raise HTTPException(400, "Unknown action")
    db.commit()
    _audit(db, admin, f"user.{action}", "user", u.id, {"email": u.email})
    return {"ok": True, "status": u.account_status, "role": u.role}


@router.get("/email-list.csv", response_class=PlainTextResponse)
def email_list(opted_in_only: bool = True, db: Session = Depends(get_db)):
    q = db.query(User).filter(User.account_status == "active")
    if opted_in_only:
        q = q.filter(User.marketing_opt_in == True)  # noqa: E712
    lines = ["email,name,role,seller,country,joined"]
    for u in q.order_by(User.created_at.desc()).all():
        name = (u.display_name or "").replace(",", " ")
        lines.append(f"{u.email},{name},{u.role},{int(u.is_seller)},{u.country or ''},"
                     f"{u.created_at.date() if u.created_at else ''}")
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
    "require_admin_2fa": False,
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
                   admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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
def roundup_run(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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
              admin: User = Depends(require_admin), db: Session = Depends(get_db)):
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
def audit_log(limit: int = 100, db: Session = Depends(get_db)):
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
