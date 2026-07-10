import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..config import settings as cfg
from ..db import get_db
from ..models import PasswordReset, User
from ..schemas import Token, UserCreate, UserPrivate
from ..security import (
    create_access_token, get_current_user, hash_password,
    user_id_from_unsubscribe, verify_password,
)
from ..services import email as mail
from ..services import ratelimit


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for")
    return (fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown"))

router = APIRouter(prefix="/api/auth", tags=["auth"])

HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$")
RESERVED = {"admin", "api", "www", "wagyutank", "support", "help", "login", "signup",
            "sell", "search", "history", "michifuku", "wagyu"}


def _private(u: User) -> UserPrivate:
    data = UserPrivate.model_validate(u, from_attributes=True)
    data.is_seller = u.is_seller
    return data


@router.post("/register", response_model=Token)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(400, "An account with that email already exists.")
    handle = payload.handle.lower().strip() if payload.handle else None
    if handle:
        if handle in RESERVED or not HANDLE_RE.match(handle):
            raise HTTPException(400, "That storefront handle is unavailable.")
        if db.query(User).filter(User.handle == handle).first():
            raise HTTPException(400, "That storefront handle is taken.")
    from ..config import settings as _cfg
    from ..roles import role_for_email
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
        handle=handle,
        phone=(payload.phone or "").strip() or None,
        country=((payload.country or "").strip().upper()[:2] or None),
        recovery_email=payload.recovery_email,
        marketing_opt_in=payload.marketing_opt_in,
        role=role_for_email(payload.email, _cfg.super_admin_emails, _cfg.admin_emails),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    try:
        mail.send_welcome(user.email, user.display_name)
    except Exception:
        pass
    return Token(access_token=create_access_token(user.id), user=_private(user))


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _finish_login(user: User, db: Session) -> dict:
    user.last_login_at = _now()
    db.commit()
    return {"access_token": create_access_token(user.id), "token_type": "bearer",
            "user": _private(user).model_dump()}


@router.post("/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form uses "username"; we accept the email there.
    if not ratelimit.allow(f"login:ip:{_client_ip(request)}", 20, 300):
        raise HTTPException(429, "Too many attempts. Please wait a minute and try again.")
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password.")
    if user.account_status == "suspended":
        raise HTTPException(403, "This account is suspended. Contact support@wagyutank.com.")
    if user.account_status == "deleted":
        raise HTTPException(401, "Incorrect email or password.")
    if user.totp_enabled:
        from ..security import create_preauth_token
        return {"twofa_required": True, "challenge": create_preauth_token(user.id)}
    return _finish_login(user, db)


@router.post("/2fa/verify")
def twofa_verify(challenge: str = Body(...), code: str = Body(...), db: Session = Depends(get_db)):
    import pyotp
    from ..security import user_id_from_preauth
    uid = user_id_from_preauth(challenge)
    user = db.get(User, uid) if uid else None
    if not user or not user.totp_secret:
        raise HTTPException(401, "Challenge expired — please sign in again.")
    if not pyotp.TOTP(user.totp_secret).verify(code.strip(), valid_window=1):
        raise HTTPException(401, "Invalid authentication code.")
    return _finish_login(user, db)


@router.get("/me", response_model=UserPrivate)
def me(user: User = Depends(get_current_user)):
    return _private(user)


# ------------------------------------------------------------------ 2FA setup
@router.post("/2fa/setup")
def twofa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Generate (or reuse) a TOTP secret and return a QR to scan. Not active until enabled."""
    import pyotp
    import segno
    if not user.totp_secret or user.totp_enabled:
        if not user.totp_enabled:
            user.totp_secret = pyotp.random_base32()
            db.commit()
    uri = pyotp.totp.TOTP(user.totp_secret).provisioning_uri(name=user.email, issuer_name="WagyuTank")
    import io
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=4, dark="#1a1a1a", light="#ffffff")
    svg = buf.getvalue().decode()
    import base64
    data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    return {"secret": user.totp_secret, "otpauth_uri": uri, "qr_svg": data_uri,
            "enabled": user.totp_enabled}


@router.post("/2fa/enable")
def twofa_enable(code: str = Body(..., embed=True), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    import pyotp
    if not user.totp_secret:
        raise HTTPException(400, "Start 2FA setup first.")
    if not pyotp.TOTP(user.totp_secret).verify(code.strip(), valid_window=1):
        raise HTTPException(400, "That code didn't match — try again.")
    user.totp_enabled = True
    db.commit()
    return {"enabled": True}


@router.post("/2fa/disable")
def twofa_disable(code: str = Body(..., embed=True), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    import pyotp
    if user.totp_enabled and not (user.totp_secret and pyotp.TOTP(user.totp_secret).verify(code.strip(), valid_window=1)):
        raise HTTPException(400, "Enter a current code to disable 2FA.")
    user.totp_enabled = False
    user.totp_secret = None
    db.commit()
    return {"enabled": False}


# ------------------------------------------------------------ Password reset
def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


@router.post("/forgot-password")
def forgot_password(request: Request, email: str = Body(..., embed=True), db: Session = Depends(get_db)):
    """Always 200 — never reveal whether an account exists. Rate-limited."""
    generic = {"message": "If an account exists for that email, we've sent a reset link."}
    ip = _client_ip(request)
    em = email.strip().lower()
    if not ratelimit.allow(f"forgot:ip:{ip}", 5, 3600) or not ratelimit.allow(f"forgot:em:{em}", 3, 3600):
        raise HTTPException(429, "Too many reset requests. Please wait a bit and try again.")
    user = db.query(User).filter(User.email == em).first()
    if not user or user.account_status == "deleted":
        return generic
    raw = secrets.token_urlsafe(32)
    db.add(PasswordReset(user_id=user.id, token_hash=_hash_token(raw),
                         expires_at=_now() + timedelta(minutes=45)))
    db.commit()
    reset_url = f"{cfg.app_base_url}/reset-password?token={raw}"
    if mail.enabled():
        mail.send_password_reset(user.email, reset_url)
        return generic
    # Dev fallback (no mail configured): surface the URL so resets are testable.
    return {**generic, "dev_reset_url": reset_url}


@router.post("/reset-password")
def reset_password(token: str = Body(...), new_password: str = Body(..., min_length=8),
                   db: Session = Depends(get_db)):
    row = db.query(PasswordReset).filter(PasswordReset.token_hash == _hash_token(token)).first()
    if not row or row.used or row.expires_at < _now():
        raise HTTPException(400, "This reset link is invalid or has expired.")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(400, "Account not found.")
    user.hashed_password = hash_password(new_password)
    row.used = True
    db.commit()
    return {"ok": True, "message": "Password updated — you can sign in now."}


@router.get("/unsubscribe", response_class=HTMLResponse)
def unsubscribe(token: str, db: Session = Depends(get_db)):
    """One-click marketing unsubscribe (from the List-Unsubscribe link in emails)."""
    uid = user_id_from_unsubscribe(token)
    user = db.get(User, uid) if uid else None
    if user:
        user.marketing_opt_in = False
        db.commit()
    msg = ("You've been unsubscribed from WagyuTank marketing emails."
           if user else "This unsubscribe link is invalid.")
    return HTMLResponse(
        f"<div style='font-family:sans-serif;max-width:480px;margin:60px auto;text-align:center'>"
        f"<h2 style='color:#8a6d2b'>WagyuTank</h2><p>{msg}</p>"
        f"<p style='color:#888;font-size:13px'>You'll still receive essential account emails "
        f"(like password resets).</p></div>")
