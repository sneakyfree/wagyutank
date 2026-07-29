"""Read the source page to work out where a listing's seller actually is.

  python -m app.jobs.resolve_countries [--limit 20] [--all] [--dry]

Country is inferred at crawl time from what the extractor happened to state, then
from the domain's TLD, then a generic .com→US guess. When all three miss, the
listing had no country at all — and before the ISO validation landed, an
extractor answering "UN" for *unknown* was being rendered as the United Nations,
flag and all.

IP geolocation is deliberately NOT used. It resolves the HOST, not the business:
a Queensland stud behind Cloudflare geolocates to wherever the edge node is, and
half the web sits in us-east-1. It would be confidently wrong.

The page itself is a far better witness, and usually says so plainly:

  - Directory pages group listings under COUNTRY HEADINGS. That is exactly the
    case here — wagyuinternational.co/genetics.php lists animals beneath
    "Australia", "Canada" and so on, and our per-listing extraction simply lost
    the heading above each row.
  - Postal addresses, phone country codes (+61, +49, +1), currency (A$, €, £),
    state and province names, "ships from", ABN/VAT/company numbers.

Aggregator pages are the reason this is per-LISTING and not per-SITE: a directory
in one country lists breeders in a dozen others, so the seller's country and the
site's country are different questions.
"""
import argparse
import json
import re
from collections import defaultdict

import httpx

from ..db import SessionLocal
from ..models import AggregatedListing
from ..services import translate as T
from ..services.ai import chat
from ..services.aggregator import _ISO_A2, _REGION_BY_COUNTRY, USER_AGENT

_TAGS = re.compile(r"<script.*?</script>|<style.*?</style>", re.S | re.I)
_BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _page_text(url: str) -> str | None:
    for ua in (USER_AGENT(), _BROWSER_UA):
        try:
            r = httpx.get(url, headers={"User-Agent": ua}, timeout=25, follow_redirects=True)
            if r.status_code != 200:
                continue
            body = _TAGS.sub(" ", r.text)
            body = re.sub(r"<[^>]+>", "\n", body)
            body = re.sub(r"[ \t]+", " ", body)
            body = "\n".join(l.strip() for l in body.split("\n") if l.strip())
            if len(body) > 200:
                return body[:14000]
        except Exception:
            continue
    return None


_SYS = (
    "You are told the text of a web page that offers cattle genetics for sale, and "
    "a list of listing titles taken from it. For EACH title, say which country the "
    "SELLER of that listing is in.\n"
    "The seller's country is not necessarily the site's country: directory pages "
    "group breeders from many countries on one page, usually under COUNTRY HEADINGS "
    "— when a listing sits beneath such a heading, that heading is the answer.\n"
    "Other evidence, in rough order of reliability: a postal address, a phone "
    "country code (+61 Australia, +49 Germany, +1 US/Canada), a state or province "
    "name, currency (A$, €, £, US$), an ABN/VAT/company number, 'ships from'.\n"
    "Answer with ISO 3166-1 alpha-2 codes (AU, DE, US, CA…). Use null when the page "
    "genuinely does not say — a wrong country is far worse than an honest blank. "
    "Never guess from the domain name alone.\n"
    'Return ONLY a JSON object mapping each title verbatim to a code or null.'
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=20, help="source pages per run")
    ap.add_argument("--all", action="store_true", help="also re-check listings that HAVE a country")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        q = db.query(AggregatedListing).filter(AggregatedListing.status == "active")
        if not args.all:
            q = q.filter(AggregatedListing.country.is_(None))
        rows = q.all()
        by_url: dict[str, list] = defaultdict(list)
        for r in rows:
            if r.source_url:
                by_url[r.source_url].append(r)
        pages = list(by_url.items())[: args.limit]
        print(f"  {len(rows)} listings without a country, across {len(by_url)} pages "
              f"— reading {len(pages)}")

        model, provider = T._model(T.BULK), T._provider_for(T.BULK)
        fixed = blank = 0
        for url, listings in pages:
            text = _page_text(url)
            if not text:
                print(f"    {url[:64]} — unreachable, skipped")
                continue
            titles = [l.title for l in listings][:40]
            body = (f"PAGE URL: {url}\n\nPAGE TEXT:\n{text}\n\n"
                    f"LISTING TITLES:\n" + "\n".join(f"- {t}" for t in titles))
            raw = chat(_SYS, body, max_tokens=1600, model=model, provider=provider)
            if not raw:
                print(f"    {url[:64]} — no answer, skipped")
                continue
            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
            try:
                got = json.loads(raw)
            except Exception:
                print(f"    {url[:64]} — unparseable reply, skipped")
                continue
            for l in listings:
                code = (got.get(l.title) or "").strip().upper()[:2] if isinstance(got.get(l.title), str) else ""
                if code and code in _ISO_A2:
                    l.country = code
                    l.region = _REGION_BY_COUNTRY.get(code)
                    fixed += 1
                else:
                    blank += 1
            print(f"    {url[:58]} — resolved {sum(1 for l in listings if l.country)}/{len(listings)}")
        if args.dry:
            db.rollback()
            print(f"  DRY — would set {fixed}, leave {blank} blank")
        else:
            db.commit()
            print(f"  resolved {fixed}, left {blank} honestly blank")
    finally:
        db.close()


if __name__ == "__main__":
    main()
