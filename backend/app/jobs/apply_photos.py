"""Apply the curated animal-photo map (reg/slug -> local /foundation/*.jpg) to
Animal.photo_url. These are historical, industry-standard foundation-sire
reference images, re-hosted locally for reliability and consistent direction
(all bulls face right). Idempotent.

  python -m app.jobs.apply_photos
"""
import json
from pathlib import Path

from ..db import SessionLocal
from ..models import Animal

MAP = Path(__file__).resolve().parent.parent / "seed" / "data" / "animal_photos.json"


def main():
    m = json.loads(MAP.read_text())
    db = SessionLocal()
    try:
        applied = 0
        for key, path in m.items():
            a = (db.query(Animal).filter(Animal.registration_no == key).first()
                 or db.query(Animal).filter(Animal.name.ilike(key.replace("-", " "))).first())
            if not a:
                # slug fallback across foundation/legend animals
                for cand in db.query(Animal).filter(
                        (Animal.is_foundation == True) | (Animal.is_legend == True)).all():  # noqa: E712
                    if cand.slug == key:
                        a = cand
                        break
            if a and a.photo_url != path:
                a.photo_url = path
                applied += 1
        db.commit()
        print(f"Applied {applied} foundation photos.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
