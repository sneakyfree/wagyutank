"""Seed the database with the pre-loaded foundation registry and facility directory.

Run:  python -m app.seed.seed
Idempotent — safe to run repeatedly.
"""
import json
from pathlib import Path

from .. import tank
from ..db import Base, SessionLocal, engine
from ..models import Animal, AnimalSource, AnimalType, Facility

DATA = Path(__file__).parent / "data"


def _animal_type(v: str) -> AnimalType:
    try:
        return AnimalType(v)
    except ValueError:
        return AnimalType.BULL


def seed_facilities(db) -> int:
    """Tolerant of the looser shapes breed-research agents produce:
    `location: "Adel, Iowa"` instead of city/state, `services` as a comma
    string instead of a list, `url` instead of `website`. Normalizing here
    beats hand-fixing every new breed's research output."""
    # STRICT: a clone with no facilities.json of its own must seed NOTHING here —
    # never fall back to WagyuTank's directory (that leak put 23 Wagyu facilities
    # into wagyusale.db). seed_path_strict returns None for a clone missing the file.
    src = tank.seed_path_strict("facilities.json")
    if src is None:
        return 0
    rows = json.loads(src.read_text())
    added = 0
    for r in rows:
        exists = db.query(Facility).filter(Facility.name == r["name"]).first()
        if exists:
            continue
        city, state = r.get("city"), r.get("state", "")
        if not city and r.get("location"):
            parts = [s.strip() for s in str(r["location"]).split(",")]
            city = parts[0] if parts else ""
            state = state or (parts[1] if len(parts) > 1 else "")
        services = r.get("services", [])
        if isinstance(services, str):
            services = [s.strip().lower() for s in services.split(",") if s.strip()]
        db.add(Facility(
            name=r["name"], city=city or "", state=state,
            country=r.get("country", "US"), lat=r.get("lat"), lng=r.get("lng"),
            services=services, export_qualified=r.get("export_qualified", False),
            website=r.get("website") or r.get("url", ""), notes=r.get("notes", ""),
        ))
        added += 1
    db.commit()
    return added


def seed_foundation_animals(db) -> int:
    # STRICT (same reason as seed_facilities): a clone with no foundation_animals.json
    # seeds no animals rather than inheriting WagyuTank's 57 founders.
    src = tank.seed_path_strict("foundation_animals.json")
    if src is None:
        return 0
    rows = json.loads(src.read_text())
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
