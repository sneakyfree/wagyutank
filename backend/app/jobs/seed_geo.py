"""Load the offline postal-code gazetteer (GeoNames, CC-BY 4.0) into geo_postal.

Powers the zero-cloud-cost "near me" radius search on live-cattle/beef tanks —
no geocoding API, no per-lookup cost. Breed-agnostic, so it lives in
app/seed/data/ and every tank that needs geo runs this once (hatchery seed phase
calls it when a tank has a live/beef product). Idempotent: skips if already
loaded; --refresh reloads.

Dataset: app/seed/data/geonames_postal.tsv.gz — columns (tab):
  country  postal  place  admin1_code  admin1_name  lat  lng
Coverage: US + CA + AU (~46k postal centroids). Attribution required in the
site footer/about ("Postal data © GeoNames, CC BY 4.0").

  python -m app.jobs.seed_geo [--refresh]
"""
import gzip
import sys
from pathlib import Path

from ..db import SessionLocal, engine
from ..models import Base, GeoPostal

DATA = Path(__file__).resolve().parent.parent / "seed" / "data" / "geonames_postal.tsv.gz"
_BATCH = 5000


def main(refresh: bool = False) -> int:
    Base.metadata.create_all(bind=engine)  # ensure geo_postal exists (fresh tank)
    if not DATA.exists():
        print(f"gazetteer not found: {DATA} — skipping geo seed.")
        return 0
    db = SessionLocal()
    try:
        have = db.query(GeoPostal).count()
        if have and not refresh:
            print(f"geo_postal already loaded ({have} rows) — skipping (use --refresh to reload).")
            return have
        if refresh and have:
            db.query(GeoPostal).delete()
            db.commit()
            print(f"cleared {have} existing rows (--refresh).")

        seen: set[tuple[str, str]] = set()
        batch: list[GeoPostal] = []
        added = 0
        with gzip.open(DATA, "rt", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 7:
                    continue
                country, postal, place, a1c, a1n, lat, lng = parts[:7]
                key = (country, postal)
                if not postal or not lat or not lng or key in seen:
                    continue
                seen.add(key)
                try:
                    latf, lngf = float(lat), float(lng)
                except ValueError:
                    continue
                batch.append(GeoPostal(
                    country=country[:2], postal=postal[:16], place_name=(place or None),
                    admin1_code=(a1c or None), admin1_name=(a1n or None), lat=latf, lng=lngf))
                if len(batch) >= _BATCH:
                    db.bulk_save_objects(batch)
                    db.commit()
                    added += len(batch)
                    batch = []
        if batch:
            db.bulk_save_objects(batch)
            db.commit()
            added += len(batch)
        print(f"geo_postal loaded: {added} postal centroids (US/CA/AU).")
        return added
    finally:
        db.close()


if __name__ == "__main__":
    main(refresh="--refresh" in sys.argv)
