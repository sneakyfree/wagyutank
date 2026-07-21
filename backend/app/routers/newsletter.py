"""Public newsletter signup — deliberately no account required."""
import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Subscriber, User
from ..services import ratelimit
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
        sub.status, sub.lang = "active", lang
        db.commit()
        return {"ok": True, "status": "updated"}

    db.add(Subscriber(email=email, lang=lang, source=(body.source or "")[:40],
                      status="active", token=secrets.token_urlsafe(24)))
    db.commit()
    return {"ok": True, "status": "subscribed"}


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
