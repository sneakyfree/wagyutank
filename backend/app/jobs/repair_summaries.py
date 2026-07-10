"""One-off: repair already-stored Roundup summaries with the 'Asking None' and
'1 embryos' bugs. Safe to re-run. New crawls generate correct text going forward.

  python -m app.jobs.repair_summaries
"""
import re

from ..db import SessionLocal
from ..models import AggregatedListing


def _fix(text: str) -> str:
    if not text:
        return text
    t = text.replace("Asking None ", "Asking USD ")
    # "1 embryos" -> "1 embryo", "1 semen straws" -> "1 semen straw", "1 cloning rights" -> "1 cloning right"
    t = re.sub(r"\b1 embryos\b", "1 embryo", t)
    t = re.sub(r"\b1 semen straws\b", "1 semen straw", t)
    t = re.sub(r"\b1 cloning rights\b", "1 cloning right", t)
    return t


def main():
    db = SessionLocal()
    try:
        rows = db.query(AggregatedListing).all()
        n = 0
        for r in rows:
            fixed = _fix(r.summary or "")
            if fixed != (r.summary or ""):
                r.summary = fixed
                n += 1
        db.commit()
        print(f"Repaired {n} listing summaries.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
