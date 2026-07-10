"""The Zenkyo Hall of Champions — Japan's 'Wagyu Olympics' (全国和牛能力共進会),
every 5 years since 1966. Serves the event timeline + champion-bull records
(seeded from researched, sourced data) and captures interest for the WagyuTank
Delegation to Zenkyo 2027 in Hokkaido."""
import json
from pathlib import Path

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ZenkyoInterest
from ..services import ratelimit

router = APIRouter(prefix="/api/zenkyo", tags=["zenkyo"])

DATA = Path(__file__).resolve().parent.parent / "seed" / "data" / "zenkyo.json"
_cache: dict = {}


def _load() -> dict:
    if not _cache:
        try:
            _cache.update(json.loads(DATA.read_text()))
        except Exception:
            _cache.update({"events": [], "champions": []})
    return _cache


@router.get("")
def zenkyo(db: Session = Depends(get_db)):
    d = _load()
    interested = db.query(ZenkyoInterest).count()
    return {**d, "next_event": {"number": 13, "year": 2027, "dates": "August 26–30, 2027",
                                "host_prefecture": "Hokkaido", "city": "Otofuke & Obihiro (Tokachi)",
                                "starts_at": "2027-08-26"},
            "delegation_interested": interested}


def _client_ip(request: Request) -> str:
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "?")


@router.post("/interest")
def register_interest(request: Request, email: str = Body(...), name: str | None = Body(None),
                      country: str | None = Body(None), party_size: int = Body(1),
                      note: str | None = Body(None), db: Session = Depends(get_db)):
    if not ratelimit.allow(f"zenkyo:ip:{_client_ip(request)}", 5, 3600):
        raise HTTPException(429, "Too many submissions — please try again later.")
    email = (email or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(400, "Please enter a valid email address.")
    if db.query(ZenkyoInterest).filter(ZenkyoInterest.email == email).first():
        return {"ok": True, "message": "You're already on the delegation list — we'll be in touch as plans firm up."}
    db.add(ZenkyoInterest(email=email, name=(name or "")[:160] or None,
                          country=(country or "")[:60] or None,
                          party_size=max(1, min(int(party_size or 1), 20)),
                          note=(note or "")[:400] or None))
    db.commit()
    return {"ok": True, "message": "You're on the list for the WagyuTank Delegation to Zenkyo 2027! "
                                   "We'll email you as the trip takes shape."}
