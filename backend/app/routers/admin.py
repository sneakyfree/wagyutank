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
from ..models import Ad, AggregatedListing, Listing, Order, User
from ..security import require_admin
from ..services import ai, settings_store

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
def put_settings(updates: dict = Body(...)):
    allowed = set(_SETTING_DEFAULTS.keys())
    for k, v in updates.items():
        if k in allowed:
            settings_store.set(k, v)
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
def roundup_action(listing_id: int, action: str = Body(..., embed=True), db: Session = Depends(get_db)):
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
        db.delete(r); db.commit(); return {"ok": True, "deleted": True}
    else:
        raise HTTPException(400, "Unknown action")
    db.commit()
    return {"ok": True, "status": r.status, "flagged": r.flagged}


@router.post("/roundup/run")
def roundup_run():
    """Kick off the aggregator as a detached background process."""
    try:
        subprocess.Popen([sys.executable, "-m", "app.jobs.aggregate"], start_new_session=True)
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
def ad_action(ad_id: int, action: str = Body(..., embed=True), db: Session = Depends(get_db)):
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
        db.delete(a); db.commit(); return {"ok": True, "deleted": True}
    else:
        raise HTTPException(400, "Unknown action")
    db.commit()
    return {"ok": True, "status": a.status}
