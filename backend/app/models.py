"""
The WagyuTank data spine.

Principle #8 — the Animal is the atom: every registration number is ONE canonical
`Animal` row. Listings, the pedigree cache, the pre-loaded foundation registry, photos,
and the public animal pages are all views of this one table.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Enums (stored as strings so SQLite and Postgres behave identically)
# ---------------------------------------------------------------------------
def _enum(e):
    return Enum(e, native_enum=False, length=32, validate_strings=True)


class ProductType(str, enum.Enum):
    SEMEN = "semen"
    EMBRYO = "embryo"
    CLONE_RIGHTS = "clone_rights"


class SaleType(str, enum.Enum):
    FIXED = "fixed"
    AUCTION = "auction"


class ListingStatus(str, enum.Enum):
    DRAFT = "draft"          # lite/progressive publish before pedigree enrichment
    ACTIVE = "active"
    SOLD = "sold"
    ENDED = "ended"
    CANCELLED = "cancelled"


class QuantityVisibility(str, enum.Enum):
    EXACT = "exact"
    RANGE = "range"
    IN_STOCK_ONLY = "in_stock_only"   # default
    HIDDEN = "hidden"


class SemenType(str, enum.Enum):
    CONVENTIONAL = "conventional"
    SEXED_FEMALE = "sexed_female"
    SEXED_MALE = "sexed_male"


class AnimalType(str, enum.Enum):
    BULL = "bull"
    COW = "cow"
    STEER = "steer"


class AnimalSource(str, enum.Enum):
    FOUNDATION = "foundation"   # pre-loaded by us
    CACHE = "cache"             # captured from a seller's first listing
    SELLER = "seller"           # seller-entered, unenriched


class WhoPaysShipping(str, enum.Enum):
    BUYER = "buyer"
    SELLER = "seller"
    SPLIT = "split"


# ---------------------------------------------------------------------------
# User / storefront
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(120))

    # Storefront / brand persona
    handle: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    bio: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(2))
    avatar_url: Mapped[str | None] = mapped_column(String(500))
    banner_url: Mapped[str | None] = mapped_column(String(500))

    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    # Admin / moderation
    role: Mapped[str] = mapped_column(String(12), default="user", index=True)     # user | manager | admin | super_admin
    account_status: Mapped[str] = mapped_column(String(12), default="active", index=True)  # active | suspended | deleted
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Contact / recovery / marketing
    phone: Mapped[str | None] = mapped_column(String(32))
    recovery_email: Mapped[str | None] = mapped_column(String(255))
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, default=True)

    # Two-factor (TOTP)
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    # Stripe Connect (payout + KYC) / customer (buying)
    stripe_account_id: Mapped[str | None] = mapped_column(String(64))
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64))

    # Dual reputation (eBay-style)
    seller_rating: Mapped[float] = mapped_column(Float, default=0.0)
    seller_rating_count: Mapped[int] = mapped_column(Integer, default=0)
    buyer_rating: Mapped[float] = mapped_column(Float, default=0.0)
    buyer_rating_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    listings: Mapped[list[Listing]] = relationship(
        back_populates="seller", foreign_keys="Listing.seller_id"
    )

    @property
    def is_seller(self) -> bool:
        return self.stripe_account_id is not None

    def badges(self) -> list[str]:
        b = []
        if self.is_email_verified:
            b.append("email_verified")
        if self.stripe_account_id:
            b.append("stripe_verified_seller")
        return b


# ---------------------------------------------------------------------------
# Facility directory (storage centers + cloning companies)
# ---------------------------------------------------------------------------
class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    city: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(80), default="")
    country: Mapped[str] = mapped_column(String(2), default="US")
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    services: Mapped[list] = mapped_column(JSON, default=list)   # storage/semen/embryo/export/cloning/tissue_banking
    export_qualified: Mapped[bool] = mapped_column(Boolean, default=False)
    website: Mapped[str] = mapped_column(String(300), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    seller_added: Mapped[bool] = mapped_column(Boolean, default=False)


# ---------------------------------------------------------------------------
# Animal — the canonical spine
# ---------------------------------------------------------------------------
class Animal(Base):
    __tablename__ = "animals"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration_no: Mapped[str | None] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)

    animal_type: Mapped[AnimalType] = mapped_column(_enum(AnimalType), default=AnimalType.BULL)
    breed: Mapped[str | None] = mapped_column(String(60))          # Fullblood Black / Red (Akaushi) / Mishima / F1..F4
    bloodline: Mapped[str | None] = mapped_column(String(60), index=True)  # Tajima / Fujiyoshi / Kedaka / Itozakura / ...
    bloodline_detail: Mapped[str | None] = mapped_column(String(255))
    blood_percentage: Mapped[str | None] = mapped_column(String(20))
    birth_year: Mapped[int | None] = mapped_column(Integer)

    # Pedigree by registration string (self-referential graph, resolved via reg lookups)
    sire_reg: Mapped[str | None] = mapped_column(String(40), index=True)
    dam_reg: Mapped[str | None] = mapped_column(String(40), index=True)
    sire_name: Mapped[str | None] = mapped_column(String(160))
    dam_name: Mapped[str | None] = mapped_column(String(160))

    registry: Mapped[str | None] = mapped_column(String(24))       # AWA / AWA-AU / DigitalBeef / JP
    importer: Mapped[str | None] = mapped_column(String(160))
    import_year: Mapped[int | None] = mapped_column(Integer)
    prefecture: Mapped[str | None] = mapped_column(String(60))     # Japanese prefecture of origin
    is_foundation: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    notable: Mapped[str | None] = mapped_column(Text)              # one-line significance
    bio: Mapped[str | None] = mapped_column(Text)                  # long-form narrative (breed-history section)
    marbling_note: Mapped[str | None] = mapped_column(Text)        # marbling / EBV / carcass reputation
    photo_note: Mapped[str | None] = mapped_column(String(300))    # photo attribution
    au_progeny: Mapped[int | None] = mapped_column(Integer)

    epd_data: Mapped[dict | None] = mapped_column(JSON)            # US EPDs
    ebv_data: Mapped[dict | None] = mapped_column(JSON)            # AU EBVs

    photo_url: Mapped[str | None] = mapped_column(String(500))
    source: Mapped[AnimalSource] = mapped_column(_enum(AnimalSource), default=AnimalSource.SELLER)
    confidence: Mapped[str | None] = mapped_column(String(12))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    listings: Mapped[list[Listing]] = relationship(
        back_populates="animal",
        primaryjoin="Animal.registration_no == foreign(Listing.animal_reg)",
        viewonly=True,
    )
    photos: Mapped[list[AnimalPhoto]] = relationship(back_populates="animal")

    @property
    def slug(self) -> str:
        """Stable, URL-safe identifier — the reg number if it has one, else a
        slugified name (so reg-less foundation cows get real, indexable URLs)."""
        if self.registration_no:
            return self.registration_no
        import re
        s = re.sub(r"[^a-z0-9]+", "-", (self.name or "").lower()).strip("-")
        return s or f"animal-{self.id}"


class AnimalPhoto(Base):
    """Photo candidate index (Content Engine §10) — harvested photos are NEVER
    auto-published; they sit here as candidates until the animal's owner confirms/licenses."""
    __tablename__ = "animal_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_id: Mapped[int] = mapped_column(ForeignKey("animals.id"), index=True)
    url: Mapped[str] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(500))
    attribution: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="candidate")  # candidate / approved / seller_upload
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    animal: Mapped[Animal] = relationship(back_populates="photos")


