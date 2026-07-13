"""Load the forensic Wagyu sale-events database (chronological auction results).

  python -m app.jobs.seed_sale_events

Re-runnable — upserts by dedup_key (sale_name + year), so re-running updates
existing rows and adds new ones as we find more sales.
"""
import hashlib
import json
from pathlib import Path

from .. import models  # noqa: F401
from ..db import Base, SessionLocal, engine
from ..models import SaleEvent

def _data_path():
    """Per-tank content, strictly: tanks/<key>/seed/sale_events.json — the Wagyu file is
    only a fallback for the wagyu tank itself. A clone without its own file
    seeds NOTHING here (never another breed's data)."""
    from .. import tank
    return tank.seed_path_strict("sale_events.json")

CONTINENT = {"AU": "OC", "NZ": "OC", "US": "NA", "CA": "NA", "MX": "NA",
             "GB": "EU", "DE": "EU", "FR": "EU", "IE": "EU", "NL": "EU",
             "BR": "SA", "AR": "SA", "UY": "SA", "JP": "AS", "CN": "AS"}

# Approximate FX to USD for the normalized trend view (indicative, not live).
USD_RATE = {"USD": 1.0, "AUD": 0.66, "NZD": 0.60, "GBP": 1.27, "EUR": 1.08,
            "BRL": 0.18, "JPY": 0.0067}


def _event_type(r: dict) -> str:
    if r.get("event_type"):
        return r["event_type"]
    name = r.get("sale_name", "").lower()
    if any(w in name for w in ("matsusaka", "contest", "carcass", "beef")):
        return "beef"
    if "calf" in name:
        return "calf"
    return "genetics"


def main():
    _dp = _data_path()
    if _dp is None:
        from .. import tank
        print(f"No sale_events.json for tank '{tank.key()}' — skipping (per-tank content).")
        return
    Base.metadata.create_all(bind=engine)
    rows = json.loads(_dp.read_text())
    db = SessionLocal()
    added = updated = 0
    try:
        for r in rows:
            key = hashlib.sha1(f"{r['sale_name']}|{r.get('year')}".encode()).hexdigest()[:24]
            existing = db.query(SaleEvent).filter(SaleEvent.dedup_key == key).first()
            fields = dict(
                sale_name=r["sale_name"], date=r.get("date"), year=r.get("year"),
                country=r.get("country"), continent=CONTINENT.get(r.get("country", ""), None),
                venue=r.get("venue"), currency=r.get("currency", "AUD"),
                gross_total=r.get("gross_total"), lots_sold=r.get("lots_sold"),
                top_price=r.get("top_price"), top_price_item=r.get("top_price_item"),
                bull_avg=r.get("bull_avg"), bull_top=r.get("bull_top"),
                female_avg=r.get("female_avg"), female_top=r.get("female_top"),
                heifer_avg=r.get("heifer_avg"), heifer_top=r.get("heifer_top"),
                semen_avg=r.get("semen_avg"), semen_top=r.get("semen_top"),
                embryo_avg=r.get("embryo_avg"), embryo_top=r.get("embryo_top"),
                source_url=r.get("source_url"), source_name=r.get("source_name"),
                notes=r.get("notes"),
            )
            if existing:
                for k, v in fields.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(SaleEvent(dedup_key=key, **fields))
                added += 1
        db.commit()
        total = db.query(SaleEvent).count()
        print(f"Sale events: +{added} added, {updated} updated, {total} total.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
