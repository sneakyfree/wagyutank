"""Mock marketplace data for testing — realistic ranches + listings across all
three product lines. Idempotent-ish: skips if mock sellers already exist.

Run:  python -m app.seed.mock
"""
from datetime import timedelta

from ..db import SessionLocal, engine, Base
from ..models import (
    Listing, ListingStatus, ProductType, QuantityVisibility, SaleType,
    SemenType, User, WhoPaysShipping, utcnow,
)
from ..security import hash_password

RANCHES = [
    {"email": "rockingw@example.com", "handle": "rockingw", "name": "Rocking W Wagyu",
     "location": "Brenham, Texas, USA", "country": "US",
     "bio": "Full-blood Tajima program since 2009. Michifuku and Itoshigenami sire lines, marbling-focused."},
    {"email": "tajimacreek@example.com", "handle": "tajimacreek", "name": "Tajima Creek Cattle Co.",
     "location": "Bacchus Marsh, VIC, Australia", "country": "AU",
     "bio": "Australia's Westholme-derived genetics. Export-qualified. Serious about EBVs."},
    {"email": "kumamotoranch@example.com", "handle": "kumamotoranch", "name": "Kumamoto Red Ranch",
     "location": "Flatonia, Texas, USA", "country": "US",
     "bio": "Akaushi / Japanese Red specialists. HeartBrand foundation lines."},
    {"email": "snowaged@example.com", "handle": "snowaged", "name": "Snow Aged Genetics",
     "location": "Alberta, Canada", "country": "CA",
     "bio": "Boutique embryo program. IVF Grade 1 out of proven donor dams."},
    {"email": "eurowagyu@example.com", "handle": "eurowagyu", "name": "EuroWagyu Genetics",
     "location": "Bavaria, Germany", "country": "DE",
     "bio": "Full-blood genetics for the European market. Registered AWA-Australia."},
]

# (product_type, animal_reg, sire_reg, dam_reg, title, price, ccy, sale, extras)
LISTINGS = [
    # Rocking W — Michifuku / Itoshigenami semen, a clone right
    dict(seller=0, product_type="semen", animal_reg="FB1615", semen_type="conventional",
         unit_price=90, qty=200, vis="hidden", export=["AUS", "EU", "CAN"], facility=1, featured_days=14),
    dict(seller=0, product_type="semen", animal_reg="FB1615", semen_type="sexed_female",
         unit_price=145, qty=40, vis="in_stock_only", export=["AUS", "EU"], facility=1),
    dict(seller=0, product_type="clone_rights", animal_reg="FB2461", unit_price=12000,
         lab_cost=20000, exclusive=True, rights_count=1, facility=12, featured_days=30),
    # Tajima Creek — Westholme lines, auction
    dict(seller=1, product_type="semen", animal_reg="FB2101", semen_type="conventional",
         sale="auction", start=1, no_reserve=True, qty=30, export=["AUS"], facility=16, ends_days=5, featured_days=7),
    dict(seller=1, product_type="embryo", sire_reg="FB1615", dam_reg="FB2101",
         unit_price=1450, qty=6, grade="IVF Grade 1", sex="SEXED_FEMALE", export=["AUS", "EU"], facility=16),
    dict(seller=1, product_type="semen", animal_reg="FB2461", semen_type="conventional",
         unit_price=110, qty=75, vis="range", export=["AUS", "EU", "US"], facility=16),
    # Kumamoto Red — Akaushi
    dict(seller=2, product_type="semen", animal_reg=None, semen_type="conventional",
         title_override="Akaushi (Red Wagyu) Semen — HeartBrand foundation line",
         unit_price=65, qty=120, vis="in_stock_only", export=["US"], facility=3),
    dict(seller=2, product_type="embryo", sire_reg=None, dam_reg=None,
         title_override="Akaushi Embryos — Full-blood Red, IVF Grade 1",
         unit_price=900, qty=8, grade="IVF Grade 1", sex="UNSEXED", export=["US", "CAN"], facility=3),
    # Snow Aged — embryos
    dict(seller=3, product_type="embryo", sire_reg="FB1615", dam_reg=None,
         unit_price=1650, qty=4, grade="IVF Grade 1", sex="SEXED_FEMALE", export=["CAN", "US"], facility=2, featured_days=7),
    dict(seller=3, product_type="embryo", sire_reg="FB2461", dam_reg=None,
         sale="auction", start=250, no_reserve=False, reserve=800, qty=3, grade="IVF Grade 2",
         export=["CAN", "US"], facility=2, ends_days=6),
    # EuroWagyu
    dict(seller=4, product_type="semen", animal_reg="FB104", semen_type="conventional",
         unit_price=70, qty=50, vis="in_stock_only", export=["EU"], facility=17),
    dict(seller=4, product_type="clone_rights", animal_reg="FB1615", unit_price=9000,
         lab_cost=18000, exclusive=False, rights_count=3, facility=12),
    dict(seller=4, product_type="semen", animal_reg="FB2101", semen_type="sexed_male",
         unit_price=130, qty=25, vis="exact", export=["EU", "AUS"], facility=17, featured_days=7),
]

