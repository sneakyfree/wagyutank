"""Load the upcoming Wagyu sales calendar. Re-runnable (upsert by name+date).

  python -m app.jobs.seed_upcoming_sales
"""
import hashlib
import json
import re
from pathlib import Path

from .. import models  # noqa: F401
from ..db import Base, SessionLocal, engine
from ..models import UpcomingSale

DATA = Path(__file__).parent.parent / "seed" / "data" / "upcoming_sales.json"
CONTINENT = {"australia": "OC", "new zealand": "OC", "usa": "NA", "canada": "NA",
             "uk": "EU", "germany": "EU", "france": "EU", "brazil": "SA", "japan": "AS"}


def _sort_date(d: str | None) -> str | None:
    if not d:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d)
    if m:
        return m.group(0)
    m = re.match(r"(\d{4})-(\d{2})", d)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    m = re.match(r"(\d{4})", d)
    return f"{m.group(1)}-01-01" if m else None


def main():
    Base.metadata.create_all(bind=engine)
    rows = json.loads(DATA.read_text())
    db = SessionLocal()
    added = updated = 0
    try:
        for r in rows:
            key = hashlib.sha1(f"{r['sale_name']}|{r.get('date')}".encode()).hexdigest()[:24]
            fields = dict(sale_name=r["sale_name"], date=r.get("date"), sort_date=_sort_date(r.get("date")),
                          country=r.get("country"), continent=CONTINENT.get((r.get("country") or "").lower()),
                          venue=r.get("venue"), host=r.get("host"), url=r.get("url"), notes=r.get("notes"))
            existing = db.query(UpcomingSale).filter(UpcomingSale.dedup_key == key).first()
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(UpcomingSale(dedup_key=key, **fields)); added += 1
        db.commit()
        print(f"Upcoming sales: +{added}, {updated} updated, {db.query(UpcomingSale).count()} total.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
