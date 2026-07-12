"""Seed TAJIMAX (FB16684) — Grant's own flagship herd sire — as a real, owned
listing on WagyuTank: a seller account (Whitmer Cattle Co. / WagyuRanch.com), the
canonical Animal profile (pedigree + bio + marbling), and one live semen Listing.

Sources: Grant's 2019 WagyuRanch.com Semen Catalog + the recovered wagyuranch.com
site + his current Great Lakes Sire Service sales. Idempotent — safe to re-run.

  TANK=wagyu python -m app.jobs.seed_tajimax
"""
from ..db import SessionLocal
from ..models import (
    Animal, AnimalSource, AnimalType, Listing, ListingStatus, ProductType,
    QuantityVisibility, SaleType, SemenType, User, WhoPaysShipping,
)
from ..security import hash_password

SELLER_EMAIL = "grant@wagyuranch.com"
SELLER_HANDLE = "wagyuranch"
SELLER_PASSWORD = "WagyuRanch2012!"   # Grant can reset from the account page

REG = "FB16684"

ANIMAL = dict(
    registration_no=REG,
    name="TAJIMAX",
    animal_type=AnimalType.BULL,
    breed="Fullblood Black",
    bloodline="Tajima",
    bloodline_detail="≥62.5% Tajima · Westholme Hirashigetayasu Z278 × GAW Sanshiga",
    blood_percentage="100% Fullblood (≥62.5% Tajima)",
    birth_year=2012,
    sire_reg="FB8376",
    sire_name="Westholme Hirashigetayasu Z278",
    dam_name="GAW Sanshiga",
    registry="AWA",
    is_foundation=False,
    source=AnimalSource.SELLER,
    notable=("Whitmer Cattle Co.'s flagship high-Tajima herd sire — very possibly the "
             "largest-framed fullblood Wagyu bred outside Japan."),
    marbling_note=("SCD AA-6 · Carrier Free · Frame Score 9 · 2,200+ lb · ≥62.5% Tajima. "
                   "Tested by breeders against the original import bulls, he is repeatedly "
                   "called the largest-framed high-Tajima fullblood they have ever seen."),
    bio=(
        "TAJIMAX (FB16684) is the bull WagyuRanch.com was built around — a true freak of "
        "nature weighing 2,000+ lb before turning three and 2,200+ lb greyhound-lean off "
        "cows at four. He is a 100% fullblood and at least 62.5% Tajima, and may be the "
        "largest-framed high-Tajima bull in the world outside Japan.\n\n"
        "The ancient Wagyu quest has always been to add frame and growth without losing "
        "Tajima percentage. Tajimax is the answer: he lets a breeder inject extreme frame, "
        "growth and high-marbling Tajima blood in a single straw and skip years of slowly "
        "grinding growth up in a high-Tajima herd. His calves are standouts from day one "
        "and mature into the biggest, thickest steers in the feedlot, and he has been used "
        "heavily in fullblood and commercial herds worldwide.\n\n"
        "Sire: Westholme Hirashigetayasu Z278 (FB8376), of the Hirashigekatsu line that "
        "reshaped growth in Japan. Dam: GAW Sanshiga. Despite hundreds of calves out of "
        "fullblood and commercial cows worldwide, we have never heard of a calving-ease "
        "problem attributed to Tajimax — a couple of 700 lb fullblood heifers even bred "
        "back accidentally before 10 months of age and dropped healthy DNA-confirmed "
        "Tajimax calves with no issues.\n\n"
        "Tired of the fugly black-jersey look in your fullblood herd? Tajimax is the antidote."
    ),
    photo_url="/foundation/FB16684.jpg",
    photo_note="TAJIMAX at 4 years, 2,200+ lb — Whitmer Cattle Co. / WagyuRanch.com",
)

