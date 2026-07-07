"""Wagyu News aggregator — pulls headlines from Google News RSS by region and
language, and TRANSLATES the Japanese feed to English (the differentiator). Stores
headline + link + our translation; never republishes full articles."""
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import quote
from xml.etree import ElementTree as ET

import httpx

from ..models import NewsArticle
from .ai import chat

UA = "WagyuTankBot/1.0 (+https://www.wagyutank.com/news; news aggregator)"

# region, query, hl (ui lang), gl (country), lang (original content language).
# English feeds cost nothing (no translation); non-English are throttle-translated.
FEEDS = [
    # --- English (free, wide net) ---
    {"region": "US", "q": "wagyu OR akaushi", "hl": "en-US", "gl": "US", "lang": "en"},
    {"region": "US", "q": "\"wagyu auction\" OR \"wagyu sale\" OR \"wagyu record\"", "hl": "en-US", "gl": "US", "lang": "en"},
    {"region": "US", "q": "\"kobe beef\" OR \"japanese wagyu\" OR akaushi", "hl": "en-US", "gl": "US", "lang": "en"},
    {"region": "AU", "q": "wagyu", "hl": "en-AU", "gl": "AU", "lang": "en"},
    {"region": "AU", "q": "\"wagyu sale\" OR \"wagyu bull sale\" OR \"elite wagyu\"", "hl": "en-AU", "gl": "AU", "lang": "en"},
    {"region": "AU", "q": "wagyu", "hl": "en-NZ", "gl": "NZ", "lang": "en"},
    {"region": "EU", "q": "wagyu", "hl": "en-GB", "gl": "GB", "lang": "en"},
    {"region": "EU", "q": "wagyu", "hl": "en-IE", "gl": "IE", "lang": "en"},
    {"region": "US", "q": "wagyu", "hl": "en-CA", "gl": "CA", "lang": "en"},
    {"region": "AS", "q": "wagyu", "hl": "en-IN", "gl": "IN", "lang": "en"},
    {"region": "US", "q": "\"matsusaka beef\" OR \"wagyu export\" OR \"wagyu genetics\"", "hl": "en-US", "gl": "US", "lang": "en"},
    # --- Japan (translated) ---
    {"region": "JP", "q": "和牛 OR 但馬牛 OR 神戸牛", "hl": "ja", "gl": "JP", "lang": "ja"},
    {"region": "JP", "q": "和牛 競り OR 子牛 価格 OR 和牛 セリ", "hl": "ja", "gl": "JP", "lang": "ja"},
    # --- Asia (translated) ---
    {"region": "AS", "q": "和牛 OR 日本牛肉", "hl": "zh-CN", "gl": "CN", "lang": "zh"},
    {"region": "AS", "q": "와규", "hl": "ko", "gl": "KR", "lang": "ko"},
    # --- Europe (translated) ---
    {"region": "EU", "q": "wagyu", "hl": "de", "gl": "DE", "lang": "de"},
    {"region": "EU", "q": "wagyu", "hl": "fr", "gl": "FR", "lang": "fr"},
    {"region": "EU", "q": "wagyu", "hl": "es", "gl": "ES", "lang": "es"},
    # --- South America (translated) ---
    {"region": "SA", "q": "wagyu", "hl": "pt-BR", "gl": "BR", "lang": "pt"},
    {"region": "SA", "q": "wagyu", "hl": "es-419", "gl": "AR", "lang": "es"},
]

# Bing News RSS — a second engine for extra coverage (English, free).
BING_QUERIES = [
    {"region": "US", "q": "wagyu genetics"}, {"region": "US", "q": "wagyu auction sale"},
    {"region": "AU", "q": "wagyu australia sale"}, {"region": "US", "q": "akaushi cattle"},
]


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _rss_url(f: dict) -> str:
    return (f"https://news.google.com/rss/search?q={quote(f['q'])}"
            f"&hl={f['hl']}&gl={f['gl']}&ceid={f['gl']}:{f['lang']}")


def _parse_pubdate(s: str | None):
    if not s:
        return None
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


_LAST_TR = [0.0]        # translation throttle (free LLM lane rate-limits)
_TR_GAP = 4.0           # min seconds between translation calls
_TR_BUDGET = [40]       # max translations per run (spike control; cache does the rest)


def _translate(title: str, lang: str) -> str | None:
    if _TR_BUDGET[0] <= 0:
        return None  # out of budget this run; picked up next run as cache fills
    names = {"ja": "Japanese", "pt": "Portuguese", "es": "Spanish", "de": "German",
             "zh": "Chinese", "ko": "Korean", "fr": "French"}
    src = names.get(lang, lang)
    import time as _t
    gap = _TR_GAP - (_t.monotonic() - _LAST_TR[0])
    if gap > 0:
        _t.sleep(gap)
    try:
        out = chat(f"You translate {src} news headlines about Wagyu/beef cattle into natural, "
                   f"concise English. Return ONLY the English translation, no quotes, no notes.",
                   title, max_tokens=120)
    except Exception:
        _LAST_TR[0] = _t.monotonic()
        return None
    _LAST_TR[0] = _t.monotonic()
    _TR_BUDGET[0] -= 1
    return (out or "").strip().strip('"') or None


