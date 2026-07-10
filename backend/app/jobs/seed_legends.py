"""Turn every Great Sires encyclopedia entry into a real Animal record, so each
one gets a full standalone profile page (bio, price analytics, Zenkyo badge,
member + Theater videos, and the translated-comment discussion) — the same
complex the exported foundation animals already have.

Exported animals already in the registry are left as-is (they have pages). The
in-Japan legends (Yasufuku J930, Dai 7 Itozakura, Tajiri, Kedaka, …) are created
as is_legend=True animals, addressable by their reg or a name slug. Idempotent.

  python -m app.jobs.seed_legends
"""
import json
import re
from pathlib import Path

from ..db import Base, SessionLocal, engine
from ..models import Animal, AnimalSource, AnimalType

DATA = Path(__file__).resolve().parent.parent / "seed" / "data" / "great_sires.json"


def _clean_reg(reg):
    if not reg:
        return None
    r = re.sub(r"^(AAA|AWA|PEDFA)\s+", "", str(reg).strip(), flags=re.I).strip()
    # Placeholder text like "Kagoshima registry" / "Miyazaki registry" → no reg
    if " " in r or "registry" in r.lower() or not re.search(r"[A-Za-z0-9]", r):
        return None
    return r[:40]


def _birth_year(era):
    m = re.search(r"\b(18|19|20)\d{2}\b", era or "")
    return int(m.group(0)) if m else None


def _breed(line):
    return "Akaushi (Japanese Red)" if "akaushi" in (line or "").lower() else "Fullblood Black"


def main():
    Base.metadata.create_all(bind=engine)
    data = json.loads(DATA.read_text())
    db = SessionLocal()
    try:
        created = linked = 0
        for group, atype in (("sires", AnimalType.BULL), ("dams", AnimalType.COW)):
            for e in data.get(group, []):
                reg = _clean_reg(e.get("reg"))
                name = (e.get("name") or "").split("(")[0].strip()
                if not name:
                    continue
                # Already a registry animal (by our own reg or exact name)? Leave it.
                existing = None
                if reg:
                    existing = db.query(Animal).filter(Animal.registration_no == reg).first()
                if not existing and e.get("registry_reg"):
                    existing = db.query(Animal).filter(Animal.registration_no == e["registry_reg"]).first()
                if not existing:
                    existing = db.query(Animal).filter(Animal.name.ilike(name)).first()
                if existing:
                    # Backfill a bio if the registry entry lacks one; mark legend.
                    if not existing.bio and e.get("bio"):
                        existing.bio = e["bio"]
                    if not existing.notable and e.get("epithet"):
                        existing.notable = e["epithet"]
                    linked += 1
                    continue
                # Create the legend animal.
                aliases = [e["name_jp"]] if e.get("name_jp") else []
                db.add(Animal(
                    registration_no=reg, name=name, aliases=aliases,
                    animal_type=atype, breed=_breed(e.get("line")),
                    bloodline=e.get("line"), prefecture=e.get("prefecture"),
                    birth_year=_birth_year(e.get("era")),
                    is_legend=True, is_foundation=False,
                    notable=e.get("epithet"), bio=e.get("bio"),
                    marbling_note="; ".join(e.get("key_facts", []))[:900] or None,
                    source=AnimalSource.FOUNDATION, confidence="medium",
                ))
                created += 1
        db.commit()
        legends = db.query(Animal).filter(Animal.is_legend == True).count()  # noqa: E712
        print(f"Legends: +{created} created, {linked} already had registry pages. "
              f"Total legend animals: {legends}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
