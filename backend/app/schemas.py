from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import (
    ProductType,
    QuantityVisibility,
    SaleType,
    SemenType,
    WhoPaysShipping,
)


# ---- Auth / user ----
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1, max_length=120)
    handle: str | None = Field(default=None, max_length=64)
    phone: str | None = Field(default=None, max_length=32)
    recovery_email: EmailStr | None = None
    marketing_opt_in: bool = True


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    display_name: str
    handle: str | None
    bio: str | None
    location: str | None
    country: str | None
    avatar_url: str | None
    banner_url: str | None
    seller_rating: float
    seller_rating_count: int
    buyer_rating: float
    buyer_rating_count: int


class UserPrivate(UserPublic):
    email: EmailStr
    is_email_verified: bool
    is_seller: bool
    role: str = "user"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPrivate


class StorefrontUpdate(BaseModel):
    display_name: str | None = None
    handle: str | None = Field(default=None, max_length=64)
    bio: str | None = None
    location: str | None = None
    country: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None


# ---- Facility ----
class FacilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    city: str
    state: str
    country: str
    lat: float | None
    lng: float | None
    services: list
    export_qualified: bool
    website: str
    notes: str


class FacilityCreate(BaseModel):
    name: str
    city: str
    state: str = ""
    country: str = "US"
    services: list[str] = []


# ---- Animal (canonical) ----
class AnimalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    registration_no: str | None
    slug: str | None = None
    name: str
    aliases: list
    animal_type: str
    breed: str | None
    bloodline: str | None
    bloodline_detail: str | None
    birth_year: int | None
    sire_reg: str | None
    dam_reg: str | None
    sire_name: str | None
    dam_name: str | None
    registry: str | None
    importer: str | None
    prefecture: str | None = None
    is_foundation: bool
    notable: str | None
    bio: str | None = None
    marbling_note: str | None = None
    photo_note: str | None = None
    au_progeny: int | None
    photo_url: str | None
    source: str


class AnimalUpsert(BaseModel):
    """What the listing flow sends after screenshot extraction / confirmation."""
    registration_no: str | None = None
    name: str
    animal_type: str = "bull"
    breed: str | None = None
    bloodline: str | None = None
    bloodline_detail: str | None = None
    birth_year: int | None = None
    sire_reg: str | None = None
    dam_reg: str | None = None
    sire_name: str | None = None
    dam_name: str | None = None
    registry: str | None = None
    epd_data: dict | None = None
    ebv_data: dict | None = None


# ---- Listing ----
class ListingCreate(BaseModel):
    product_type: ProductType
    title: str | None = None            # auto-generated if omitted
    description: str | None = None

    animal_reg: str | None = None       # semen animal / clone source
    sire_reg: str | None = None         # embryo sire
    dam_reg: str | None = None          # embryo dam

    semen_type: SemenType | None = None
    embryo_grade: str | None = None
    embryo_sex: str | None = None
    straws_per_unit: int | None = None

    # clone-rights
    rights_count: int | None = None
    exclusive: bool = False
    lab_production_cost: float | None = None
    cloning_facility_id: int | None = None

    quantity_available: int = 1
    quantity_visibility: QuantityVisibility = QuantityVisibility.IN_STOCK_ONLY
    per_buyer_cap: int | None = None

    sale_type: SaleType = SaleType.FIXED
    unit_price: float | None = None
    currency: str = "USD"
    start_price: float | None = None
    reserve_price: float | None = None
    no_reserve: bool = False
    ends_at: datetime | None = None

    storage_facility_id: int | None = None
    on_farm_storage: bool = False
    who_pays_shipping: WhoPaysShipping = WhoPaysShipping.BUYER
    tank_to_tank_available: bool = False
    local_pickup: bool = False
    export_eligibility: list[str] = []
    css_status: str = "unknown"

    photo_url: str | None = None
    video_embed_url: str | None = None


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    seller_id: int
    product_type: str
    title: str
    description: str | None
    animal_reg: str | None
    sire_reg: str | None
    dam_reg: str | None
    semen_type: str | None
    embryo_grade: str | None
    embryo_sex: str | None
    rights_count: int | None
    exclusive: bool
    lab_production_cost: float | None
    quantity_display: str = ""
    seller_handle: str | None = None
    seller_name: str | None = None
    quantity_visibility: str
    sale_type: str
    unit_price: float | None
    currency: str
    start_price: float | None
    no_reserve: bool
    ends_at: datetime | None
    current_bid: float | None
    storage_facility_id: int | None
    who_pays_shipping: str
    export_eligibility: list
    css_status: str = "unknown"
    photo_url: str | None
    video_embed_url: str | None
    status: str
    featured: bool = False
    views: int
    created_at: datetime


class BidCreate(BaseModel):
    amount: float


class FeedbackCreate(BaseModel):
    listing_id: int | None = None
    ratee_id: int
    ratee_role: str  # "seller" | "buyer"
    score: int = Field(ge=1, le=5)
    comment: str | None = None
    sub_scores: dict | None = None


class AdCopyRequest(BaseModel):
    product_type: ProductType
    animal: AnimalUpsert
    language: str = "en"
    tone: str = "professional"


class AdOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    advertiser_name: str
    headline: str
    body: str | None
    image_url: str | None
    cta: str
    placement: str
    is_house: bool


class AdSubmit(BaseModel):
    advertiser_name: str
    contact_email: str
    headline: str
    body: str | None = None
    image_url: str | None = None
    link_url: str
    placement: str = "feed"
    tier: str | None = None


class AggregatedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    product_type: str
    title: str
    summary: str | None
    animal_name: str | None
    animal_reg: str | None
    bloodline: str | None
    price: float | None
    price_unit: str | None
    currency: str
    quantity_text: str | None
    seller_name: str | None
    location: str | None
    country: str | None
    region: str | None = None
    css_status: str = "unknown"
    export_regions: list = []
    source_site: str
    outbound_clicks: int
    first_seen_at: datetime
    last_seen_at: datetime
    source_updated_at: datetime | None = None
    source_date_type: str | None = None
