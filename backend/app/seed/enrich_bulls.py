"""Load the deep-research foundation-bull profiles (bios, photos, corrected
bloodlines) into the DB. Replaces existing foundation BULLS with the enriched
set (preserving registration numbers so listings still resolve); leaves
foundation cows untouched.

Run:  python -m app.seed.enrich_bulls
"""
import json
from pathlib import Path

from ..db import Base, SessionLocal, engine
from ..models import Animal, AnimalSource, AnimalType

from .. import tank
DATA = tank.seed_path_strict("foundation_bulls_enriched.json")  # strict: clones never enrich from Wagyu data

# Columns added after the initial schema — ensure they exist (SQLite ALTER ADD).
_NEW_COLUMNS = {
    "prefecture": "VARCHAR(60)",
    "bio": "TEXT",
    "marbling_note": "TEXT",
    "photo_note": "VARCHAR(300)",
    "bred_outside_japan": "BOOLEAN DEFAULT 0",
    "birth_country": "VARCHAR(2)",
    "conceived_in_japan": "BOOLEAN DEFAULT 0",
    "semen_only": "BOOLEAN DEFAULT 0",
    "blend": "JSON",
    "blend_group": "VARCHAR(2)",
    "blend_total": "FLOAT",
    "blend_source": "VARCHAR(120)",
}


def _ensure_columns():
    with engine.begin() as conn:
        existing = {r[1] for r in conn.exec_driver_sql("PRAGMA table_info(animals)")}
        for col, coltype in _NEW_COLUMNS.items():
            if col not in existing:
                conn.exec_driver_sql(f"ALTER TABLE animals ADD COLUMN {col} {coltype}")
                print(f"  added column animals.{col}")


def _tagline(b: dict) -> str:
    parts = []
    if b.get("bloodline"):
        parts.append(b["bloodline"])
    if b.get("import_year"):
        parts.append(f"exported {b['import_year']}")
    if b.get("au_progeny"):
        parts.append(f"{b['au_progeny']:,} AU progeny")
    return " · ".join(parts)


def main():
    Base.metadata.create_all(bind=engine)
    _ensure_columns()
    db = SessionLocal()
    try:
        if DATA is None:
            print(f"No foundation_bulls_enriched.json for tank '{{}}' — skipping.".format(tank.key()))
            return
        rows = json.loads(DATA.read_text())
        # Remove existing foundation bulls (cows stay).
        removed = (
            db.query(Animal)
            .filter(Animal.is_foundation == True, Animal.animal_type == AnimalType.BULL)  # noqa: E712
            .delete(synchronize_session=False)
        )
        db.commit()

        added = 0
        for b in rows:
            photos = b.get("photo_urls") or []
            db.add(Animal(
                registration_no=b.get("registration_no"),
                name=b["name"],
                aliases=b.get("aliases", []),
                animal_type=AnimalType.BULL,
                breed=b.get("breed"),
                bloodline=b.get("bloodline"),
                bloodline_detail=b.get("bloodline_detail") or None,
                birth_year=b.get("birth_year"),
                sire_name=b.get("sire") or None,
                dam_name=b.get("dam") or None,
                registry="AWA" if (b.get("registration_no") or "").startswith("FB") else None,
                importer=b.get("importer") or None,
                import_year=b.get("import_year"),
                prefecture=b.get("prefecture") or None,
                is_foundation=True,
                notable=_tagline(b) or None,
                bio=b.get("bio") or None,
                marbling_note=b.get("marbling_note") or None,
                au_progeny=b.get("au_progeny"),
                photo_url=photos[0] if photos else None,
                photo_note=b.get("photo_note") or None,
                bred_outside_japan=bool(b.get("bred_outside_japan")),
                birth_country=b.get("birth_country") or None,
                conceived_in_japan=bool(b.get("conceived_in_japan")),
                semen_only=bool(b.get("semen_only")),
                blend=b.get("blend") or None,
                blend_group=b.get("blend_group") or None,
                blend_total=b.get("blend_total"),
                blend_source=b.get("blend_source") or None,
                source=AnimalSource.FOUNDATION,
                confidence=b.get("confidence"),
            ))
            added += 1
        db.commit()
        photos_n = db.query(Animal).filter(
            Animal.is_foundation == True, Animal.photo_url != None  # noqa: E712,E711
        ).count()
        print(f"Removed {removed} old bulls, inserted {added} enriched bulls.")
        print(f"Foundation animals now: {db.query(Animal).filter(Animal.is_foundation == True).count()}"  # noqa: E712
              f" ({photos_n} with photos).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
