"""The Roundup — public, attributed aggregation of Wagyu-genetics listings found
elsewhere on the web. These are NOT WagyuTank vendor listings; every response
links back to the original source, and there is no on-site checkout."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AggregatedListing, ProductType, RemovalRequest
from ..schemas import AggregatedOut
from ..security import create_takedown_token, takedown_from_token
from ..services import email as email_service
from ..services import ratelimit

router = APIRouter(prefix="/api/roundup", tags=["roundup"])

# Registrable-domain suffixes that are two labels deep (so a sub.example.co.uk
# email is matched against example.co.uk, not co.uk). Not exhaustive — on any
# ambiguity the match simply fails and the request falls to admin review, which
# is the safe default.
_MULTI_TLD = {
    "co.uk", "org.uk", "me.uk", "com.au", "net.au", "org.au", "co.nz", "com.br",
    "com.mx", "co.za", "com.ar", "com.co", "com.py", "com.uy", "com.pe", "co.jp",
    "or.jp", "ne.jp", "com.tr", "co.il", "com.sg", "co.id", "com.ph", "co.th",
}


def _registrable(host: str) -> str:
    """Reduce a hostname to its registrable domain (strip www, port, subdomains)."""
    host = (host or "").strip().lower().rstrip(".").split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    parts = [p for p in host.split(".") if p]
    if len(parts) <= 2:
        return ".".join(parts)
    return ".".join(parts[-3:]) if ".".join(parts[-2:]) in _MULTI_TLD else ".".join(parts[-2:])


def _domain_matches(email: str, source_site: str) -> bool:
    """True only when the email's domain is the same registrable domain as the
    listing's source website — i.e. the requester can receive mail at the seller's
    own domain. This is what stops one bad actor from wiping a rival's listings."""
    if "@" not in email:
        return False
    edom = _registrable(email.rsplit("@", 1)[1])
    return bool(edom) and edom == _registrable(source_site)


def _client_ip(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip")
            or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "?"))


class FlagBody(BaseModel):
    email: str


