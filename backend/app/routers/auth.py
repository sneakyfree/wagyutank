import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import Token, UserCreate, UserPrivate
from ..security import create_access_token, get_current_user, hash_password, verify_password

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
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        display_name=payload.display_name,
        handle=handle,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return Token(access_token=create_access_token(user.id), user=_private(user))


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # OAuth2 form uses "username"; we accept the email there.
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password.")
    return Token(access_token=create_access_token(user.id), user=_private(user))


@router.get("/me", response_model=UserPrivate)
def me(user: User = Depends(get_current_user)):
    return _private(user)
