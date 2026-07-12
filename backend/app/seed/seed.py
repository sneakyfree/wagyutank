"""Seed the database with the pre-loaded foundation registry and facility directory.

Run:  python -m app.seed.seed
Idempotent — safe to run repeatedly.
"""
import json
from pathlib import Path

from ..db import Base, SessionLocal, engine
from ..models import Animal, AnimalSource, AnimalType, Facility

DATA = Path(__file__).parent / "data"


def _animal_type(v: str) -> AnimalType:
    try:
        return AnimalType(v)
    except ValueError:
        return AnimalType.BULL


def seed_facilities(db) -> int:
    from .. import tank
    rows = json.loads(tank.seed_path("facilities.json").read_text())
    added = 0
    for r in rows:
        exists = db.query(Facility).filter(Facility.name == r["name"]).first()
        if exists:
            continue
        db.add(Facility(
            name=r["name"], city=r["city"], state=r.get("state", ""),
            country=r.get("country", "US"), lat=r.get("lat"), lng=r.get("lng"),
            services=r.get("services", []), export_qualified=r.get("export_qualified", False),
            website=r.get("website", ""), notes=r.get("notes", ""),
        ))
        added += 1
    db.commit()
    return added


def seed_foundation_animals(db) -> int:
    rows = json.loads(tank.seed_path("foundation_animals.json").read_text())
    added = 0
    for r in rows:
        reg = r.get("registration_no")
        # De-dupe by registration_no when present, else by name.
        q = db.query(Animal)
        exists = (
            q.filter(Animal.registration_no == reg).first()
            if reg else q.filter(Animal.name == r["name"], Animal.is_foundation == True).first()  # noqa: E712
        )
        if exists:
            continue
        db.add(Animal(
            registration_no=reg, name=r["name"], aliases=r.get("aliases", []),
            animal_type=_animal_type(r.get("animal_type", "bull")),
            breed=r.get("breed"), bloodline=r.get("bloodline"),
            bloodline_detail=r.get("bloodline_detail") or None,
            birth_year=r.get("birth_year"), importer=r.get("importer") or None,
            import_year=r.get("import_year"), is_foundation=True,
            notable=r.get("notable"), au_progeny=r.get("au_progeny"),
            source=AnimalSource.FOUNDATION, confidence=r.get("confidence"),
        ))
        added += 1
    db.commit()
    return added


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        f = seed_facilities(db)
        a = seed_foundation_animals(db)
        print(f"Seeded {f} facilities and {a} foundation animals.")
        print(f"Totals — facilities: {db.query(Facility).count()}, animals: {db.query(Animal).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
