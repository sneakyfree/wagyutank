from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    Bid,
    Listing,
    ListingStatus,
    ProductType,
    QuantityVisibility,
    SaleType,
    User,
)
from ..schemas import (
    AdCopyRequest,
    BidCreate,
    CatalogOptIn,
    ListingCreate,
    ListingOut,
)
from ..security import get_current_user, get_optional_user
from ..services.ai import generate_ad_copy

router = APIRouter(prefix="/api/listings", tags=["listings"])

_PRODUCT_LABEL = {
    ProductType.SEMEN: "Semen",
    ProductType.EMBRYO: "Embryos",
    ProductType.CLONE_RIGHTS: "Cloning Rights",
}


def _quantity_display(li: Listing) -> str:
    vis = li.quantity_visibility
    n = li.quantity_available or 0
    if vis == QuantityVisibility.EXACT:
        unit = "straw" if li.product_type == ProductType.SEMEN else "unit"
        return f"{n} {unit}{'s' if n != 1 else ''} available"
    if vis == QuantityVisibility.RANGE:
        lo = (n // 10) * 10
        return f"{lo}+ available" if lo else "Limited availability"
    if vis == QuantityVisibility.HIDDEN:
        return "Contact for availability"
    return "In stock" if n > 0 else "Sold out"


def to_listing_out(li: Listing) -> ListingOut:
    out = ListingOut.model_validate(li, from_attributes=True)
    out.quantity_display = _quantity_display(li)
    out.featured = bool(li.featured_until and li.featured_until > datetime.now(timezone.utc).replace(tzinfo=None))
    if li.seller:
        out.seller_handle = li.seller.handle
        out.seller_name = li.seller.display_name
    return out


def _auto_title(li: ListingCreate, animal_name: str | None) -> str:
    label = _PRODUCT_LABEL[li.product_type]
    name = animal_name or li.animal_reg or "Wagyu"
    if li.product_type == ProductType.EMBRYO:
        return f"Wagyu Embryos — {name}"
    if li.product_type == ProductType.CLONE_RIGHTS:
        excl = "Exclusive " if li.exclusive else ""
        return f"{excl}Cloning Rights — {name}"
    return f"Wagyu {label} — {name}"


@router.post("", response_model=ListingOut)
def create_listing(payload: ListingCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.is_seller:
        # Soft gate for MVP dev: allow, but flag. In prod require Stripe Connect onboarding.
        pass

    # Config-driven product gate: a tank only accepts the product types its
    # tank.json enables (e.g. a semen-only breed omits embryos/cloning). For
    # WagyuTank all three are enabled, so this changes nothing here.
    from .. import tank
    if payload.product_type and payload.product_type.value not in tank.product_keys():
        raise HTTPException(400, f"This marketplace doesn't accept {payload.product_type.value} listings.")

    # Resolve the animal name for the title (from the canonical registry if we have it).
    # For embryos, the headline animal is the sire.
    from .animals import find_animal  # lazy import to avoid circular import
    primary_reg = payload.animal_reg or (payload.sire_reg if payload.product_type == ProductType.EMBRYO else None)
    animal = find_animal(db, primary_reg) if primary_reg else None
    animal_name = animal.name if animal else None
    if animal_name is None and payload.product_type == ProductType.EMBRYO and payload.sire_reg:
        animal_name = payload.sire_reg

    # Validate sale specifics
    if payload.sale_type == SaleType.FIXED and payload.unit_price is None:
        raise HTTPException(400, "Fixed-price listings need a unit price.")
    if payload.sale_type == SaleType.AUCTION and payload.start_price is None:
        raise HTTPException(400, "Auctions need a start price.")

    title = payload.title or _auto_title(payload, animal_name)
    description = payload.description
    if not description:
        from ..schemas import AnimalUpsert
        upsert = AnimalUpsert(
            name=animal_name or (payload.animal_reg or "Wagyu"),
            registration_no=payload.animal_reg,
            bloodline=animal.bloodline if animal else None,
            bloodline_detail=animal.bloodline_detail if animal else None,
            breed=animal.breed if animal else None,
            sire_name=animal.sire_name if animal else None,
        )
        description = generate_ad_copy(payload.product_type.value, upsert)

    li = Listing(
        seller_id=user.id,
        product_type=payload.product_type,
        title=title,
        description=description,
        animal_reg=payload.animal_reg,
        sire_reg=payload.sire_reg,
        dam_reg=payload.dam_reg,
        semen_type=payload.semen_type,
        embryo_grade=payload.embryo_grade,
        embryo_sex=payload.embryo_sex,
        straws_per_unit=payload.straws_per_unit,
        rights_count=payload.rights_count,
        exclusive=payload.exclusive,
        lab_production_cost=payload.lab_production_cost,
        cloning_facility_id=payload.cloning_facility_id,
        quantity_available=payload.quantity_available,
        quantity_visibility=payload.quantity_visibility,
        per_buyer_cap=payload.per_buyer_cap,
        sale_type=payload.sale_type,
        unit_price=payload.unit_price,
        currency=payload.currency.upper()[:3],
        start_price=payload.start_price,
        reserve_price=payload.reserve_price,
        no_reserve=payload.no_reserve,
        ends_at=payload.ends_at,
        current_bid=payload.start_price if payload.sale_type == SaleType.AUCTION else None,
        storage_facility_id=payload.storage_facility_id,
        on_farm_storage=payload.on_farm_storage,
        who_pays_shipping=payload.who_pays_shipping,
        tank_to_tank_available=payload.tank_to_tank_available,
        local_pickup=payload.local_pickup,
        export_eligibility=payload.export_eligibility,
        css_status=payload.css_status,
        photo_url=payload.photo_url,
        video_embed_url=payload.video_embed_url,
        status=ListingStatus.ACTIVE,
    )
    db.add(li)
    db.commit()
    db.refresh(li)
    return to_listing_out(li)


@router.get("", response_model=list[ListingOut])
def browse(
    product_type: ProductType | None = None,
    seller_id: int | None = None,
    featured: bool = False,
    limit: int = Query(30, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Listing).filter(Listing.status == ListingStatus.ACTIVE)
    if product_type:
        q = q.filter(Listing.product_type == product_type)
    if seller_id:
        q = q.filter(Listing.seller_id == seller_id)
    if featured:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        q = q.filter(Listing.featured_until != None, Listing.featured_until > now)  # noqa: E711
    rows = q.order_by(Listing.created_at.desc()).offset(offset).limit(limit).all()
    return [to_listing_out(x) for x in rows]


@router.get("/mine", response_model=list[ListingOut])
def my_listings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Listing).filter(Listing.seller_id == user.id).order_by(Listing.created_at.desc()).all()
    return [to_listing_out(x) for x in rows]


@router.get("/{listing_id}", response_model=ListingOut)
def get_listing(listing_id: int, db: Session = Depends(get_db)):
    li = db.get(Listing, listing_id)
    if not li:
        raise HTTPException(404, "Listing not found")
    li.views += 1
    db.commit()
    return to_listing_out(li)


@router.post("/{listing_id}/bid", response_model=ListingOut)
def place_bid(listing_id: int, payload: BidCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    li = db.get(Listing, listing_id)
    if not li:
        raise HTTPException(404, "Listing not found")
    if li.sale_type != SaleType.AUCTION or li.status != ListingStatus.ACTIVE:
        raise HTTPException(400, "This listing is not an active auction.")
    if li.is_sample:
        raise HTTPException(400, "This is a sample listing — it shows what your ad will look like and can't be bid on.")
    if li.ends_at and li.ends_at <= datetime.now(timezone.utc).replace(tzinfo=None):
        raise HTTPException(400, "This auction has ended.")
    if li.seller_id == user.id:
        raise HTTPException(400, "You can't bid on your own listing.")
    # NOTE: MVP requires a payment method on file to bid; enforced at Stripe wiring time.
    floor = li.current_bid or li.start_price or 0
    min_next = floor if li.current_bid is None else floor + max(1.0, round(floor * 0.02, 2))
    if payload.amount < min_next:
        raise HTTPException(400, f"Bid must be at least {min_next} {li.currency}.")
    db.add(Bid(listing_id=li.id, bidder_id=user.id, amount=payload.amount))
    li.current_bid = payload.amount
    li.current_bidder_id = user.id
    # Anti-snipe: extend if bid lands in the final 5 minutes.
    if li.ends_at:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if (li.ends_at - now) < timedelta(minutes=5):
            li.ends_at = now + timedelta(minutes=5)
    db.commit()
    db.refresh(li)
    return to_listing_out(li)


@router.post("/{listing_id}/feature", response_model=ListingOut)
def feature_listing(
    listing_id: int,
    days: int = Query(7, ge=1, le=30),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Flat-fee 'Feature this listing' (§15). Payment via Stripe wired later; this marks it featured."""
    li = db.get(Listing, listing_id)
    if not li:
        raise HTTPException(404, "Listing not found")
    if li.seller_id != user.id:
        raise HTTPException(403, "Not your listing.")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    base = li.featured_until if (li.featured_until and li.featured_until > now) else now
    li.featured_until = base + timedelta(days=days)
    db.commit()
    db.refresh(li)
    return to_listing_out(li)


@router.post("/{listing_id}/catalog", response_model=ListingOut)
def toggle_catalog(listing_id: int, payload: CatalogOptIn,
                   user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Seller opts a semen listing in/out of the printed WagyuTank Semen Catalog."""
    li = db.get(Listing, listing_id)
    if not li or li.seller_id != user.id:
        raise HTTPException(404, "Listing not found")
    if li.is_sample:
        raise HTTPException(400, "Sample listings can't join the catalog.")
    if li.product_type != ProductType.SEMEN:
        raise HTTPException(400, "The printed catalog is for semen listings only.")
    li.catalog_opt_in = payload.opt_in
    db.commit(); db.refresh(li)
    return to_listing_out(li)


@router.post("/ai/ad-copy")
def ai_ad_copy(req: AdCopyRequest, _: User | None = Depends(get_optional_user)):
    """Generate (or regenerate) listing copy from the confirmed animal (§9 Job 2)."""
    return {"description": generate_ad_copy(req.product_type.value, req.animal, req.language)}