def _fetch_bing(bq: dict, limit: int = 8) -> list[dict]:
    """Bing News RSS — a second English engine for extra coverage."""
    try:
        r = httpx.get("https://www.bing.com/news/search", params={"q": bq["q"], "format": "RSS"},
                      headers={"User-Agent": UA}, timeout=20, follow_redirects=True)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception:
        return []
    out = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        out.append({"region": bq["region"], "lang": "en", "source_name": "Bing News",
                    "source_url": link, "published_at": _parse_pubdate(item.findtext("pubDate")),
                    "title": title, "is_translated": False})
        if len(out) >= limit:
            break
    return out


def _upsert(db, item: dict) -> bool:
    key = hashlib.sha1(item["source_url"].encode()).hexdigest()[:40]
    if db.query(NewsArticle).filter(NewsArticle.dedup_key == key).first():
        return False
    db.add(NewsArticle(
        dedup_key=key, title=item["title"][:400], original_title=item.get("original_title"),
        summary=item.get("summary"), source_name=item["source_name"][:120],
        source_url=item["source_url"], region=item["region"], language=item["lang"],
        is_translated=item.get("is_translated", False),
        published_at=item.get("published_at"), first_seen_at=_now(), status="active",
    ))
    return True


def _fetch_feed(f: dict, limit: int = 12) -> list[dict]:
    try:
        r = httpx.get(_rss_url(f), headers={"User-Agent": UA}, timeout=25, follow_redirects=True)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
    except Exception:
        return []
    out = []
    for item in root.iter("item"):
        title_raw = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title_raw or not link:
            continue
        src_el = item.find("source")
        source_name = (src_el.text if src_el is not None and src_el.text else "Google News").strip()
        # Google News titles end with " - Publisher"; trim it
        title = re.sub(r"\s+-\s+" + re.escape(source_name) + r"\s*$", "", title_raw).strip()
        rec = {"region": f["region"], "lang": f["lang"], "source_name": source_name,
               "source_url": link, "published_at": _parse_pubdate(item.findtext("pubDate")),
               "title": title, "is_translated": False}
        if f["lang"] != "en":
            rec["original_title"] = title
            translated = _translate(title, f["lang"])
            if not translated:
                continue  # skip untranslatable items rather than show foreign text
            rec["title"] = translated
            rec["is_translated"] = True
        out.append(rec)
        if len(out) >= limit:
            break
    return out


def run(db) -> dict:
    _TR_BUDGET[0] = 40  # reset per-run translation spike budget
    added = seen = 0
    for f in FEEDS:
        for item in _fetch_feed(f):
            seen += 1
            if _upsert(db, item):
                added += 1
        db.commit()
    for bq in BING_QUERIES:
        for item in _fetch_bing(bq):
            seen += 1
            if _upsert(db, item):
                added += 1
        db.commit()
    # keep a deep archive so trending-by-year works over time (retain newest 2000)
    ids = [r[0] for r in db.query(NewsArticle.id).order_by(NewsArticle.first_seen_at.desc())
           .offset(2000).all()]
    if ids:
        db.query(NewsArticle).filter(NewsArticle.id.in_(ids)).update(
            {NewsArticle.status: "archived"}, synchronize_session=False)
        db.commit()
    return {"feeds": len(FEEDS), "seen": seen, "added": added}


HIGHLIGHTS_SYS = (
    "You are the editor of a global Wagyu news brief. From the list of recent Wagyu "
    "headlines, write 4-6 punchy bullet points summarizing the biggest themes and stories "
    "in world Wagyu right now — prices, records, exports, Japan, breeding, market trends. "
    "Each bullet one sentence, factual, no hype, no preamble. Return ONLY the bullets, one "
    "per line, each starting with '- '."
)


def generate_highlights(db) -> list[str]:
    """LLM synthesis of the current top news into bullet highlights (cached in Settings)."""
    rows = (db.query(NewsArticle).filter(NewsArticle.status == "active")
            .order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.first_seen_at.desc())
            .limit(25).all())
    if not rows:
        return []
    headlines = "\n".join(f"[{a.region}] {a.title}" for a in rows)
    try:
        out = chat(HIGHLIGHTS_SYS, headlines, max_tokens=400)
    except Exception:
        out = None
    if not out:
        return []
    bullets = [ln.lstrip("-• ").strip() for ln in out.splitlines() if ln.strip().lstrip("-• ")]
    bullets = [b for b in bullets if len(b) > 15][:6]
    if bullets:
        from . import settings_store
        settings_store.set("news_highlights", {"bullets": bullets, "generated": _now().isoformat()})
    return bullets
