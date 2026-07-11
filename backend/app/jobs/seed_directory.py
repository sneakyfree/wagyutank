"""Seed the Wagyu Atlas registry from the curated Roundup seed list.

  python -m app.jobs.seed_directory

Every entry in roundup_seeds.json is an agent/hand-verified Wagyu or Akaushi
operation with a website and a country — even when our crawler can't extract
listings from it (JS-only sites, catalog-behind-contact-form, etc.). This puts
ALL of them on the Atlas: country + website minimum, with categories/blurb
filled in by jobs.enrich_directory afterward. Idempotent — upserts by domain,
never overwrites enrichment."""
import json
from pathlib import Path
from urllib.parse import urlparse

from ..db import Base, SessionLocal, engine
from ..models import DirectorySeller
from ..services.aggregator import _REGION_BY_COUNTRY

SEEDS = Path(__file__).resolve().parent.parent / "seed" / "data" / "roundup_seeds.json"

# General livestock/classifieds PLATFORMS in the crawl seed list — useful crawl
# targets, but they're not Wagyu operations, so they don't belong on the Atlas.
_NOT_OPERATIONS = {
    "2dehands.be", "marktplaats.nl", "kleinanzeigen.de", "bazos.cz", "kijiji.ca",
    "gumtree.com.au", "subito.it", "milanuncios.com", "agroanuncios.es", "infoagro.com",
    "agriaffaires.com", "landwirt.com", "mfrural.com.br", "cattlerange.com",
    "livestockmarket.com", "ranchworldads.com", "agriseek.com", "mercadolibre.com.mx",
    "pecuaria.com.br", "mfleiloes.com.br", "programaleiloes.com", "auctionsplus.com.au",
    "bidr.co.nz", "herdyard.com", "deine-tierwelt.de", "annonces-pleinchamp.com",
}


def _registrable(host: str) -> str:
    host = (host or "").lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def main():
    Base.metadata.create_all(bind=engine)
    seeds = json.loads(SEEDS.read_text())
    db = SessionLocal()
    added = updated = 0
    seen: set[str] = set()   # the seed list holds multiple URLs per host
    try:
        for s in seeds:
            site = _registrable(urlparse(s["url"]).netloc)
            if not site or "." not in site or site in seen:
                continue
            seen.add(site)
            if site in _NOT_OPERATIONS or any(site.endswith("." + d) for d in _NOT_OPERATIONS):
                continue
            country = (s.get("country") or "").upper()[:2] or None
            row = db.query(DirectorySeller).filter_by(site=site).first()
            if row:
                if not row.country and country:
                    row.country = country
                    row.region = _REGION_BY_COUNTRY.get(country)
                    updated += 1
                continue
            label = site.split(".")[0].replace("-", " ").replace("_", " ").title()
            db.add(DirectorySeller(
                site=site, name=label or site, url=f"https://{site}",
                country=country, region=_REGION_BY_COUNTRY.get(country or ""),
                categories=[], breeds=[], source="roundup_seed",
            ))
            added += 1
        db.commit()
        total = db.query(DirectorySeller).count()
        print(f"Atlas registry: +{added} added, {updated} updated → {total} sellers total.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