# ---------------------------------------------------------------------------
# Listing — a straw, an embryo, or a clone-right (three co-equal lines)
# ---------------------------------------------------------------------------
class Listing(Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)

    product_type: Mapped[ProductType] = mapped_column(_enum(ProductType), index=True)
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str | None] = mapped_column(Text)

    # Genetics (references the canonical Animal by registration string)
    animal_reg: Mapped[str | None] = mapped_column(String(40), index=True)  # semen animal / clone source
    sire_reg: Mapped[str | None] = mapped_column(String(40))                # embryo sire
    dam_reg: Mapped[str | None] = mapped_column(String(40))                 # embryo dam

    # Product spec
    semen_type: Mapped[SemenType | None] = mapped_column(_enum(SemenType))
    embryo_grade: Mapped[str | None] = mapped_column(String(40))
    embryo_sex: Mapped[str | None] = mapped_column(String(20))
    straws_per_unit: Mapped[int | None] = mapped_column(Integer)

    # Clone-rights specifics (§7B)
    rights_count: Mapped[int | None] = mapped_column(Integer)        # how many clone-rights offered
    exclusive: Mapped[bool] = mapped_column(Boolean, default=False)  # "the only clone ever"
    lab_production_cost: Mapped[float | None] = mapped_column(Float) # est. cost payable to cloning lab
    cloning_facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"))

    # Quantity + visibility
    quantity_available: Mapped[int] = mapped_column(Integer, default=1)
    quantity_visibility: Mapped[QuantityVisibility] = mapped_column(
        _enum(QuantityVisibility), default=QuantityVisibility.IN_STOCK_ONLY
    )
    per_buyer_cap: Mapped[int | None] = mapped_column(Integer)

    # Pricing / sale
    sale_type: Mapped[SaleType] = mapped_column(_enum(SaleType), default=SaleType.FIXED)
    unit_price: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # Auction fields
    start_price: Mapped[float | None] = mapped_column(Float)
    reserve_price: Mapped[float | None] = mapped_column(Float)
    no_reserve: Mapped[bool] = mapped_column(Boolean, default=False)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime)
    current_bid: Mapped[float | None] = mapped_column(Float)
    current_bidder_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    # Storage & shipping (§6)
    storage_facility_id: Mapped[int | None] = mapped_column(ForeignKey("facilities.id"))
    on_farm_storage: Mapped[bool] = mapped_column(Boolean, default=False)
    facility_handles_shipping: Mapped[bool] = mapped_column(Boolean, default=True)
    who_pays_shipping: Mapped[WhoPaysShipping] = mapped_column(
        _enum(WhoPaysShipping), default=WhoPaysShipping.BUYER
    )
    tank_to_tank_available: Mapped[bool] = mapped_column(Boolean, default=False)
    local_pickup: Mapped[bool] = mapped_column(Boolean, default=False)
    export_eligibility: Mapped[list] = mapped_column(JSON, default=list)  # regions: EU/AUS/CAN/MEX/BR/UK/CN/NZ
    # CSS (Certified Semen Services / NAAB) — the baseline gate for export. Non-CSS = domestic only.
    css_status: Mapped[str] = mapped_column(String(12), default="unknown")  # css | domestic | unknown

    # Media / state
    photo_url: Mapped[str | None] = mapped_column(String(500))
    video_embed_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[ListingStatus] = mapped_column(_enum(ListingStatus), default=ListingStatus.ACTIVE, index=True)
    featured_until: Mapped[datetime | None] = mapped_column(DateTime)
    # Sample listings show new users what an ad looks like — never buyable.
    is_sample: Mapped[bool] = mapped_column(Boolean, default=False)
    # Seller wants this listing in the printed WagyuTank Semen Catalog edition.
    catalog_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    seller: Mapped[User] = relationship(back_populates="listings", foreign_keys=[seller_id])
    animal: Mapped[Animal | None] = relationship(
        back_populates="listings",
        primaryjoin="foreign(Listing.animal_reg) == Animal.registration_no",
        viewonly=True,
    )
    bids: Mapped[list[Bid]] = relationship(back_populates="listing", cascade="all, delete-orphan")


