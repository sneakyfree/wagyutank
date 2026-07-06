"""Seed WagyuTank house ads (shown free until paid inventory fills the slots).

  python -m app.jobs.seed_ads
"""
from ..db import Base, SessionLocal, engine
from ..models import Ad

HOUSE_ADS = [
    dict(headline="Sell your genetics — free", placement="feed", cta="List now",
         body="List semen, embryos, or cloning rights in under a minute. Type a registration "
              "number and we write the ad for you.", link_url="https://www.wagyutank.com/sell"),
    dict(headline="Every Wagyu straw for sale, one place", placement="feed", cta="Browse the Roundup",
         body="The Roundup gathers frozen Wagyu genetics from across the web — semen, embryos, "
              "cloning — with export eligibility at a glance.", link_url="https://www.wagyutank.com/roundup"),
    dict(headline="Advertise on WagyuTank", placement="sidebar", cta="See ad options",
         body="Put your ranch or vendor brand in front of Wagyu buyers worldwide.",
         link_url="https://www.wagyutank.com/advertise"),
    dict(headline="The world's Wagyu genetics marketplace", placement="banner", cta="Get started",
         body="Buy and sell frozen Wagyu & Akaushi genetics — globally, with export eligibility, "
              "pedigree records, and the world's deepest breed history.",
         link_url="https://www.wagyutank.com/"),
    dict(headline="Know your bloodlines", placement="sidebar", cta="Explore",
         body="57 foundation bulls & cows, photographed and documented — the deepest Wagyu "
              "breed history anywhere.", link_url="https://www.wagyutank.com/foundation"),
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        n = 0
        for a in HOUSE_ADS:
            exists = db.query(Ad).filter(Ad.is_house == True, Ad.headline == a["headline"]).first()  # noqa: E712
            if exists:
                continue
            db.add(Ad(advertiser_name="WagyuTank", is_house=True, status="active", weight=1, **a))
            n += 1
        db.commit()
        print(f"Seeded {n} house ad(s). Total active: "
              f"{db.query(Ad).filter(Ad.status == 'active').count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
