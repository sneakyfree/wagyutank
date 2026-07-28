"""Write the tank's effective crawl seed list: curated seeds ∪ the Atlas.

  python -m app.jobs.export_seeds /path/to/out.json

The crawler used to read only the hand-written `tanks/<key>/seed/roundup_seeds.json`.
For Wagyu that file holds 43 sites while the Atlas holds ~390 verified operations
with websites — so the flagship was crawling barely a tenth of the sellers it had
already identified, and the clones (Dexter 132, Gir 111) were seeded better than
the source tank.

Unioning them makes the loop close: jobs.discover_sites adds newly-seen domains to
the Atlas as hidden candidates, and they become crawl targets from the next run on.
Curated seeds always win on ordering so the known-good sites are crawled first if
the page budget runs short.
"""
import json
import sys
from urllib.parse import urlparse

from .. import tank
from ..db import SessionLocal
from ..models import DirectorySeller
from ..services.aggregator import _norm_site


def main() -> None:
    out_path = sys.argv[1] if len(sys.argv) > 1 else "seeds_effective.json"
    seeds: list[dict] = []
    seen: set[str] = set()

    sp = tank.seed_path_strict("roundup_seeds.json")
    if sp is not None:
        try:
            for s in json.loads(sp.read_text()):
                site = _norm_site(urlparse(s.get("url", "")).netloc)
                if not site:
                    continue
                seeds.append(s)
                seen.add(site)
        except Exception as e:
            print(f"export_seeds: could not read curated seeds ({e})")
    curated = len(seeds)

    db = SessionLocal()
    try:
        # Hidden rows are included on purpose: that is how a discovered candidate
        # gets its first crawl and earns promotion to the public Atlas.
        for d in db.query(DirectorySeller).all():
            site = _norm_site(d.site or "")
            if not site or site in seen:
                continue
            url = d.url or f"https://{site}/"
            seeds.append({"url": url, "country": (d.country or "").upper()[:2] or None})
            seen.add(site)
    finally:
        db.close()

    with open(out_path, "w") as f:
        json.dump(seeds, f)
    print(f"export_seeds: {len(seeds)} sites → {out_path} "
          f"({curated} curated + {len(seeds) - curated} from the Atlas)")


if __name__ == "__main__":
    main()