class Bid(Base):
    __tablename__ = "bids"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    bidder_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    listing: Mapped[Listing] = relationship(back_populates="bids")


# ---------------------------------------------------------------------------
# Trust, retention, demand-side
# ---------------------------------------------------------------------------
class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"))
    rater_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    ratee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ratee_role: Mapped[str] = mapped_column(String(8))   # "seller" | "buyer"
    score: Mapped[int] = mapped_column(Integer)          # 1..5
    comment: Mapped[str | None] = mapped_column(Text)
    sub_scores: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Follow(Base):
    __tablename__ = "follows"
    __table_args__ = (UniqueConstraint("follower_id", "target_type", "target_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    follower_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    target_type: Mapped[str] = mapped_column(String(12))   # "seller" | "bloodline" | "animal"
    target_key: Mapped[str] = mapped_column(String(80))    # user handle / bloodline name / reg no
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SavedSearch(Base):
    __tablename__ = "saved_searches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str | None] = mapped_column(String(120))
    query: Mapped[dict] = mapped_column(JSON, default=dict)
    notify: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WantAd(Base):
    __tablename__ = "want_ads"

    id: Mapped[int] = mapped_column(primary_key=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    product_type: Mapped[ProductType] = mapped_column(_enum(ProductType))
    criteria: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AuditLog(Base):
    """Every admin mutation, for accountability. Append-only."""
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    admin_email: Mapped[str] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(48), index=True)   # e.g. user.suspend, settings.update
    target_type: Mapped[str | None] = mapped_column(String(24))
    target_id: Mapped[str | None] = mapped_column(String(48))
    detail: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Campaign(Base):
    """A marketing email blast to the opted-in list."""
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    subject: Mapped[str] = mapped_column(String(200))
    body_html: Mapped[str] = mapped_column(Text)
    segment: Mapped[str] = mapped_column(String(16), default="all")  # all | sellers | buyers
    recipients: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="draft")  # draft | sending | sent
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PasswordReset(Base):
    """Single-use password-reset token (only the sha256 hash is stored)."""
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Event(Base):
    """First-party analytics event — page views + key funnel steps."""
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(40), index=True)
    path: Mapped[str | None] = mapped_column(String(300))
    referrer: Mapped[str | None] = mapped_column(String(300))
    meta: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class UpcomingSale(Base):
    """A scheduled/announced future Wagyu sale — the sales calendar."""
    __tablename__ = "upcoming_sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    sale_name: Mapped[str] = mapped_column(String(200))
    date: Mapped[str | None] = mapped_column(String(24), index=True)  # YYYY-MM-DD or "2027-04 (typical)"
    sort_date: Mapped[str | None] = mapped_column(String(10), index=True)  # YYYY-MM-DD for ordering
    country: Mapped[str | None] = mapped_column(String(40))
    continent: Mapped[str | None] = mapped_column(String(8), index=True)
    venue: Mapped[str | None] = mapped_column(String(240))
    host: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(600))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SaleEvent(Base):
    """A Wagyu auction/sale EVENT with per-category results — the forensic sales
    record that powers the sale-reports charts and the sale-data ticker."""
    __tablename__ = "sale_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    sale_name: Mapped[str] = mapped_column(String(200))
    date: Mapped[str | None] = mapped_column(String(12))      # YYYY-MM-DD if known
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    country: Mapped[str | None] = mapped_column(String(2), index=True)
    continent: Mapped[str | None] = mapped_column(String(8), index=True)  # NA/SA/EU/AS/OC
    venue: Mapped[str | None] = mapped_column(String(240))
    currency: Mapped[str] = mapped_column(String(4), default="AUD")

    gross_total: Mapped[float | None] = mapped_column(Float)
    lots_sold: Mapped[int | None] = mapped_column(Integer)
    top_price: Mapped[float | None] = mapped_column(Float)
    top_price_item: Mapped[str | None] = mapped_column(String(300))

    bull_avg: Mapped[float | None] = mapped_column(Float)
    bull_top: Mapped[float | None] = mapped_column(Float)
    female_avg: Mapped[float | None] = mapped_column(Float)
    female_top: Mapped[float | None] = mapped_column(Float)
    heifer_avg: Mapped[float | None] = mapped_column(Float)
    heifer_top: Mapped[float | None] = mapped_column(Float)
    semen_avg: Mapped[float | None] = mapped_column(Float)
    semen_top: Mapped[float | None] = mapped_column(Float)
    embryo_avg: Mapped[float | None] = mapped_column(Float)
    embryo_top: Mapped[float | None] = mapped_column(Float)

    source_url: Mapped[str | None] = mapped_column(String(600))
    source_name: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NotableSale(Base):
    """Record-setting and headline Wagyu genetics/cattle sales — the "wow" content."""
    __tablename__ = "notable_sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(12), index=True)  # semen|embryo|bull|female|carcass
    animal_name: Mapped[str | None] = mapped_column(String(160))
    headline: Mapped[str] = mapped_column(String(240))
    price: Mapped[float] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(4), default="AUD")
    usd_approx: Mapped[float | None] = mapped_column(Float)   # for sorting / comparison
    unit: Mapped[str | None] = mapped_column(String(24))       # per straw | per embryo | head | total
    country: Mapped[str | None] = mapped_column(String(2))
    sale_venue: Mapped[str | None] = mapped_column(String(120))
    date_label: Mapped[str | None] = mapped_column(String(24))
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    buyer: Mapped[str | None] = mapped_column(String(160))
    seller: Mapped[str | None] = mapped_column(String(160))
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(400))
    is_record: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class MarketQuote(Base):
    """A single figure in the Beef Market Data Center — commodity cattle/beef prices
    (from USDA AMS public-domain reports) and Wagyu premium benchmarks."""
    __tablename__ = "market_quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(16), index=True)  # feeder|fed|cutout|wagyu|context
    label: Mapped[str] = mapped_column(String(160))
    value: Mapped[float | None] = mapped_column(Float)
    value_text: Mapped[str | None] = mapped_column(String(60))     # for ranges like "$50–80"
    unit: Mapped[str | None] = mapped_column(String(24))
    change: Mapped[float | None] = mapped_column(Float)            # period change
    as_of: Mapped[str | None] = mapped_column(String(24))
    source: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(400))
    note: Mapped[str | None] = mapped_column(String(300))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Translation(Base):
    """Cache of machine-translated content (keyed by source-hash + language), so we
    only pay the LLM once per unique string per language."""
    __tablename__ = "translations"

    id: Mapped[int] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(String(72), unique=True, index=True)  # sha256(text)[:32]+lang
    lang: Mapped[str] = mapped_column(String(4), index=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class NewsArticle(Base):
    """Aggregated Wagyu news — a headline + our (translated) gloss + a link back to
    the source. The translated Japanese feed is the differentiator. Never republishes
    full articles."""
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(400))              # English (translated if needed)
    original_title: Mapped[str | None] = mapped_column(String(400))
    summary: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(String(120))
    source_url: Mapped[str] = mapped_column(String(700))
    region: Mapped[str] = mapped_column(String(8), index=True)   # US|AU|JP|EU|SA|OTHER
    language: Mapped[str] = mapped_column(String(4), default="en")
    is_translated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(12), default="active", index=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0)