_PRODUCT_LABEL = {"semen": "Semen", "embryo": "Embryos", "clone_rights": "Cloning Rights"}


def _title(db, spec):
    if spec.get("title_override"):
        return spec["title_override"]
    from ..models import Animal
    reg = spec.get("animal_reg") or spec.get("sire_reg")
    name = reg or "Wagyu"
    if reg:
        a = db.query(Animal).filter(Animal.registration_no == reg).first()
        if a:
            name = a.name
    pt = spec["product_type"]
    if pt == "embryo":
        return f"Wagyu Embryos — {name}"
    if pt == "clone_rights":
        excl = "Exclusive " if spec.get("exclusive") else ""
        return f"{excl}Cloning Rights — {name}"
    return f"Wagyu Semen — {name}"


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == RANCHES[0]["email"]).first():
            print("Mock sellers already exist — skipping. (Delete them to re-seed.)")
            return
        # Guard against handle/email collisions from prior manual testing.
        for r in RANCHES:
            clash = db.query(User).filter(
                (User.handle == r["handle"]) | (User.email == r["email"])
            ).first()
            if clash:
                r["handle"] = f"{r['handle']}2"
                r["email"] = r["email"].replace("@", "2@")
        sellers = []
        for r in RANCHES:
            u = User(email=r["email"], hashed_password=hash_password("password123"),
                     display_name=r["name"], handle=r["handle"], bio=r["bio"],
                     location=r["location"], country=r["country"], is_email_verified=True,
                     stripe_account_id=f"acct_mock_{r['handle']}",
                     seller_rating=round(4.4 + 0.5 * (hash(r["handle"]) % 10) / 10, 1),
                     seller_rating_count=3 + hash(r["handle"]) % 40)
            db.add(u); sellers.append(u)
        db.commit()
        for u in sellers:
            db.refresh(u)

        from ..services.ai import generate_ad_copy
        from ..schemas import AnimalUpsert
        from ..models import Animal

        n = 0
        for spec in LISTINGS:
            seller = sellers[spec["seller"]]
            pt = ProductType(spec["product_type"])
            title = _title(db, spec)
            reg = spec.get("animal_reg") or spec.get("sire_reg")
            animal = db.query(Animal).filter(Animal.registration_no == reg).first() if reg else None
            desc = generate_ad_copy(pt.value, AnimalUpsert(
                name=(animal.name if animal else title), registration_no=reg,
                bloodline=animal.bloodline if animal else None,
                bloodline_detail=animal.bloodline_detail if animal else None,
                breed=animal.breed if animal else None,
                sire_name=animal.name if (animal and pt == ProductType.EMBRYO) else None,
            ))
            sale = SaleType(spec.get("sale", "fixed"))
            ends = utcnow() + timedelta(days=spec["ends_days"]) if spec.get("ends_days") else None
            feat = utcnow() + timedelta(days=spec["featured_days"]) if spec.get("featured_days") else None
            li = Listing(
                seller_id=seller.id, product_type=pt, title=title, description=desc,
                animal_reg=spec.get("animal_reg"), sire_reg=spec.get("sire_reg"), dam_reg=spec.get("dam_reg"),
                semen_type=SemenType(spec["semen_type"]) if spec.get("semen_type") else None,
                embryo_grade=spec.get("grade"), embryo_sex=spec.get("sex"),
                rights_count=spec.get("rights_count"), exclusive=spec.get("exclusive", False),
                lab_production_cost=spec.get("lab_cost"),
                cloning_facility_id=spec["facility"] if pt == ProductType.CLONE_RIGHTS else None,
                storage_facility_id=spec.get("facility") if pt != ProductType.CLONE_RIGHTS else None,
                quantity_available=spec.get("qty", 1),
                quantity_visibility=QuantityVisibility(spec.get("vis", "in_stock_only")),
                sale_type=sale,
                unit_price=spec.get("unit_price") if sale == SaleType.FIXED else None,
                currency=spec.get("ccy", "USD"),
                start_price=spec.get("start") if sale == SaleType.AUCTION else None,
                reserve_price=spec.get("reserve"), no_reserve=spec.get("no_reserve", False),
                ends_at=ends, current_bid=spec.get("start") if sale == SaleType.AUCTION else None,
                who_pays_shipping=WhoPaysShipping.BUYER,
                export_eligibility=spec.get("export", []),
                featured_until=feat, views=10 + (hash(title) % 400),
                status=ListingStatus.ACTIVE,
            )
            db.add(li); n += 1
        db.commit()
        print(f"Seeded {len(sellers)} ranches and {n} listings.")
        print(f"Totals — users: {db.query(User).count()}, listings: {db.query(Listing).count()}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
