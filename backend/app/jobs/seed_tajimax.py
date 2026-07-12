"""Seed TAJIMAX (FB16684) — Grant's own flagship herd sire — as a real, owned
listing on WagyuTank: a seller account (Whitmer Cattle Co. / WagyuRanch.com), the
canonical Animal profile (pedigree + bio + marbling), and one live semen Listing.

Copy is Grant's own 2026 Spring Semen Offering writeup + the recovered
WagyuRanch.com catalog. Idempotent — safe to re-run.

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
VIDEO = "https://www.youtube.com/embed/oDRh--vpJHY"   # TAJIMAX on cows

BIO = """I've spent months of my life riding through the largest fullblood herds on three continents, and to this day I've never seen a frame-score-9 bull at 2,400 lb on cows like TAJIMAX. He stands 64" at the hip with a freakish, plane-straight backline you can't believe until you see it in person — after a lifetime of looking over buffalo-backed high Tajimas. In the video on his page those are 1,200 lb mature cows with calves, and TAJ makes them look like yearlings.

What makes him mind-blowing is that he is OVER 60% Tajima. Historically, increasing marbling and growth was a mutually exclusive decision — you could only gain one at the expense of the other. TAJIMAX is that rare caliber of freak bull that lets you spike frame, Tajima, milk and marbling in your fullblood calf crop all in one shot. We fed out and froze many a TAJIMAX steer over the years, and TAJ ribeyes are as beautiful as any Michifuku or Sanjirou you will ever see — only with an extra 200–400 lb of red meat hanging on the hook.

He follows a legendary line. Z278 outperformed his sire 001 in nearly every statistical category, and TAJIMAX has continued the tradition by outperforming his reference sire Z278 — highlighted by a staggering 111 yearling weight ratio — and has now become a reference sire himself, with more registered progeny than his famous daddy Z278.

I spent hours riding around with the great Bruce Hemmingsen, who personally picked the original Wagyu cattle in Japan, got them through quarantine, rode over on the plane next to MICHIFUKU and 068, and maintained the largest fullblood herd in the world outside Japan for years. Having sent tens of thousands of feeders to the slaughterhouse, he told me the "flat bone" and feed efficiency of the Tajimas was mind-blowing — their yield coefficient often 5–7% higher than the rounder-boned Shimanes, Kedakas and continental breeds, and they eat a lot less per pound gained. As feed-efficiency selection becomes more common, he said, high-Tajima blood will be sought after more and more. TAJIMAX has that flat Tajima bone with a straight topline that just doesn't add up.

We calved out hundreds of TAJIMAX calves over the years and never had to pull a calf — even the year he bred half a dozen 8–9 month heifers that were left in a little too late; every one calved out under 800 lb with no issues whatsoever. After all these years I would breed TAJIMAX to any set of heifers, any breed, and sleep like a baby with zero dystocia anxiety.

TAJIMAX was registered before herd brands were required, so anyone can use him in their program and not be advertising for someone else — he is listed in the herd book simply as "TAJIMAX," with no herd brand in front of his name. TAJIMAX is his own adjective."""

LISTING_DESC = """2026 TAJIMAX Seedstock Spring Semen Offering — 1,901 straws, collected and stored at Great Lakes Sire Service in Bronson, MI.

TAJIMAX (FB16684) is the new-age reference sire: a frame-score-9, 2,400 lb, OVER 60% Tajima freak with a 111 yearling weight ratio and a straight, show-Angus topline — the rare bull that spikes frame, Tajima, milk and marbling all in one shot, without trading marbling for growth. He now has more registered progeny than his reference sire Z278. Buying TAJIMAX right now is like buying 001 straws in the late '90s or Z278 straws in the 2010's — only TAJIMAX outperforms them both.

He's been heavily used in the dairy industry; now that we've realized how few straws are left, we want as much of it as possible in the hands of seedstock programs so this abominable freak's genetics can influence the breed for decades. Zero dystocia — we calved out hundreds and never pulled one.

Volume pricing (per straw):
• 1–10: $17   • 11–20: $16   • 21–50: $15   • 51–100: $14   • 101–200: $13
• 201–300: $12   • 301–500: $11   • 501–1,000: $10   • 1,001+: $8.50

If someone wants to be the evil dark lord of the TAJIMAX franchise, one call and $8.50 a straw buys it all.

To order: PayPal/Venmo @GrantWhitmer · CashApp $TheWindstorm · Cell 801-259-9358. Text how much you sent, where you sent it, and your email, and I'll cc you the semen-release email to Great Lakes.

— Grant"""

ANIMAL = dict(
    registration_no=REG,
    name="TAJIMAX",
    animal_type=AnimalType.BULL,
    breed="Fullblood Black",
    bloodline="Tajima",
    bloodline_detail=">60% Tajima · Westholme Hirashigetayasu Z278 × GAW Sanshiga",
    blood_percentage="100% Fullblood (>60% Tajima)",
    birth_year=2012,
    sire_reg="FB8376",
    sire_name="Westholme Hirashigetayasu Z278",
    dam_name="GAW Sanshiga",
    registry="AWA",
    is_foundation=False,
    source=AnimalSource.SELLER,
    notable=("The new-age reference sire — a frame-score-9, 2,400 lb, >60% Tajima freak "
             "with a 111 yearling weight ratio and a straight backline you won't believe "
             "until you see it."),
    marbling_note=("Frame score 9 · 2,400 lb on cows · 64\" at the hip · >60% Tajima · SCD AA-6, "
                   "carrier free. 111 yearling weight ratio — outperforms his reference sire Z278 "
                   "in nearly every category and now has more registered progeny than Z278. The "
                   "flat Tajima bone gives a 5–7% higher yield coefficient and superior feed "
                   "efficiency (per Bruce Hemmingsen). TAJ ribeyes rival any Michifuku or Sanjirou "
                   "with 200–400 lb more red meat on the hook."),
    bio=BIO,
    photo_url="/foundation/FB16684.jpg",
    photo_note="TAJIMAX at 4 years, 2,400 lb on cows — Whitmer Cattle Co. / WagyuRanch.com",
)

LISTING = dict(
    product_type=ProductType.SEMEN,
    title="Wagyu Semen — TAJIMAX (FB16684): 2,400 lb, >60% Tajima reference sire",
    animal_reg=REG,
    semen_type=SemenType.CONVENTIONAL,
    straws_per_unit=1,
    unit_price=17.0,
    currency="USD",
    sale_type=SaleType.FIXED,
    quantity_available=1901,
    quantity_visibility=QuantityVisibility.EXACT,
    css_status="css",
    export_eligibility=["AUS"],
    who_pays_shipping=WhoPaysShipping.BUYER,
    facility_handles_shipping=True,
    photo_url="/foundation/FB16684.jpg",
    video_embed_url=VIDEO,
    status=ListingStatus.ACTIVE,
    description=LISTING_DESC,
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
        print(f"Listing #{listing.id} — {listing.title} @ ${listing.unit_price}/straw "
              f"[{listing.status.value}] video={'yes' if listing.video_embed_url else 'no'}")
        print("Now run:  python -m app.jobs.apply_photos   (sets primary + gallery)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
