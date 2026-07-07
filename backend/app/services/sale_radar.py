"""Sale radar — scans the news feed for Wagyu auction-RESULT articles and
auto-extracts sale-event data, so the forensic sales database grows on its own.

Conservative + honest: only fires on headlines that clearly report a sale result
with a price; every auto-added event links to the real news article and is flagged
as auto-detected (verify against source). Dedups against known sales."""
import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

from ..models import NewsArticle, SaleEvent
from .ai import chat

# headline must mention an auction AND a result/price to be a candidate
_AUCTION = re.compile(r"\b(sale|auction|sells?|sold|tops?|topped|averaged?|gross(?:ed)?|record|fetch)", re.I)
_PRICE = re.compile(r"[\$£¥€]|\bmillion\b|\b\d{1,3}[,\d]{3,}\b|\bcwt\b", re.I)

_SYS = (
    "Extract structured data about a WAGYU CATTLE/GENETICS AUCTION SALE from a news headline. "
    "Return ONLY JSON: {is_sale_result: bool, sale_name, year (int), country (ISO-2), "
    "currency (AUD/USD/JPY/EUR/GBP/BRL), top_price (number), top_price_item}. "
    "is_sale_result is true ONLY if the headline reports the OUTCOME of a specific auction "
    "(a price achieved, gross, or average) — not a preview, a beef/restaurant story, or general news. "
    "Use null for anything not stated. Never invent numbers."
)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _continent(country: str | None) -> str | None:
    return {"AU": "OC", "NZ": "OC", "US": "NA", "CA": "NA", "GB": "EU", "DE": "EU",
            "FR": "EU", "BR": "SA", "AR": "SA", "JP": "AS", "CN": "AS"}.get((country or "").upper())


def scan(db) -> dict:
    """Scan recent news for auction results; auto-add high-confidence sale events."""
    since = _now() - timedelta(days=3)
    articles = (db.query(NewsArticle)
                .filter(NewsArticle.status == "active", NewsArticle.first_seen_at >= since)
                .all())
    candidates = [a for a in articles if _AUCTION.search(a.title or "") and _PRICE.search(a.title or "")]
    added = checked = 0
    for a in candidates[:20]:  # cap LLM calls per run
        checked += 1
        try:
            out = chat(_SYS, a.title, max_tokens=200)
        except Exception:
            continue
        if not out:
            continue
        m = re.search(r"\{.*\}", out, re.DOTALL)
        if not m:
            continue
        try:
            d = json.loads(m.group(0))
        except Exception:
            continue
        if not d.get("is_sale_result") or not d.get("sale_name") or not d.get("top_price"):
            continue
        year = d.get("year") or (a.published_at.year if a.published_at else None)
        key = hashlib.sha1(f"{d['sale_name']}|{year}".encode()).hexdigest()[:24]
        if db.query(SaleEvent).filter(SaleEvent.dedup_key == key).first():
            continue  # already known
        country = (d.get("country") or a.region or "")[:2].upper() or None
        db.add(SaleEvent(
            dedup_key=key, sale_name=str(d["sale_name"])[:200], year=year,
            date=(a.published_at.strftime("%Y-%m-%d") if a.published_at else None),
            country=country, continent=_continent(country),
            currency=(d.get("currency") or "USD")[:4],
            top_price=d.get("top_price"), top_price_item=d.get("top_price_item"),
            source_url=a.source_url, source_name=(a.source_name or "news"),
            notes="Auto-detected from news coverage — figures from the headline; verify against source.",
        ))
        added += 1
    if added:
        db.commit()
    return {"candidates": len(candidates), "checked": checked, "added": added}