class Comment(Base):
    """Discussion thread attached to a foundation animal's media-center page.
    Seed comments (is_seed) prime the conversation; real users post the rest."""
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    animal_reg: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    author_handle: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str | None] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("comments.id"), index=True)
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(12), default="visible")  # visible | hidden
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PriceSnapshot(Base):
    """Daily snapshot of the Wagyu Genetics Price Index (from Roundup data), so the
    ticker can show a real trend over time."""
    __tablename__ = "price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(60), index=True)  # market:semen | sire:michifuku | ...
    avg_price: Mapped[float | None] = mapped_column(Float)
    count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class JobRun(Base):
    """One execution of a scheduled spider/job — powers the System Health dashboard."""
    __tablename__ = "job_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job: Mapped[str] = mapped_column(String(48), index=True)   # news | roundup | digest | radar | ...
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    seen: Mapped[int] = mapped_column(Integer, default=0)
    added: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(String(500))


class SourceHealth(Base):
    """Per-source contribution tracking — which of the individual spiders (news
    feeds, roundup sources, engines) are live and still contributing."""
    __tablename__ = "source_health"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    type: Mapped[str] = mapped_column(String(24), index=True)   # news_feed | engine | roundup_source
    label: Mapped[str] = mapped_column(String(160))
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime)   # last time it contributed >0
    last_count: Mapped[int] = mapped_column(Integer, default=0)
    runs: Mapped[int] = mapped_column(Integer, default=0)
    ok_runs: Mapped[int] = mapped_column(Integer, default=0)


