"""Send the weekly Wagyu Wire digest to opted-in users.

  python -m app.jobs.digest          # send for real
  python -m app.jobs.digest --test EMAIL   # send one preview
"""
import sys

from .. import models  # noqa: F401
from ..config import settings
from ..db import Base, SessionLocal, engine
from ..models import Campaign, User
from ..security import create_unsubscribe_token
from ..services import digest, email as mail, settings_store

def _subject() -> str:
    from .. import tank
    breed = (tank.brand().get("breed") or "Wagyu").split(" & ")[0].strip()
    return f"The State of the {breed} — this week from {tank.brand().get('name', 'WagyuTank')}"


def _unsub(uid: int) -> str:
    from .. import tank
    api = tank.api_base_url()
    return f"{api}/api/auth/unsubscribe?token={create_unsubscribe_token(uid)}"


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        body = digest.build_body(db)

        if len(sys.argv) > 2 and sys.argv[1] == "--test":
            to = sys.argv[2]
            ok = mail.send(to, _subject(), mail.campaign_html(body, _unsub(0)))
            print(f"Digest test to {to}: {'sent' if ok else 'FAILED'}")
            return

        if not settings_store.get("digest_enabled", True):
            print("Digest disabled by admin — skipping.")
            return

        users = db.query(User).filter(User.account_status == "active",
                                      User.marketing_opt_in == True).all()  # noqa: E712
        camp = Campaign(subject=_subject(), body_html=body, segment="all",
                        recipients=len(users), status="sending")
        db.add(camp); db.commit()
        messages = [{"to": u.email, "subject": _subject(),
                     "html": mail.campaign_html(body, _unsub(u.id)),
                     "unsubscribe_url": _unsub(u.id)} for u in users]
        from datetime import datetime, timezone
        from ..services import health
        t0 = datetime.now(timezone.utc).replace(tzinfo=None)
        sent = mail.send_bulk(messages)
        camp.sent = sent; camp.status = "sent"; db.commit()
        health.record_job(db, "digest", started=t0, ok=True, added=sent,
                          detail={"recipients": len(users)})
        print(f"Wagyu Wire: sent to {sent}/{len(users)} recipients (campaign {camp.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