@router.get("", response_model=list[AggregatedOut])
def browse(
    product_type: ProductType | None = None,
    bloodline: str | None = None,
    region: str | None = Query(None, description="NA/SA/CAM/EU/AU/AS"),
    country: str | None = None,
    css: str | None = Query(None, description="css | domestic"),
    export_to: str | None = Query(None, description="EU/AUS/CAN/... export destination"),
    animal: str | None = Query(None, description="match sire name or registration number"),
    q: str | None = None,
    sort: str = Query("recent", pattern="^(recent|price_asc|price_desc)$"),
    limit: int = Query(40, le=100),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(AggregatedListing).filter(
        AggregatedListing.status == "active", AggregatedListing.flagged == False  # noqa: E712
    )
    if product_type:
        query = query.filter(AggregatedListing.product_type == product_type)
    if bloodline:
        query = query.filter(AggregatedListing.bloodline == bloodline)
    if region:
        query = query.filter(AggregatedListing.region == region.upper())
    if country:
        query = query.filter(AggregatedListing.country == country.upper())
    if css in ("css", "domestic"):
        query = query.filter(AggregatedListing.css_status == css)
    if animal:
        like = f"%{animal.lower()}%"
        query = query.filter(or_(
            func.lower(AggregatedListing.animal_name).like(like),
            func.lower(AggregatedListing.animal_reg).like(like),
        ))
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(or_(
            func.lower(AggregatedListing.title).like(like),
            func.lower(AggregatedListing.seller_name).like(like),
            func.lower(AggregatedListing.animal_name).like(like),
            func.lower(AggregatedListing.animal_reg).like(like),
            func.lower(AggregatedListing.bloodline).like(like),
        ))
    if sort == "price_asc":
        query = query.order_by(AggregatedListing.price.asc().nullslast())
    elif sort == "price_desc":
        query = query.order_by(AggregatedListing.price.desc().nullslast())
    else:
        query = query.order_by(AggregatedListing.last_seen_at.desc())
    rows = query.offset(offset).limit(limit if not export_to else 200).all()
    if export_to:
        dest = export_to.upper()
        rows = [r for r in rows if dest in (r.export_regions or [])][:limit]
    return rows


@router.get("/index")
def price_index(db: Session = Depends(get_db)):
    """The Wagyu Genetics Price Index — live market + marquee-sire semen pricing."""
    from ..services import price_index as pidx
    return pidx.compute(db)


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    from sqlalchemy import func
    active = AggregatedListing.status == "active"
    base = db.query(AggregatedListing).filter(active, AggregatedListing.flagged == False)  # noqa: E712
    sites = [s[0] for s in db.query(AggregatedListing.source_site).filter(active).distinct()]
    regions = dict(
        db.query(AggregatedListing.region, func.count())
        .filter(active, AggregatedListing.region != None)  # noqa: E711
        .group_by(AggregatedListing.region).all()
    )
    countries = sorted(c[0] for c in db.query(AggregatedListing.country)
                       .filter(active, AggregatedListing.country != None).distinct() if c[0])  # noqa: E711
    css_export = base.filter(AggregatedListing.css_status == "css").count()
    bloodlines = dict(
        db.query(AggregatedListing.bloodline, func.count())
        .filter(active, AggregatedListing.bloodline != None)  # noqa: E711
        .group_by(AggregatedListing.bloodline).order_by(func.count().desc()).all()
    )
    return {"active": base.count(), "sources": len(sites), "sites": sorted(sites),
            "regions": regions, "countries": countries, "css_export_eligible": css_export,
            "bloodlines": bloodlines}


@router.get("/{listing_id}/go")
def go(listing_id: int, db: Session = Depends(get_db)):
    """Count the outbound click and redirect to the original listing."""
    row = db.get(AggregatedListing, listing_id)
    if not row:
        raise HTTPException(404, "Listing not found")
    row.outbound_clicks += 1
    db.commit()
    return RedirectResponse(row.source_url, status_code=302)


def _takedown_page(msg: str) -> str:
    return (f"<div style='font-family:sans-serif;max-width:520px;margin:60px auto;"
            f"text-align:center;line-height:1.6'>"
            f"<h2 style='color:#8a6d2b'>WagyuTank Roundup</h2><p>{msg}</p>"
            f"<p style='color:#888;font-size:13px'>The Roundup only ever links to public "
            f"listings on their original sites — it never hosts your photos or ad copy.</p></div>")


@router.post("/{listing_id}/flag")
def flag(listing_id: int, payload: FlagBody, request: Request, db: Session = Depends(get_db)):
    """Request removal of a Roundup listing. Requesting NEVER hides anything on its
    own (that would let one bad actor wipe a competitor's listings). Instead:

      - If the email is on the listing's OWN source domain, we email a one-click
        confirmation link there; clicking it removes all of that seller's listings.
      - Otherwise the request goes to the admin review queue and nothing changes.

    Rate-limited per IP so the review queue can't be flooded."""
    if not ratelimit.allow(f"roundup_flag:ip:{_client_ip(request)}", 5, 3600):
        raise HTTPException(429, "Too many requests — please try again later.")
    row = db.get(AggregatedListing, listing_id)
    if not row:
        raise HTTPException(404, "Listing not found")
    email = (payload.email or "").strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(400, "Please provide a valid email address.")

    matched = _domain_matches(email, row.source_site)
    db.add(RemovalRequest(listing_id=listing_id, source_site=row.source_site,
                          requester_email=email, domain_matched=matched, status="pending"))
    db.commit()

    if matched:
        token = create_takedown_token(row.source_site, email)
        host = request.headers.get("host", "api.wagyutank.com")
        scheme = "http" if ("localhost" in host or "127.0.0.1" in host) else "https"
        link = f"{scheme}://{host}/api/roundup/takedown?token={token}"
        html = (f"<div style='font-family:sans-serif;max-width:520px;margin:0 auto;line-height:1.6'>"
                f"<h2 style='color:#8a6d2b'>Confirm removal from the WagyuTank Roundup</h2>"
                f"<p>We received a request to remove the Wagyu-genetics listings from "
                f"<strong>{row.source_site}</strong> from the WagyuTank Roundup (a free index that "
                f"links back to your own site).</p>"
                f"<p>If that was you, click below to remove them. If not, ignore this email — nothing "
                f"will change.</p>"
                f"<p style='margin:24px 0'><a href='{link}' style='background:#8a6d2b;color:#fff;"
                f"padding:12px 22px;border-radius:6px;text-decoration:none'>Remove my listings</a></p>"
                f"<p style='color:#888;font-size:13px'>This link expires in 7 days.</p></div>")
        email_service.send(email, "Confirm removal from the WagyuTank Roundup", html)
        return {"status": "verify",
                "message": f"We've emailed a confirmation link to {email}. Click it to remove your listings."}

    return {"status": "review",
            "message": ("Thanks — your removal request has been received and our team will review it. "
                        "To remove listings instantly, send the request from an email address on the "
                        "listing's own website (e.g. name@" + _registrable(row.source_site) + ").")}


@router.get("/takedown", response_class=HTMLResponse)
def takedown_confirm(token: str, db: Session = Depends(get_db)):
    """One-click confirmation (from the emailed link) — removes every active Roundup
    listing from the verified source domain."""
    data = takedown_from_token(token)
    site = (data or {}).get("site")
    if not site:
        return HTMLResponse(_takedown_page("This removal link is invalid or has expired."),
                            status_code=400)
    rows = db.query(AggregatedListing).filter(
        AggregatedListing.source_site == site,
        AggregatedListing.status != "hidden",
    ).all()
    n = 0
    for r in rows:
        r.status = "hidden"
        r.flagged = True
        n += 1
    from datetime import datetime, timezone
    db.query(RemovalRequest).filter(
        RemovalRequest.source_site == site, RemovalRequest.status == "pending"
    ).update({"status": "actioned", "verified_at": datetime.now(timezone.utc).replace(tzinfo=None)},
             synchronize_session=False)
    db.commit()
    return HTMLResponse(_takedown_page(
        f"Done — {n} listing(s) from <strong>{site}</strong> have been removed from the "
        f"WagyuTank Roundup. Thank you."))
