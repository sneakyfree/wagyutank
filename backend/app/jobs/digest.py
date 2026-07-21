"""Send the weekly Wagyu Wire digest to opted-in users.

  python -m app.jobs.digest          # send for real
  python -m app.jobs.digest --test EMAIL   # send one preview
"""
import sys

from .. import models  # noqa: F401
from ..config import settings
from ..db import Base, SessionLocal, engine
from ..models import Campaign, Subscriber, User
from ..security import create_unsubscribe_token
from ..services import digest, email as mail, settings_store

def _subject(db=None, lang: str = "en") -> str:
    """The masthead. Kept in English even on translated editions — it is the
    publication's name, and a consistent subject line is what makes the archive
    searchable years later."""
    from .. import tank
    breed = (tank.brand().get("breed") or "Wagyu").split(" & ")[0].strip()
    return f"The State of the {breed} Weekly — {tank.brand().get('name', 'WagyuTank')}"


def _archive_recipients() -> list[str]:
    """Addresses that receive every edition regardless of subscriber list — the
    permanent archive mailbox. Comma-separated admin setting."""
    raw = settings_store.get("digest_archive_recipients", "") or ""
    return [e.strip() for e in raw.split(",") if e.strip()]


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
        subs = db.query(Subscriber).filter(Subscriber.status == "active").all()

        # One body per language, built once and reused — translation is cached,
        # so a six-language send is six short LLM calls, not six hundred.
        def _unsub_sub(t: str) -> str:
            from .. import tank
            return f"{tank.api_base_url()}/api/newsletter/unsubscribe?token={t}"

        recipients: list[tuple[str, str, str]] = []   # (email, lang, unsubscribe)
        for u in users:
            recipients.append((u.email, (u.newsletter_lang or "en"), _unsub(u.id)))
        for sb in subs:
            recipients.append((sb.email, sb.lang or "en", _unsub_sub(sb.token)))

        bodies = {"en": body}
        for _, lg, _u in recipients:
            if lg not in bodies:
                bodies[lg] = digest.build_body(db, lg)

        messages = [{"to": em, "subject": _subject(),
                     "html": mail.campaign_html(bodies.get(lg, body), un),
                     "unsubscribe_url": un} for em, lg, un in recipients]

        # Archive copies — every edition lands in the office mailbox forever.
        for arch in _archive_recipients():
            messages.append({"to": arch, "subject": _subject(),
                             "html": mail.campaign_html(body, _unsub(0)),
                             "unsubscribe_url": _unsub(0)})

        camp = Campaign(subject=_subject(), body_html=body, segment="all",
                        recipients=len(messages), status="sending")
        db.add(camp); db.commit()
        from datetime import datetime, timezone
        from ..services import health
        t0 = datetime.now(timezone.utc).replace(tzinfo=None)
        sent = mail.send_bulk(messages)
        camp.sent = sent; camp.status = "sent"; db.commit()
        health.record_job(db, "digest", started=t0, ok=True, added=sent,
                          detail={"recipients": len(messages),
                                  "members": len(users), "subscribers": len(subs),
                                  "languages": sorted(bodies)})
        print(f"State of the Wagyu Weekly: sent {sent}/{len(messages)} "
              f"({len(users)} members, {len(subs)} subscribers, "
              f"langs {sorted(bodies)}, campaign {camp.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
