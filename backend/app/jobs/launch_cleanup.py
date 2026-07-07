"""Launch cleanup — remove mock marketplace data, seed official SAMPLE listings.

The mock ranches (@example.com sellers with acct_mock_* Stripe ids) made the
marketplace look fake to launch visitors. Replace them with a small set of
clearly-labeled SAMPLE listings owned by the official WagyuTank account, so new
users see exactly what a posted ad will look like. Idempotent.

Run:  python -m app.jobs.launch_cleanup
"""
import secrets

from ..db import SessionLocal
from ..models import (
    Bid, Comment, Event, Feedback, Follow, Listing, ListingStatus, Order,
    PasswordReset, ProductType, QuantityVisibility, SaleType, SemenType, User,
    WhoPaysShipping,
)
from ..security import hash_password

SAMPLE_EMAIL = "samples@wagyutank.com"
SAMPLE_HANDLE = "wagyutank"

_PREAMBLE = (
    "👋 THIS IS A SAMPLE LISTING — WagyuTank just launched, and this ad shows "
    "you exactly what your own listing will look like. Posting is free and "
    "takes about 60 seconds: tap Sell, pick your animal, and our AI writes the "
    "ad copy for you.\n\n"
)

SAMPLES = [
    dict(
        product_type=ProductType.SEMEN,
        title="SAMPLE — Wagyu Semen: Michifuku (FB1615)",
        animal_reg="FB1615",
        semen_type=SemenType.CONVENTIONAL,
        unit_price=95.0, quantity_available=100,
        css_status="css", export_eligibility=["EU", "AUS", "CAN"],
        body=(
            "Conventional semen from Michifuku (FB1615), the foundation Tajima "
            "sire behind more marbling records than any bull of his era. CSS-"
            "collected and export-eligible to the EU, Australia, and Canada. "
            "Stored at a certified facility with tank-to-tank transfer available."
        ),
    ),
    dict(
        product_type=ProductType.EMBRYO,
        title="SAMPLE — Wagyu Embryos: Michifuku × Okutani",
        sire_reg="FB1615", dam_reg="FB1616",
        embryo_grade="IVF Grade 1", embryo_sex="SEXED_FEMALE",
        unit_price=1250.0, quantity_available=6,
        css_status="css", export_eligibility=["EU", "AUS"],
        body=(
            "IVF Grade 1 sexed-female embryos out of Okutani (FB1616), the dam "
            "of the first US-born fullblood, by Michifuku (FB1615). Produced "
            "from CSS semen, so resulting embryos are export-eligible."
        ),
    ),
    dict(
        product_type=ProductType.CLONE_RIGHTS,
        title="SAMPLE — Cloning Rights: preserve a proven sire line",
        animal_reg="FB1615",
        unit_price=12000.0, quantity_available=1,
        rights_count=1, exclusive=False, lab_production_cost=20000.0,
        body=(
            "Cloning rights are WagyuTank's signature category: the right to "
            "produce a genetic copy of a proven animal from a banked cell line. "
            "The price here is for the rights; lab production cost is paid "
            "separately to the cloning facility and is shown transparently on "
            "every clone-rights listing."
        ),
    ),
]


def main():
    db = SessionLocal()
    try:
        # ---- 1. Remove mock ranches + everything that hangs off them ----
        mocks = db.query(User).filter(
            (User.stripe_account_id.like("acct_mock_%"))
            | (User.email.like("%@example.com"))
        ).all()
        uids = [u.id for u in mocks]
        handles = [u.handle for u in mocks if u.handle]
        if uids:
            lids = [lid for (lid,) in db.query(Listing.id).filter(Listing.seller_id.in_(uids))]
            if lids:
                db.query(Bid).filter(Bid.listing_id.in_(lids)).delete(synchronize_session=False)
                db.query(Order).filter(Order.listing_id.in_(lids)).delete(synchronize_session=False)
                db.query(Feedback).filter(Feedback.listing_id.in_(lids)).delete(synchronize_session=False)
                db.query(Listing).filter(Listing.id.in_(lids)).delete(synchronize_session=False)
            db.query(Feedback).filter(
                (Feedback.rater_id.in_(uids)) | (Feedback.ratee_id.in_(uids))
            ).delete(synchronize_session=False)
            db.query(Follow).filter(Follow.follower_id.in_(uids)).delete(synchronize_session=False)
            if handles:
                db.query(Follow).filter(
                    Follow.target_type == "seller", Follow.target_key.in_(handles)
                ).delete(synchronize_session=False)
            db.query(Comment).filter(Comment.user_id.in_(uids)).delete(synchronize_session=False)
            db.query(Event).filter(Event.user_id.in_(uids)).delete(synchronize_session=False)
            db.query(PasswordReset).filter(PasswordReset.user_id.in_(uids)).delete(synchronize_session=False)
            db.query(User).filter(User.id.in_(uids)).delete(synchronize_session=False)
            db.commit()
            print(f"Removed {len(uids)} mock sellers ({', '.join(handles)}) and {len(lids)} mock listings.")
        else:
            print("No mock sellers found — already clean.")

        # ---- 2. Official sample account ----
        owner = db.query(User).filter(User.email == SAMPLE_EMAIL).first()
        if not owner:
            handle = SAMPLE_HANDLE
            if db.query(User).filter(User.handle == handle).first():
                handle = "wagyutank-samples"
            owner = User(
                email=SAMPLE_EMAIL, hashed_password=hash_password(secrets.token_urlsafe(24)),
                display_name="WagyuTank", handle=handle,
                bio=("Official WagyuTank sample listings. These ads show what your "
                     "own listing will look like — post yours from the Sell page."),
                location="WagyuTank HQ", country="US",
                is_email_verified=True, marketing_opt_in=False,
            )
            db.add(owner)
            db.commit(); db.refresh(owner)
            print(f"Created sample account @{owner.handle}.")

        # ---- 3. Sample listings (one per product line) ----
        have = db.query(Listing).filter(Listing.is_sample == True).count()  # noqa: E712
        if have:
            print(f"{have} sample listing(s) already present — skipping seed.")
            return
        for spec in SAMPLES:
            body = spec.pop("body")
            li = Listing(
                seller_id=owner.id, description=_PREAMBLE + body,
                is_sample=True, status=ListingStatus.ACTIVE,
                sale_type=SaleType.FIXED, currency="USD",
                quantity_visibility=QuantityVisibility.IN_STOCK_ONLY,
                who_pays_shipping=WhoPaysShipping.BUYER,
                **spec,
            )
            db.add(li)
        db.commit()
        print(f"Seeded {len(SAMPLES)} sample listings under @{owner.handle}.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
