"""First-party analytics ingest — the frontend posts page views + key actions.

Deliberately lightweight and unauthenticated (associates a user when a token is
present). No third-party trackers, no cookies beyond a random session id."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Event
from ..security import get_optional_user

router = APIRouter(prefix="/api/events", tags=["events"])

# only accept a known vocabulary — keeps the table clean
ALLOWED = {"page_view", "listing_view", "animal_view", "search", "roundup_click",
           "ad_click", "sell_start", "signup", "checkout_start"}


class EventIn(BaseModel):
    type: str
    path: str | None = None
    referrer: str | None = None
    session_id: str | None = None
    meta: dict | None = None


@router.post("")
def ingest(e: EventIn, user=Depends(get_optional_user), db: Session = Depends(get_db)):
    if e.type not in ALLOWED:
        return {"ok": False}
    db.add(Event(
        type=e.type, user_id=(user.id if user else None),
        session_id=(e.session_id or "")[:40] or None,
        path=(e.path or "")[:300] or None,
        referrer=(e.referrer or "")[:300] or None,
        meta=e.meta if isinstance(e.meta, dict) else None,
    ))
    db.commit()
    return {"ok": True}
