"""Seed the tank's house ads (shown free until paid inventory fills the slots).

Templated from the tank's brand so every clone gets ITS OWN ads — breed, name,
and links all point at the tank itself. The wagyu tank's output is identical to
the original hand-written set.

  python -m app.jobs.seed_ads
"""
from ..db import Base, SessionLocal, engine
from ..models import Ad
from .. import tank


def house_ads() -> list[dict]:
    b = tank.brand()
    name = b.get("name", "WagyuTank")
    breed = (b.get("breed") or "Wagyu").split(" & ")[0].strip()
    base = tank.base_url()
    kinds = [p.get("label", "").lower() for p in tank.products() if p.get("label")]
    kinds_txt = ", ".join(kinds[:-1]) + (f", or {kinds[-1]}" if len(kinds) > 1 else (kinds[0] if kinds else "genetics"))
    ads = [
        dict(headline="Sell your genetics — free", placement="feed", cta="List now",
             body=f"List {kinds_txt} in under a minute. Type a registration "
                  "number and we write the ad for you.", link_url=f"{base}/sell"),
        dict(headline=f"Every {breed} straw for sale, one place", placement="feed", cta="Browse the Roundup",
             body=f"The Roundup gathers frozen {breed} genetics from across the web — "
                  f"{', '.join(kinds) or 'semen, embryos'} — with export eligibility at a glance.",
             link_url=f"{base}/roundup"),
        dict(headline=f"Advertise on {name}", placement="sidebar", cta="See ad options",
             body=f"Put your ranch or vendor brand in front of {breed} buyers worldwide.",
             link_url=f"{base}/advertise"),
        dict(headline=f"The world's {breed} genetics marketplace", placement="banner", cta="Get started",
             body=f"Buy and sell frozen {b.get('breed', breed)} genetics — globally, with export eligibility, "
                  "pedigree records, and the world's deepest breed history.",
             link_url=f"{base}/"),
        dict(headline="Know your bloodlines", placement="sidebar", cta="Explore",
             body=(f"57 foundation bulls & cows, photographed and documented — the deepest {breed} "
                   "breed history anywhere.") if tank.key() == "wagyu" else
                  (f"The breed's foundation animals, documented — the deepest {breed} "
                   "breed history anywhere."),
             link_url=f"{base}/foundation"),
    ]
    return ads


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n = 0
        for a in house_ads():
            exists = db.query(Ad).filter(Ad.is_house == True, Ad.headline == a["headline"]).first()  # noqa: E712
            if exists:
                continue
            db.add(Ad(advertiser_name=tank.brand().get("name", "WagyuTank"),
                      is_house=True, status="active", weight=1, **a))
            n += 1
        db.commit()
        print(f"Seeded {n} house ad(s). Total active: "
              f"{db.query(Ad).filter(Ad.status == 'active').count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
