"""Seed the curated foundation-sire reference prices (idempotent replace).

  python -m app.jobs.seed_reference_prices
"""
import json
from pathlib import Path

from ..db import Base, SessionLocal, engine
from ..models import FoundationReferencePrice

def _data_path():
    """Per-tank content, strictly: tanks/<key>/seed/foundation_reference_prices.json — the Wagyu file is
    only a fallback for the wagyu tank itself. A clone without its own file
    seeds NOTHING here (never another breed's data)."""
    from .. import tank
    return tank.seed_path_strict("foundation_reference_prices.json")


def main():
    _dp = _data_path()
    if _dp is None:
        from .. import tank
        print(f"No foundation_reference_prices.json for tank '{tank.key()}' — skipping (per-tank content).")
        return
    Base.metadata.create_all(bind=engine)
    rows = json.loads(_dp.read_text())
    db = SessionLocal()
    try:
        db.query(FoundationReferencePrice).delete()
        for r in rows:
            db.add(FoundationReferencePrice(
                registration_no=r.get("registration_no"),
                sire=r["sire"],
                semen_usd=r.get("semen_usd"),
                semen_low=r.get("semen_low"),
                semen_high=r.get("semen_high"),
                embryo_usd=r.get("embryo_usd"),
                as_of_year=r.get("as_of_year"),
                availability=r.get("availability"),
                confidence=r.get("confidence", "low"),
                source_name=r.get("source_name"),
                notes=r.get("notes"),
            ))
        db.commit()
        print(f"Seeded {len(rows)} foundation reference prices.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
