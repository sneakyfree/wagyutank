from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Animal, AnimalSource, AnimalType, Listing, ListingStatus, User
from ..schemas import AnimalOut, AnimalUpsert, ListingOut
from ..security import get_current_user
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
    for cand in db.query(Animal).filter((Animal.is_foundation == True) | (Animal.is_legend == True)).all():  # noqa: E712
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


@router.get("/{reg}/zenkyo")
def animal_zenkyo(reg: str, db: Session = Depends(get_db)):
    """Zenkyo champions in this animal's pedigree — powers the 🏆 badge."""
    import json as _json
    from pathlib import Path as _Path
    a = find_animal(db, reg)
    key = (a.registration_no if a else reg) or reg
    from .. import tank as _tank
    data_path = _tank.seed_path_strict("zenkyo.json")
    if data_path is None:
        return []
    try:
        champs = _json.loads(data_path.read_text()).get("champions", [])
    except Exception:
        champs = []
    hits = []
    for c in champs:
        for fc in c.get("foundation_connections", []):
            if (fc.get("reg") or "").upper() == key.upper():
                hits.append({"champion": c["name"], "name_jp": c.get("name_jp"),
                             "zenkyo_record": c.get("zenkyo_record"), "relationship": fc.get("relationship"),
                             "line": c.get("line")})
    return {"registration_no": key, "champions": hits}


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


def _embed_url(url: str) -> str | None:
    """Turn a YouTube/Vimeo watch URL into an embeddable one. Returns None if we
    can't safely embed it (so we won't iframe an arbitrary page)."""
    import re as _re
    u = (url or "").strip()
    m = _re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{6,})", u)
    if m:
        return f"https://www.youtube.com/embed/{m.group(1)}"
    m = _re.search(r"vimeo\.com/(\d+)", u)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"
    return None


@router.get("/{reg}/videos")
def animal_videos(reg: str, db: Session = Depends(get_db)):
    """Member-shared videos + Theater-harvested videos for this animal, unified.
    Also walks one pedigree step (sire/dam) for 'videos in this pedigree'."""
    from ..models import AnimalVideo, WagyuVideo
    out = []
    member = (db.query(AnimalVideo)
              .filter(func.lower(AnimalVideo.animal_reg) == reg.lower(), AnimalVideo.status == "approved")
              .order_by(AnimalVideo.created_at.desc()).all())
    out += [{"id": f"m{v.id}", "kind": "member", "title": v.title, "embed_url": v.embed_url,
             "submitter_name": v.submitter_name, "created_at": v.created_at} for v in member]

    def _theater(r: str, pedigree_of: str | None = None):
        key = r.upper().replace(" ", "")
        rows = (db.query(WagyuVideo)
                .filter(WagyuVideo.status == "approved", WagyuVideo.embeddable == True,  # noqa: E712
                        (func.upper(WagyuVideo.matched_animal_reg) == r.upper())
                        | func.upper(func.cast(WagyuVideo.matched_regs, __import__("sqlalchemy").String)).like(f'%"{key}"%'))
                .order_by(WagyuVideo.views.desc().nullslast()).limit(8).all())
        return [{"id": f"t{v.id}", "kind": "theater", "theater_id": v.id, "title": v.title,
                 "channel": v.channel, "views": v.views, "embed_url": v.embed_url,
                 "thumbnail_url": v.thumbnail_url, "pedigree_of": pedigree_of} for v in rows]

    out += _theater(reg)
    a = find_animal(db, reg)
    if a:
        if a.name:
            # name-match too (query-matched harvests may lack the reg)
            nm = a.name.lower()
            rows = (db.query(WagyuVideo)
                    .filter(WagyuVideo.status == "approved", WagyuVideo.embeddable == True,  # noqa: E712
                            WagyuVideo.matched_animal_reg == None,  # noqa: E711
                            func.lower(WagyuVideo.title).like(f"%{nm}%"))
                    .order_by(WagyuVideo.views.desc().nullslast()).limit(4).all())
            have = {o.get("theater_id") for o in out if o.get("theater_id")}
            out += [{"id": f"t{v.id}", "kind": "theater", "theater_id": v.id, "title": v.title,
                     "channel": v.channel, "views": v.views, "embed_url": v.embed_url,
                     "thumbnail_url": v.thumbnail_url} for v in rows if v.id not in have]
        for anc_reg, label in ((a.sire_reg, "sire"), (a.dam_reg, "dam")):
            if anc_reg:
                have = {o.get("theater_id") for o in out if o.get("theater_id")}
                out += [v for v in _theater(anc_reg, pedigree_of=label) if v["theater_id"] not in have]
    return out


@router.post("/{reg}/videos")
def submit_animal_video(reg: str, payload: dict = Body(...),
                        user: "User" = Depends(get_current_user), db: Session = Depends(get_db)):
    from ..models import AnimalVideo
    title = (payload.get("title") or "").strip()
    url = (payload.get("video_url") or "").strip()
    if not title or not url:
        raise HTTPException(400, "A title and a video link are required.")
    embed = _embed_url(url)
    if not embed:
        raise HTTPException(400, "Please paste a YouTube or Vimeo link so we can embed it.")
    v = AnimalVideo(animal_reg=reg, user_id=user.id, title=title[:200], video_url=url[:600],
                    embed_url=embed, submitter_name=(user.display_name or user.handle or "A member")[:120],
                    status="approved")
    db.add(v)
    db.commit(); db.refresh(v)
    return {"id": v.id, "title": v.title, "embed_url": v.embed_url,
            "submitter_name": v.submitter_name, "created_at": v.created_at}


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