class Setting(Base):
    """Runtime key/value config editable from the admin panel — so the AI provider,
    launch flags, fees, and aggregator knobs can change without a redeploy."""
    __tablename__ = "settings_kv"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Ad(Base):
    """Paid (or house) advertising — ranch banners and vendor promos placed around
    the site. House ads (is_house=True) are WagyuTank's own promos shown for free
    until inventory fills. Advertiser submissions start `pending` and go live on
    approval. Placements: feed (in listing grids), sidebar, banner (wide strip)."""
    __tablename__ = "ads"

    id: Mapped[int] = mapped_column(primary_key=True)
    advertiser_name: Mapped[str] = mapped_column(String(160))
    contact_email: Mapped[str | None] = mapped_column(String(160))
    headline: Mapped[str] = mapped_column(String(120))
    body: Mapped[str | None] = mapped_column(String(300))
    image_url: Mapped[str | None] = mapped_column(String(600))
    link_url: Mapped[str] = mapped_column(String(600))
    cta: Mapped[str] = mapped_column(String(40), default="Learn more")

    placement: Mapped[str] = mapped_column(String(12), default="feed", index=True)  # feed|sidebar|banner
    tier: Mapped[str | None] = mapped_column(String(16))  # bronze|silver|gold (pricing tier)
    is_house: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)  # pending|active|paused|expired
    weight: Mapped[int] = mapped_column(Integer, default=1)  # rotation weight (higher tier = more)

    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id"), index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(12), default="purchase")  # purchase | feature
    amount_cents: Mapped[int] = mapped_column(Integer)                 # what the buyer pays
    application_fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    stripe_payment_intent: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(12), default="pending")  # pending | paid | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class AggregatedListing(Base):
    """"The Roundup" — a listing found elsewhere on the web and surfaced here as a
    free, attributed pointer back to the source. NOT a WagyuTank vendor listing: it
    stores extracted *facts* + our own neutral summary + a link to the original.
    Never rehosts the seller's ad copy or images. Sellers can opt out (flag)."""
    __tablename__ = "aggregated_listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    dedup_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)

    product_type: Mapped[ProductType] = mapped_column(_enum(ProductType), index=True)
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str | None] = mapped_column(Text)          # our neutral blurb, not their copy

    animal_name: Mapped[str | None] = mapped_column(String(160), index=True)  # sire / animal
    animal_reg: Mapped[str | None] = mapped_column(String(40), index=True)
    bloodline: Mapped[str | None] = mapped_column(String(60), index=True)

    price: Mapped[float | None] = mapped_column(Float)
    price_unit: Mapped[str | None] = mapped_column(String(40))  # "per straw" / "per embryo"
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    quantity_text: Mapped[str | None] = mapped_column(String(80))

    seller_name: Mapped[str | None] = mapped_column(String(160))
    location: Mapped[str | None] = mapped_column(String(160))
    country: Mapped[str | None] = mapped_column(String(2), index=True)
    region: Mapped[str | None] = mapped_column(String(24), index=True)  # NA/SA/CA/EU/AU/AS — for the international feel

    # Export eligibility (extracted from the source when stated)
    css_status: Mapped[str] = mapped_column(String(12), default="unknown")  # css | domestic | unknown
    export_regions: Mapped[list] = mapped_column(JSON, default=list)  # EU/AUS/CAN/MEX/BR/UK/CN/NZ

    source_site: Mapped[str] = mapped_column(String(120), index=True)  # domain / name
    source_url: Mapped[str] = mapped_column(String(600))               # link back to original

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    # Best-available "when was the source listing last updated" signal.
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime)
    source_date_type: Mapped[str | None] = mapped_column(String(16))  # shopify | stated | page-header
    status: Mapped[str] = mapped_column(String(12), default="active", index=True)  # active | delisted | hidden
    outbound_clicks: Mapped[int] = mapped_column(Integer, default=0)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)  # opt-out / removal requested
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CatalogSubmission(Base):
    """An entry a member submits for a printed WagyuTank Semen Catalog edition.
    Distinct from a marketplace listing — this is "put my bull / ranch in the
    book". Carries a mailing address so we can ship the printed copy."""
    __tablename__ = "catalog_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    edition: Mapped[str] = mapped_column(String(40), index=True)  # e.g. "2026-northern"

    ranch_name: Mapped[str] = mapped_column(String(160))
    animal_name: Mapped[str | None] = mapped_column(String(160))
    animal_reg: Mapped[str | None] = mapped_column(String(40))
    bloodline: Mapped[str | None] = mapped_column(String(60))
    product_type: Mapped[str] = mapped_column(String(20), default="semen")  # semen | embryo | bull | ranch
    price_note: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(String(500))

    contact_email: Mapped[str] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(32))
    website: Mapped[str | None] = mapped_column(String(200))

    # Mailing address for the printed copy
    ship_name: Mapped[str | None] = mapped_column(String(160))
    ship_address: Mapped[str | None] = mapped_column(String(240))
    ship_city: Mapped[str | None] = mapped_column(String(120))
    ship_region: Mapped[str | None] = mapped_column(String(120))
    ship_postal: Mapped[str | None] = mapped_column(String(24))
    ship_country: Mapped[str | None] = mapped_column(String(60))

    listing_id: Mapped[int | None] = mapped_column(ForeignKey("listings.id"))
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)  # pending|approved|printed|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped[User] = relationship()
