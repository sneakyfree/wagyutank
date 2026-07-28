"""Turn outbound links seen during the nightly crawl into new crawl targets.

  python -m app.jobs.discover_sites <key>_rendered-candidates.json

This is the step the Roundup was missing. Before it, `roundup_seeds.json` was a
static hand-written file and `seed_directory` seeded the Atlas from that SAME
file — so the crawler could go deeper into sites it already knew but could never
find a new one. Every tank's log read "Atlas registry: +0 added" for weeks and
new-listing counts decayed as the known sites were exhausted.

Breeders link to breeders. The crawler already renders these pages and already
reads every <a href>, so the candidates cost nothing extra to collect. This job
keeps the plausible ones as HIDDEN Atlas rows: they get crawled from the next run
onward (export_seeds unions them into the seed list) and are promoted to a public
Atlas entry only once they actually yield listings — so a bad guess is invisible.

Deliberately dumb: a domain/anchor keyword test and a blocklist, no LLM, no
scoring model. The crawl+extract pass that follows is the real filter.
"""
import json
import os
import re
import sys
from urllib.parse import urlparse

from .. import tank
from ..db import Base, SessionLocal, engine
from ..models import AggregatedListing, DirectorySeller
from ..services.aggregator import _REGION_BY_COUNTRY, _norm_site

# Infrastructure, social, platforms and other non-operations. A domain here is
# never a breeder's own site, however often it is linked.
_BLOCK_SUFFIX = (
    "facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com", "youtu.be",
    "linkedin.com", "pinterest.com", "tiktok.com", "vimeo.com", "whatsapp.com",
    "google.com", "goo.gl", "gstatic.com", "googleapis.com", "maps.app.goo.gl",
    "wordpress.com", "wordpress.org", "wix.com", "squarespace.com", "shopify.com",
    "godaddy.com", "cloudflare.com", "gravatar.com", "w3.org", "schema.org",
    "apple.com", "microsoft.com", "adobe.com", "paypal.com", "stripe.com",
    "mailchimp.com", "constantcontact.com", "eventbrite.com", "gofundme.com",
    "amazon.com", "ebay.com", "etsy.com", "craigslist.org", "reddit.com",
    "wikipedia.org", "blogspot.com", "medium.com", "substack.com", "issuu.com",
    "weebly.com", "webflow.io", "netlify.app", "pages.dev", "herokuapp.com",
    "bit.ly", "tinyurl.com", "linktr.ee", "calendly.com", "zoom.us",
)
_BLOCK_TLD = (".gov", ".mil", ".edu")


def _blocked(site: str) -> bool:
    if any(site == d or site.endswith("." + d) for d in _BLOCK_SUFFIX):
        return True
    if any(site.endswith(t) for t in _BLOCK_TLD):
        return True
    return False


def _terms() -> list[str]:
    """Breed words for this tank — same source the crawler uses for TANK_TERMS."""
    words: set[str] = set()
    raw = os.getenv("TANK_TERMS") or ""
    for w in raw.split("|"):
        w = w.strip().lower()
        if w:
            words.add(w)
    if not words:
        b = tank.brand()
        for part in (b.get("breed") or "").replace("&", "/").split("/"):
            part = part.split("(")[0].strip().lower()
            if part:
                words.add(part)
    # Generic livestock-trade words are useful signal in anchor text but far too
    # weak to justify a domain on their own.
    return [w for w in words if len(w) >= 3]


def _relevant(row: dict, terms: list[str]) -> bool:
    site = row["site"]
    domain_word = re.sub(r"[^a-z0-9]", "", site.rsplit(".", 2)[0].lower())
    # Strongest signal: the breed name is in the domain itself (wagyugenes.com).
    if any(re.sub(r"[^a-z0-9]", "", t) in domain_word for t in terms):
        return True
    # Otherwise require the breed word in anchor text AND more than one referrer,
    # so a single stray link can't drag in an unrelated site.
    blob = " ".join(row.get("anchors") or []).lower()
    if any(t in blob for t in terms) and len(row.get("from") or []) >= 2:
        return True
    return False


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m app.jobs.discover_sites <candidates.json>")
        return
    path = sys.argv[1]
    try:
        rows = json.loads(open(path).read())
    except Exception as e:
        print(f"discover: cannot read {path} ({e}) — skipping")
        return

    Base.metadata.create_all(bind=engine)
    terms = _terms()
    if not terms:
        print("discover: no breed terms for this tank — skipping (refusing to add untargeted sites)")
        return

    db = SessionLocal()
    added = promoted = 0
    try:
        known = {s for (s,) in db.query(DirectorySeller.site).all()}
        for row in rows:
            site = _norm_site(row.get("site") or "")
            if not site or site in known or _blocked(site) or not _relevant(row, terms):
                continue
            db.add(DirectorySeller(
                site=site,
                name=site,
                url=f"https://{site}/",
                country=None,
                region=None,
                categories=[],
                breeds=[],
                blurb=None,
                source="discovered",
                # Hidden until it proves itself by yielding listings — a wrong
                # guess never reaches the public Atlas.
                status="hidden",
            ))
            known.add(site)
            added += 1

        # Promote anything previously discovered that has since produced listings.
        producing = {s for (s,) in db.query(AggregatedListing.source_site)
                     .filter(AggregatedListing.status == "active").distinct()}
        for d in db.query(DirectorySeller).filter(
                DirectorySeller.source == "discovered",
                DirectorySeller.status == "hidden").all():
            if d.site in producing:
                d.status = "active"
                promoted += 1
        db.commit()
    finally:
        db.close()
    print(f"Discovery: +{added} candidate sites queued, {promoted} promoted to the Atlas "
          f"(from {len(rows)} off-domain hosts)")


if __name__ == "__main__":
    main()
