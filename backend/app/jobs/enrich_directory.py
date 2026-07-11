"""Enrich Atlas registry entries from each seller's own public homepage.

  python -m app.jobs.enrich_directory [--limit N] [--refresh]

For every un-enriched DirectorySeller: fetch the homepage (static, polite),
LLM-classify what the operation does (genetics / live cattle / beef / feedlot /
stud services), its breed focus (Black Wagyu / Akaushi), a proper display name,
and a one-line ORIGINAL blurb. Sites that won't fetch (JS-only, bot-blocked)
still keep their name/country/website tile — enrichment is additive, never a
gate. Idempotent; re-run any time (--refresh re-does everything)."""
import json
import re
import sys
import time
from datetime import datetime, timezone

import httpx

from ..db import SessionLocal
from ..models import DirectorySeller
from ..services.ai import chat

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_CATS = {"genetics", "live_cattle", "beef", "feedlot", "stud_services"}
_BREEDS = {"black_wagyu", "akaushi"}

_SYSTEM = (
    "You classify a cattle-operation website from its homepage text. Reply with ONLY a "
    "JSON object: {\"name\": display name of the operation (from the page, not the domain; "
    "keep original language), \"categories\": subset of "
    "[\"genetics\",\"live_cattle\",\"beef\",\"feedlot\",\"stud_services\"] "
    "(genetics = sells semen/embryos/breeding genetics; live_cattle = sells breeding "
    "stock/bulls/heifers; beef = sells meat; feedlot = feeding/finishing operation; "
    "stud_services = AI/collection/repro services), \"breeds\": subset of "
    "[\"black_wagyu\",\"akaushi\"] they work with, \"blurb\": ONE original English sentence "
    "(max 140 chars) describing the operation - your own words, never copied text}."
)


def _fetch(url: str) -> str | None:
    try:
        with httpx.Client(follow_redirects=True, timeout=15,
                          headers={"User-Agent": _UA, "Accept-Language": "en;q=0.8,*;q=0.5"}) as c:
            r = c.get(url)
        if r.status_code >= 400 or not r.text:
            return None
        text = re.sub(r"<script[^>]*>.*?</script>|<style[^>]*>.*?</style>", " ",
                      r.text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:6000] if len(text) > 120 else None
    except Exception:
        return None


def _classify(site: str, text: str) -> dict | None:
    try:
        out = chat(_SYSTEM, f"Website: {site}\n\nHomepage text:\n{text}", max_tokens=300)
        m = re.search(r"\{.*\}", out or "", re.S)
        if not m:
            return None
        d = json.loads(m.group(0))
        cats = [c for c in (d.get("categories") or []) if c in _CATS]
        breeds = [b for b in (d.get("breeds") or []) if b in _BREEDS]
        name = (d.get("name") or "").strip()[:160]
        blurb = (d.get("blurb") or "").strip()[:300]
        return {"name": name, "categories": cats, "breeds": breeds, "blurb": blurb}
    except Exception:
        return None


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    refresh = "--refresh" in sys.argv
    db = SessionLocal()
    try:
        q = db.query(DirectorySeller).filter(DirectorySeller.status == "active")
        if not refresh:
            q = q.filter(DirectorySeller.enriched_at == None)  # noqa: E711
        rows = q.all()
        if limit:
            rows = rows[:limit]
        print(f"Enriching {len(rows)} Atlas entries…")
        done = ok = 0
        now = lambda: datetime.now(timezone.utc).replace(tzinfo=None)  # noqa: E731
        for r in rows:
            text = _fetch(r.url)
            if text:
                d = _classify(r.site, text)
                if d:
                    if d["name"]:
                        r.name = d["name"]
                    r.categories = d["categories"]
                    r.breeds = d["breeds"]
                    r.blurb = d["blurb"] or None
                    ok += 1
                time.sleep(2.5)  # politeness + free-LLM-lane throttle
            # mark attempted either way, so re-runs don't hammer dead sites;
            # --refresh clears the slate when we want another pass.
            r.enriched_at = now()
            done += 1
            if done % 25 == 0:
                db.commit()
                print(f"  {done}/{len(rows)} (enriched {ok})")
        db.commit()
        print(f"Done: {done} processed, {ok} enriched from homepage, "
              f"{done - ok} kept as name+country+link tiles.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