LISTING = dict(
    product_type=ProductType.SEMEN,
    title="Wagyu Semen — TAJIMAX (FB16684) · high-Tajima, carrier-free",
    animal_reg=REG,
    semen_type=SemenType.CONVENTIONAL,
    straws_per_unit=1,
    unit_price=15.0,
    currency="USD",
    sale_type=SaleType.FIXED,
    quantity_available=100,
    quantity_visibility=QuantityVisibility.IN_STOCK_ONLY,
    css_status="css",
    export_eligibility=["AUS"],
    who_pays_shipping=WhoPaysShipping.BUYER,
    facility_handles_shipping=True,
    photo_url="/foundation/FB16684.jpg",
    status=ListingStatus.ACTIVE,
    description=(
        "TAJIMAX (FB16684) — Whitmer Cattle Co.'s flagship herd sire and the bull "
        "WagyuRanch.com was built around. 100% fullblood, at least 62.5% Tajima, "
        "SCD AA-6 carrier-free, frame score 9, and 2,200+ lb — very possibly the "
        "largest-framed high-Tajima fullblood bred outside Japan.\n\n"
        "Tajimax injects extreme frame, growth and high-marbling Tajima blood in a "
        "single straw without sacrificing Tajima percentage. His calves are standouts "
        "from day one and mature into the biggest, thickest steers in the feedlot, with "
        "no reported calving-ease issues across hundreds of fullblood and commercial calves.\n\n"
        "Sire: Westholme Hirashigetayasu Z278 (FB8376) · Dam: GAW Sanshiga.\n\n"
        "Conventional semen, currently collected and stored at Great Lakes Sire Service. "
        "CSS conventional exportable available on request. Message for volume pricing."
    ),
)


def _get_or_create_seller(db) -> User:
    u = db.query(User).filter(User.email == SELLER_EMAIL).first()
    if not u:
        u = User(
            email=SELLER_EMAIL,
            hashed_password=hash_password(SELLER_PASSWORD),
            display_name="Whitmer Cattle Co.",
            handle=SELLER_HANDLE,
            bio=("Whitmer Cattle Co. / WagyuRanch.com — Grant Whitmer's fullblood Wagyu "
                 "and Akaushi seedstock program, home of the incomparable Tajimax."),
            location="Lehi, Utah",
            country="US",
        )
        db.add(u)
    # Make/keep it a real seller storefront (idempotent field fills)
    if not u.stripe_account_id:
        u.stripe_account_id = "acct_dev_grant"
    if not u.handle:
        u.handle = SELLER_HANDLE
    u.is_email_verified = True
    db.commit(); db.refresh(u)
    return u


def _upsert_animal(db) -> Animal:
    a = db.query(Animal).filter(Animal.registration_no == REG).first()
    if not a:
        a = Animal(**ANIMAL)
        db.add(a)
    else:
        for k, v in ANIMAL.items():
            setattr(a, k, v)
    db.commit(); db.refresh(a)
    return a


def _upsert_listing(db, seller: User) -> Listing:
    li = (db.query(Listing)
          .filter(Listing.seller_id == seller.id,
                  Listing.animal_reg == REG,
                  Listing.product_type == ProductType.SEMEN)
          .first())
    if not li:
        li = Listing(seller_id=seller.id, **LISTING)
        db.add(li)
    else:
        for k, v in LISTING.items():
            setattr(li, k, v)
    db.commit(); db.refresh(li)
    return li


def main():
    db = SessionLocal()
    try:
        seller = _get_or_create_seller(db)
        animal = _upsert_animal(db)
        listing = _upsert_listing(db, seller)
        print(f"Seller @{seller.handle} (id={seller.id}, seller={seller.is_seller})")
        print(f"Animal {animal.registration_no} '{animal.name}' (id={animal.id})")
        print(f"Listing #{listing.id} — {listing.title} @ ${listing.unit_price}/straw [{listing.status.value}]")
        print("Now run:  python -m app.jobs.apply_photos   (sets primary + gallery)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
