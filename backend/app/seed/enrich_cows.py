"""Load deep-research foundation-cow profiles (bios, photos, corrected data)
into the DB. Replaces existing foundation COWS with the enriched set; leaves
foundation bulls untouched.

Run:  python -m app.seed.enrich_cows   (after foundation_cows_enriched.json exists)
"""
import json
from pathlib import Path

from .enrich_bulls import _ensure_columns  # reuse the column-ensure helper
from ..db import Base, SessionLocal, engine
from ..models import Animal, AnimalSource, AnimalType

from .. import tank
DATA = tank.seed_path_strict("foundation_cows_enriched.json")  # strict: clones never enrich from Wagyu data


def _tagline(c: dict) -> str:
    parts = []
    if c.get("bloodline"):
        parts.append(c["bloodline"])
    if c.get("import_year"):
        parts.append(f"exported {c['import_year']}")
    if c.get("importer"):
        imp = c["importer"].split("(")[0].split("/")[0].strip()
        if imp:
            parts.append(imp)
    return " · ".join(parts[:3])


def main():
    if DATA is None or not DATA.exists():
        print(f"No {DATA.name} yet — run the cow research first.")
        return
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    db = SessionLocal()
    try:
        rows = json.loads(DATA.read_text())
        removed = (
            db.query(Animal)
            .filter(Animal.is_foundation == True, Animal.animal_type == AnimalType.COW)  # noqa: E712
            .delete(synchronize_session=False)
        )
        db.commit()
        added = 0
        for c in rows:
            photos = c.get("photo_urls") or []
            db.add(Animal(
                registration_no=c.get("registration_no"),
                name=c["name"], aliases=c.get("aliases", []),
                animal_type=AnimalType.COW, breed=c.get("breed"),
                bloodline=c.get("bloodline"), bloodline_detail=c.get("bloodline_detail") or None,
                birth_year=c.get("birth_year"),
                sire_name=c.get("sire") or None, dam_name=c.get("dam") or None,
                registry="AWA" if (c.get("registration_no") or "").startswith("FB") else None,
                importer=c.get("importer") or None, import_year=c.get("import_year"),
                prefecture=c.get("prefecture") or None, is_foundation=True,
                notable=_tagline(c) or None, bio=c.get("bio") or None,
                marbling_note=c.get("marbling_note") or (c.get("notable_offspring") or None),
                photo_url=photos[0] if photos else None, photo_note=c.get("photo_note") or None,
                source=AnimalSource.FOUNDATION, confidence=c.get("confidence"),
            ))
            added += 1
        db.commit()
        print(f"Removed {removed} old cows, inserted {added} enriched cows.")
        print(f"Foundation animals now: {db.query(Animal).filter(Animal.is_foundation == True).count()}")  # noqa: E712
    finally:
        db.close()


if __name__ == "__main__":
    main()
