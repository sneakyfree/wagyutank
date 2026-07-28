"""Re-map existing Roundup bloodlines onto the breed's canonical lines.

  python -m app.jobs.recanon_bloodlines [--apply]

Ingest now canonicalises at write time (aggregator._canon_bloodline); this fixes
the rows already in the table. Dry by default — pass --apply to commit.

The seller's original wording is not lost: _describe() wrote it into the listing
summary at ingest, and that is what the card actually displays.
"""
import sys
from collections import Counter

from sqlalchemy import func

from ..db import SessionLocal
from ..models import AggregatedListing as A
from ..services.aggregator import _canon_bloodline


def main() -> None:
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        before = db.query(func.count(func.distinct(A.bloodline))).filter(
            A.bloodline.isnot(None)).scalar() or 0
        rows = db.query(A).filter(A.bloodline.isnot(None)).all()
        after: Counter = Counter()
        cleared = changed = 0
        for r in rows:
            new = _canon_bloodline(r.bloodline)
            if new != r.bloodline:
                changed += 1
                if new is None:
                    cleared += 1
                r.bloodline = new
            if new:
                after[new] += 1
        print(f"  distinct bloodline values: {before} -> {len(after)}")
        print(f"  rows rewritten: {changed} (of which cleared to none: {cleared})")
        for name, n in after.most_common():
            print(f"    {n:5}  {name}")
        if apply:
            db.commit()
            print("  COMMITTED")
        else:
            db.rollback()
            print("  DRY RUN — pass --apply to commit")
    finally:
        db.close()


if __name__ == "__main__":
    main()
