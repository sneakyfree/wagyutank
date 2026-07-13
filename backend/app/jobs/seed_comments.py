"""Seed discussion threads on foundation-animal pages to break the empty-room
silence. Knowledgeable, plausible starter comments; real users take it from there.

  python -m app.jobs.seed_comments
"""
from datetime import datetime, timedelta, timezone

from .. import models  # noqa: F401
from ..db import Base, SessionLocal, engine
from ..models import Animal, Comment

BASE = datetime(2026, 7, 5, 12, 0, 0)  # reference "now" for backdating seeds


def _at(days_ago: float) -> datetime:
    return BASE - timedelta(days=days_ago)


# (name fragment, [ {handle, name, body, days, replies:[...]} ])
THREADS = {
    "michifuku": [
        {"h": "tajima_ridge", "n": "Tajima Ridge Cattle", "d": 46,
         "b": "Michifuku is THE cornerstone of American fullblood Wagyu marbling. Nearly every elite pedigree in the country traces back to him. If you're building a herd, you want him behind your cows.",
         "r": [{"h": "doc_kobe", "n": "Dr. K, DVM", "d": 45,
                "b": "Can confirm. His carcass data still holds up decades later — the consistency he throws is what makes him special."}]},
        {"h": "marbling_matt", "n": "Matt R.", "d": 19,
         "b": "Ran Michifuku over our F1 Angus females — the ribeye marbling graded off the charts. Even at premium semen prices it paid for itself at the rail."},
    ],
    "itoshigenami": [
        {"h": "highplains_gen", "n": "High Plains Genetics", "d": 31,
         "b": "If Michifuku is marbling, Itoshigenami is the total package — feet, milk, AND marbling. One of the most underrated foundation bulls out there.",
         "r": [{"h": "f1_finisher", "n": "Cade H.", "d": 30,
                "b": "The Michifuku x Itoshigenami cross is money. Best of both worlds."}]},
    ],
    "shigeshige": [
        {"h": "lonestar_wagyu", "n": "Lone Star Wagyu", "d": 27,
         "b": "Shigeshigetani daughters are some of the best brood cows we've kept — fertility and udders you can count on."},
    ],
    "fukutsuru": [
        {"h": "tajima_ridge", "n": "Tajima Ridge Cattle", "d": 36,
         "b": "Fukutsuru 068 — pure Tajima, incredible marbling fineness. One of the Japanese Venture Partners bulls. His BMS numbers are legendary for a reason."},
    ],
    "kitaguni": [
        {"h": "snowaged", "n": "SnowAged Beef", "d": 18,
         "b": "Kitaguni brings frame and growth to the marbling. Good outcross when your cows are getting a little small."},
    ],
    "yasufuku": [
        {"h": "outback_fullblood", "n": "Outback Fullblood (AU)", "d": 41,
         "b": "The Yasufuku line is the backbone of the Australian herd. Yasufuku genetics command a premium and it's earned."},
    ],
    "haruki": [
        {"h": "doc_kobe", "n": "Dr. K, DVM", "d": 23,
         "b": "Haruki 2 (Kedaka line) adds growth and a little hybrid vigor without giving up marbling. Nice complement to Tajima-heavy cows."},
    ],
    "fuji": [
        {"h": "outback_fullblood", "n": "Outback Fullblood (AU)", "d": 50,
         "b": "Mt. Fuji — one of the ORIGINAL four 1976 bulls. Hyogo/Tajima. A piece of living history, and wild that his semen is still around.",
         "r": [{"h": "pasture2plate", "n": "Dana M.", "d": 49,
                "b": "The '76 bulls — Mt Fuji, Mazda, Rueshaw, Judo — are the DNA of everything in North America. Respect."}]},
    ],
    "mazda": [
        {"h": "highplains_gen", "n": "High Plains Genetics", "d": 33,
         "b": "Mazda — Tottori/Kedaka, one of the '76 bulls. Brought the growth the Tajima lines needed. Story goes he died at 17 chasing a cow. Legend."},
    ],
    "rueshaw": [
        {"h": "kumamoto_reds", "n": "Kumamoto Reds", "d": 28,
         "b": "Rueshaw was the 1975 Japanese Red national champion and the FIRST Wagyu ever registered with the AWA. The American Akaushi breed starts right here.",
         "r": [{"h": "reddirt_akaushi", "n": "Red Dirt Akaushi", "d": 27,
                "b": "People forget the reds when they talk foundation stock. Rueshaw and Judo built the entire American Akaushi herd."}]},
    ],
    "judo": [
        {"h": "reddirt_akaushi", "n": "Red Dirt Akaushi", "d": 24,
         "b": "Judo — one of the two Kumamoto red bulls from 1976. HeartBrand and the whole American Akaushi program owe him everything."},
    ],
    "suzutani": [
        {"h": "tajima_ridge", "n": "Tajima Ridge Cattle", "d": 38,
         "b": "Suzutani — one of the first three fullblood cows to ever leave Japan, back in 1993. 100% Tajima. The maternal foundation of North America right here."},
    ],
    "akiko": [
        {"h": "kumamoto_reds", "n": "Kumamoto Reds", "d": 31,
         "b": "The Akiko / Big Al story is the best in the breed — bred in quarantine in Japan, arrived pregnant, and calved the first fullblood Akaushi on US soil. Unreal history."},
    ],
}


def _find_reg(db, fragment: str) -> str | None:
    from sqlalchemy import func
    a = db.query(Animal).filter(func.lower(Animal.name).like(f"%{fragment}%")) \
        .order_by(Animal.registration_no).first()
    return a.registration_no if a else None


def main():
    from .. import tank
    if tank.key() != "wagyu":
        # THREADS below are curated WAGYU discussions keyed by wagyu sire-name
        # fragments — meaningless (or name-collision-dangerous) on another breed.
        print(f"seed_comments is wagyu-curated content — skipping for tank '{tank.key()}'.")
        return
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    inserted = 0
    try:
        for fragment, threads in THREADS.items():
            reg = _find_reg(db, fragment)
            if not reg:
                continue
            if db.query(Comment).filter(Comment.animal_reg == reg, Comment.is_seed == True).first():  # noqa: E712
                continue
            for t in threads:
                top = Comment(animal_reg=reg, author_handle=t["h"], author_name=t["n"],
                              body=t["b"], is_seed=True, likes=max(1, int(t["d"] / 6)),
                              created_at=_at(t["d"]))
                db.add(top)
                db.flush()
                inserted += 1
                for r in t.get("r", []):
                    db.add(Comment(animal_reg=reg, author_handle=r["h"], author_name=r["n"],
                                   body=r["b"], is_seed=True, parent_id=top.id,
                                   likes=max(1, int(r["d"] / 8)), created_at=_at(r["d"])))
                    inserted += 1
            db.commit()
        print(f"Seeded {inserted} discussion comment(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
