from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Animal, AnimalSource, AnimalType, Listing, ListingStatus
from ..schemas import AnimalOut, AnimalUpsert, ListingOut
from ..services.ai import extract_pedigree_from_image
from .listings import to_listing_out

router = APIRouter(prefix="/api/animals", tags=["animals"])


@router.post("/extract")
async def extract_from_screenshot(file: UploadFile = File(...)):
    """Screenshot -> structured pedigree (§9 Job 1). Returns fields shaped like AnimalUpsert.
    Falls back to a manual-entry scaffold if no vision key is configured."""
    data = await file.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 12 MB).")
    return extract_pedigree_from_image(data, file.filename or "")


def find_animal(db: Session, reg_or_name: str) -> Animal | None:
    """Registry lookup for the listing flow's auto-fill: match registration number,
    then exact name, then alias."""
    key = reg_or_name.strip()
    a = db.query(Animal).filter(func.lower(Animal.registration_no) == key.lower()).first()
    if a:
        return a
    a = db.query(Animal).filter(func.lower(Animal.name) == key.lower()).first()
    if a:
        return a
    # slug fallback — reg-less foundation animals are addressed by slugified name
    for cand in db.query(Animal).filter(Animal.is_foundation == True).all():  # noqa: E712
        if cand.slug.lower() == key.lower():
            return cand
    # alias contains (JSON stored as text on SQLite) — best-effort
    return db.query(Animal).filter(Animal.aliases.contains(key)).first()


@router.get("/lookup", response_model=AnimalOut | None)
def lookup(q: str, db: Session = Depends(get_db)):
    """Auto-fill: 'type a reg number, get the pedigree' — served instantly from our
    foundation DB or the cache of previously-listed animals."""
    return find_animal(db, q)


@router.get("/suggest", response_model=list[AnimalOut])
def suggest(q: str, limit: int = 8, db: Session = Depends(get_db)):
    """Typeahead as the seller types a name or reg number."""
    like = f"%{q.lower()}%"
    return (
        db.query(Animal)
        .filter(or_(func.lower(Animal.name).like(like), func.lower(Animal.registration_no).like(like)))
        .order_by(Animal.is_foundation.desc(), Animal.au_progeny.desc().nullslast())
        .limit(min(limit, 25))
        .all()
    )


@router.get("/foundation", response_model=list[AnimalOut])
def foundation_registry(bloodline: str | None = None, db: Session = Depends(get_db)):
    q = db.query(Animal).filter(Animal.is_foundation == True)  # noqa: E712
    if bloodline:
        q = q.filter(Animal.bloodline == bloodline)
    return q.order_by(Animal.au_progeny.desc().nullslast(), Animal.name).all()


@router.get("/{reg}", response_model=AnimalOut)
def get_animal(reg: str, db: Session = Depends(get_db)):
    a = find_animal(db, reg)
    if not a:
        raise HTTPException(404, "Animal not found")
    return a


@router.get("/{reg}/offers", response_model=list[ListingOut])
def animal_offers(reg: str, db: Session = Depends(get_db)):
    """Multi-seller aggregation (§8): every live offer for this animal, in one place."""
    rows = (
        db.query(Listing)
        .filter(func.lower(Listing.animal_reg) == reg.lower(), Listing.status == ListingStatus.ACTIVE,
                Listing.is_sample == False)  # noqa: E712 — sample listings aren't real offers
        .order_by(Listing.unit_price.asc().nullslast())
        .all()
    )
    return [to_listing_out(x) for x in rows]


@router.get("/{reg}/price-history")
def animal_price_history(reg: str, db: Session = Depends(get_db)):
    """Per-bull price analytics: the curated reference price + snapshot history +
    what this animal's genetics currently list for on the marketplace/roundup."""
    from ..models import (AggregatedListing, FoundationReferencePrice, PriceSnapshot,
                          ProductType)
    a = find_animal(db, reg)
    ref = None
    q = db.query(FoundationReferencePrice)
    if a and a.registration_no:
        ref = q.filter(func.lower(FoundationReferencePrice.registration_no) == a.registration_no.lower()).first()
    if not ref:
        ref = q.filter(func.lower(FoundationReferencePrice.registration_no) == reg.lower()).first()
    if not ref and a:
        ref = q.filter(func.lower(FoundationReferencePrice.sire).like(f"%{a.name.lower()}%")).first()

    reference = None
    if ref:
        reference = {
            "semen_usd": ref.semen_usd, "semen_low": ref.semen_low, "semen_high": ref.semen_high,
            "embryo_usd": ref.embryo_usd, "as_of_year": ref.as_of_year,
            "availability": ref.availability, "confidence": ref.confidence,
            "source": ref.source_name, "notes": ref.notes,
        }

    # Snapshot trend for this sire's reference key
    history = []
    if ref:
        key = f"ref:{ref.registration_no or ref.sire}"
        snaps = (db.query(PriceSnapshot).filter(PriceSnapshot.key == key,
                 PriceSnapshot.avg_price != None)  # noqa: E711
                 .order_by(PriceSnapshot.created_at.asc()).all())
        history = [{"date": s.created_at.date().isoformat(), "price": s.avg_price} for s in snaps]

    # What this animal's genetics list for right now on the marketplace + roundup
    reg_key = (a.registration_no if a else reg) or reg
    def _agg(pt):
        rows = [r[0] for r in db.query(AggregatedListing.price).filter(
            AggregatedListing.status == "active", AggregatedListing.product_type == pt,
            AggregatedListing.price != None,  # noqa: E711
            func.lower(AggregatedListing.animal_name).like(f"%{(a.name if a else reg).lower()}%")).all() if r[0]]
        if not rows:
            return None
        return {"count": len(rows), "avg": round(sum(rows) / len(rows), 2),
                "min": round(min(rows), 2), "max": round(max(rows), 2)}
    market = {"semen": _agg(ProductType.SEMEN), "embryo": _agg(ProductType.EMBRYO)}

    return {"registration_no": reg_key, "name": a.name if a else reg,
            "reference": reference, "history": history, "market": market}


def upsert_animal(db: Session, data: AnimalUpsert, source: AnimalSource = AnimalSource.CACHE) -> Animal:
    """Cache flywheel: the first time an animal is listed, store it so the next
    seller gets it instantly."""
    existing = None
    if data.registration_no:
        existing = db.query(Animal).filter(Animal.registration_no == data.registration_no).first()
    if existing:
        return existing
    try:
        atype = AnimalType(data.animal_type)
    except ValueError:
        atype = AnimalType.BULL
    a = Animal(
        registration_no=data.registration_no, name=data.name, animal_type=atype,
        breed=data.breed, bloodline=data.bloodline, bloodline_detail=data.bloodline_detail,
        birth_year=data.birth_year, sire_reg=data.sire_reg, dam_reg=data.dam_reg,
        sire_name=data.sire_name, dam_name=data.dam_name, registry=data.registry,
        epd_data=data.epd_data, ebv_data=data.ebv_data, source=source,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a
