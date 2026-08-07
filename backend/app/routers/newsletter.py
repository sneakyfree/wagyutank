"""Public newsletter signup — deliberately no account required."""
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from .. import tank
from ..db import get_db
from ..models import Subscriber, User
from ..services import email as mail, ratelimit
from fastapi import Request


def _client_ip(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip")
            or (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))

router = APIRouter(prefix="/api/newsletter", tags=["newsletter"])

LANGS = ["en", "es", "pt", "de", "ja", "zh"]


class SubscribeIn(BaseModel):
    email: EmailStr
    lang: str = "en"
    source: str | None = None


@router.post("/subscribe")
def subscribe(body: SubscribeIn, request: Request, db: Session = Depends(get_db)):
    if not ratelimit.allow(f"nl:ip:{_client_ip(request)}", 10, 3600):
        raise HTTPException(429, "Too many signups from this address — try again later.")

    lang = body.lang if body.lang in LANGS else "en"
    email = body.email.strip().lower()

    # Already a member? Just switch their preference on — never create a shadow row.
    u = db.query(User).filter(User.email == email).first()
    if u:
        u.marketing_opt_in = True
        u.newsletter_lang = lang
        db.commit()
        return {"ok": True, "status": "member"}

    sub = db.query(Subscriber).filter(Subscriber.email == email).first()
    if sub:
        sub.lang = lang
        if sub.status == "active":
            db.commit()
            return {"ok": True, "status": "updated"}
        # pending or previously unsubscribed — re-confirm rather than silently
        # reactivating an address whose owner may never have agreed.
        sub.status = "pending"
        db.commit()
        mail.send_newsletter_confirm(email, f"{tank.api_base_url()}/api/newsletter/confirm?token={sub.token}")
        return {"ok": True, "status": "pending"}

    # Confirmed opt-in: land as "pending" and prove the address before we ever
    # send to it. Single opt-in let anyone subscribe an address they don't own,
    # and the spam complaints from that fall on the one Resend account every
    # tank's transactional mail depends on. The digest only ever selects
    # status=="active", so a pending row is inert until the link is clicked.
    token = secrets.token_urlsafe(24)
    db.add(Subscriber(email=email, lang=lang, source=(body.source or "")[:40],
                      status="pending", token=token))
    db.commit()
    mail.send_newsletter_confirm(email, f"{tank.api_base_url()}/api/newsletter/confirm?token={token}")
    return {"ok": True, "status": "pending"}


@router.get("/confirm")
def confirm(token: str = Query(...), db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse
    sub = db.query(Subscriber).filter(Subscriber.token == token).first()
    if sub and sub.status != "unsubscribed":
        sub.status = "active"
        db.commit()
        msg = "<h2>You're subscribed</h2><p style='color:#666'>You'll get the weekly newsletter from now on.</p>"
    elif sub:
        msg = "<h2>You're subscribed</h2><p style='color:#666'>Welcome back — you'll get the weekly newsletter again.</p>"
        sub.status = "active"; db.commit()
    else:
        msg = "<h2>Link not recognised</h2><p style='color:#666'>That confirmation link isn't valid. Try subscribing again.</p>"
    return HTMLResponse(
        f"<div style='font-family:system-ui;max-width:520px;margin:80px auto;text-align:center'>{msg}</div>")


@router.get("/unsubscribe")
def unsubscribe(token: str = Query(...), db: Session = Depends(get_db)):
    sub = db.query(Subscriber).filter(Subscriber.token == token).first()
    if sub:
        sub.status = "unsubscribed"
        db.commit()
    from fastapi.responses import HTMLResponse
    return HTMLResponse(
        "<div style='font-family:system-ui;max-width:520px;margin:80px auto;text-align:center'>"
        "<h2>You're unsubscribed</h2><p style='color:#666'>You won't receive the weekly "
        "newsletter again. You can re-subscribe any time.</p></div>")


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """Public count — social proof on the signup form."""
    subs = db.query(Subscriber).filter(Subscriber.status == "active").count()
    members = db.query(User).filter(User.marketing_opt_in == True,  # noqa: E712
                                    User.account_status == "active").count()
    return {"subscribers": subs + members}
