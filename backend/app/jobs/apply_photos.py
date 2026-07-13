"""Apply the curated animal-photo map (reg/slug -> local /foundation/*.jpg) to
Animal.photo_url, plus any gallery (extra) photos. These are historical,
industry-standard foundation-sire reference images, re-hosted locally for
reliability. Idempotent.

Map value forms:
  "FB103": "/foundation/FB103.jpg"                       # primary only
  "AF6808": {                                            # primary + gallery
     "primary": "/foundation/AF6808.jpg",
     "gallery": [{"src": "/foundation/AF6808-reeves.jpg", "caption": "..."}]
  }

  python -m app.jobs.apply_photos
"""
import json
from pathlib import Path

from ..db import SessionLocal
from ..models import Animal, AnimalPhoto

def _data_path():
    """Per-tank content, strictly: tanks/<key>/seed/animal_photos.json — the Wagyu file is
    only a fallback for the wagyu tank itself. A clone without its own file
    seeds NOTHING here (never another breed's data)."""
    from .. import tank
    return tank.seed_path_strict("animal_photos.json")


def _resolve(db, key: str) -> Animal | None:
    a = (db.query(Animal).filter(Animal.registration_no == key).first()
         or db.query(Animal).filter(Animal.name.ilike(key.replace("-", " "))).first())
    if a:
        return a
    for cand in db.query(Animal).filter(
            (Animal.is_foundation == True) | (Animal.is_legend == True)).all():  # noqa: E712
        if cand.slug == key:
            return cand
    return None


def _apply_one(db, a: Animal, val) -> int:
    """Set the primary photo and reconcile gallery rows. Returns #changes."""
    if isinstance(val, str):
        primary, gallery = val, []
    else:
        primary = val.get("primary")
        gallery = val.get("gallery", []) or []

    changed = 0
    if primary and a.photo_url != primary:
        a.photo_url = primary
        changed += 1

    # Reconcile our curated gallery: index the approved /foundation/ extras we
    # previously added, diff against the desired set, add/update/remove.
    existing = {p.url: p for p in a.photos
                if p.status == "approved" and (p.url or "").startswith("/foundation/")}
    want: dict[str, str | None] = {}
    for g in gallery:
        if isinstance(g, str):
            src, cap = g, None
        else:
            src, cap = g.get("src"), g.get("caption")
        if src:
            want[src] = cap

    for url, cap in want.items():
        if url in existing:
            if existing[url].attribution != cap:
                existing[url].attribution = cap
                changed += 1
        else:
            db.add(AnimalPhoto(animal_id=a.id, url=url, attribution=cap, status="approved"))
            changed += 1
    for url, p in existing.items():
        if url not in want:
            db.delete(p)
            changed += 1
    return changed


def main():
    _dp = _data_path()
    if _dp is None:
        from .. import tank
        print(f"No animal_photos.json for tank '{tank.key()}' — skipping (per-tank content).")
        return
    m = json.loads(_dp.read_text())
    db = SessionLocal()
    try:
        applied = 0
        for key, val in m.items():
            a = _resolve(db, key)
            if a:
                applied += _apply_one(db, a, val)
        db.commit()
        print(f"Applied {applied} foundation photo changes (primaries + gallery).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
