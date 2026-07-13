from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import tank
from .config import settings
from .db import get_db
from .models import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    # bcrypt caps at 72 bytes
    return pwd_context.hash(password[:72])


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain[:72], hashed)


def create_access_token(user_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_preauth_token(user_id: int) -> str:
    """Short-lived token issued after password success when 2FA is pending."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=5)
    payload = {"sub": str(user_id), "scope": "2fa", "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def user_id_from_preauth(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("scope") != "2fa":
            return None
        return int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None


def create_unsubscribe_token(user_id: int) -> str:
    """Non-expiring signed token for one-click email unsubscribe."""
    return jwt.encode({"sub": str(user_id), "scope": "unsub"}, settings.jwt_secret,
                      algorithm=settings.jwt_algorithm)


def create_email_verify_token(user_id: int) -> str:
    """7-day signed token emailed to a user to confirm they control their address.
    Verification gates domain-based features (e.g. claiming Roundup listings)."""
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    return jwt.encode({"sub": str(user_id), "scope": "verify_email", "exp": expire},
                      settings.jwt_secret, algorithm=settings.jwt_algorithm)


def user_id_from_email_verify(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("scope") != "verify_email":
            return None
        return int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None


def create_takedown_token(source_site: str, email: str) -> str:
    """7-day signed token emailed to a domain-verified requester. Confirming the
    link takes down all Roundup listings from `source_site`."""
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    return jwt.encode({"site": source_site, "email": email, "scope": "roundup_takedown",
                       "exp": expire}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def takedown_from_token(token: str) -> dict | None:
    """Return {'site', 'email'} for a valid takedown token, else None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("scope") != "roundup_takedown":
            return None
        return {"site": payload.get("site"), "email": payload.get("email")}
    except (JWTError, TypeError, ValueError):
        return None


def create_sso_token(email: str, display_name: str, email_verified: bool, aud: str) -> str:
    """Cross-site handoff token for the sister-tank trust circle (wagyutank ↔
    wagyusale). Signed with the SHARED SSO secret — never this tank's own
    jwt_secret — so a compromise of one tank's session secret can't forge
    logins on the other. 90-second lifetime; single-use via the jti recorded
    in SsoRedemption at redeem time."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "name": display_name,
        "ev": bool(email_verified),
        "jti": uuid4().hex,
        "aud": aud,                                   # the PEER tank's domain
        "iss": tank.brand().get("domain", ""),        # this tank's domain
        "iat": now,
        "exp": now + timedelta(seconds=90),
        "scope": "sso",
    }
    return jwt.encode(payload, settings.sso_shared_secret, algorithm=settings.jwt_algorithm)


def verify_sso_token(token: str, expected_aud: str) -> dict | None:
    """Decode a sister-tank SSO token. Returns the claims dict, or None if the
    signature, expiry, audience (must equal THIS tank's domain) or scope fails.
    Replay protection (jti) is the caller's job — this only proves authenticity."""
    if not settings.sso_shared_secret or not expected_aud:
        return None
    try:
        payload = jwt.decode(token, settings.sso_shared_secret,
                             algorithms=[settings.jwt_algorithm], audience=expected_aud)
        if payload.get("scope") != "sso":
            return None
        return payload
    except JWTError:
        return None


def user_id_from_unsubscribe(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("scope") != "unsub":
            return None
        return int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None


def _user_from_token(token: str | None, db: Session) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        return None
    return db.get(User, user_id)


def get_current_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    user = _user_from_token(token, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_optional_user(
    token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User | None:
    return _user_from_token(token, db)


def _enforce_2fa(user: User) -> None:
    """When an admin has enforced platform-wide 2FA, staff without it are locked out."""
    try:
        from .services import settings_store
        if settings_store.get("require_admin_2fa", False) and not user.totp_enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Admin 2FA is required. Enable it under Dashboard → Security.")
    except HTTPException:
        raise
    except Exception:
        pass


def _require_rank(user: User, min_rank: int, label: str) -> User:
    from .roles import rank
    if user.account_status != "active" or rank(user.role) < min_rank:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"{label} access required.")
    _enforce_2fa(user)
    return user


def require_staff(user: User = Depends(get_current_user)) -> User:
    """Manager and up — panel visibility (analytics, members, moderation)."""
    return _require_rank(user, 1, "Staff")


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Admin and up — member/settings/campaign control. Super admins pass too."""
    return _require_rank(user, 2, "Admin")


def require_super_admin(user: User = Depends(get_current_user)) -> User:
    """Super admin only — assigning/removing admins."""
    return _require_rank(user, 3, "Super-admin")
