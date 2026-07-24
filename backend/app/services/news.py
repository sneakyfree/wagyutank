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
# English geo-feeds cost nothing (no translation); non-English are throttle-translated.
# Regions: US=N.America SA=S.America EU=Europe AS=Asia JP=Japan AU=Oceania ME=MiddleEast AF=Africa
def _feeds() -> list[dict]:
    """WagyuTank uses its curated 38-feed set. Any other tank builds Google-News
    feeds from its config's news_search_terms across the key cattle regions — so a
    Murray Grey tank pulls Murray Grey news (heartland Australia first), and the
    on-read translation makes those Australian stories readable worldwide."""
    from .. import tank
    if tank.key() == "wagyu":
        return FEEDS
    terms = tank.vocab().get("news_search_terms") or [tank.brand().get("breed", "cattle")]
    q = " OR ".join(f'"{t}"' for t in terms)
    regions = [("AU", "en-AU", "AU", "en"), ("US", "en-US", "US", "en"),
               ("AU", "en-NZ", "NZ", "en"), ("EU", "en-GB", "GB", "en"),
               ("US", "en-CA", "CA", "en")]
    feeds, seen = [], set()
    for region, hl, gl, lang in regions:
        if gl in seen:
            continue
        seen.add(gl)
        feeds.append({"region": region, "q": q, "hl": hl, "gl": gl, "lang": lang})
    return feeds


FEEDS = [
    # --- North America (English, free) ---
    {"region": "US", "q": "wagyu OR akaushi", "hl": "en-US", "gl": "US", "lang": "en"},
    {"region": "US", "q": "\"wagyu auction\" OR \"wagyu sale\" OR \"wagyu record\"", "hl": "en-US", "gl": "US", "lang": "en"},
    {"region": "US", "q": "\"kobe beef\" OR \"japanese wagyu\" OR akaushi", "hl": "en-US", "gl": "US", "lang": "en"},
    {"region": "US", "q": "\"matsusaka beef\" OR \"wagyu export\" OR \"wagyu genetics\"", "hl": "en-US", "gl": "US", "lang": "en"},
    {"region": "US", "q": "wagyu", "hl": "en-CA", "gl": "CA", "lang": "en"},
    {"region": "US", "q": "wagyu OR \"carne wagyu\"", "hl": "es-419", "gl": "MX", "lang": "es"},
    # --- Oceania (English, free) ---
    {"region": "AU", "q": "wagyu", "hl": "en-AU", "gl": "AU", "lang": "en"},
    {"region": "AU", "q": "\"wagyu sale\" OR \"wagyu bull sale\" OR \"elite wagyu\"", "hl": "en-AU", "gl": "AU", "lang": "en"},
    {"region": "AU", "q": "wagyu", "hl": "en-NZ", "gl": "NZ", "lang": "en"},
    # --- Europe: English (free) + local (translated) ---
    {"region": "EU", "q": "wagyu", "hl": "en-GB", "gl": "GB", "lang": "en"},
    {"region": "EU", "q": "wagyu", "hl": "en-IE", "gl": "IE", "lang": "en"},
    {"region": "EU", "q": "wagyu", "hl": "de", "gl": "DE", "lang": "de"},
    {"region": "EU", "q": "wagyu", "hl": "fr", "gl": "FR", "lang": "fr"},
    {"region": "EU", "q": "wagyu", "hl": "es", "gl": "ES", "lang": "es"},
    {"region": "EU", "q": "wagyu", "hl": "it", "gl": "IT", "lang": "it"},
    {"region": "EU", "q": "wagyu", "hl": "nl", "gl": "NL", "lang": "nl"},
    # --- Japan (translated — the moat) ---
    {"region": "JP", "q": "和牛 OR 但馬牛 OR 神戸牛", "hl": "ja", "gl": "JP", "lang": "ja"},
    {"region": "JP", "q": "和牛 競り OR 子牛 価格 OR 和牛 セリ", "hl": "ja", "gl": "JP", "lang": "ja"},
    # --- Asia: local (translated) + English (free) ---
    {"region": "AS", "q": "和牛 OR 日本牛肉", "hl": "zh-CN", "gl": "CN", "lang": "zh"},
    {"region": "AS", "q": "和牛", "hl": "zh-TW", "gl": "TW", "lang": "zh"},
    {"region": "AS", "q": "와규", "hl": "ko", "gl": "KR", "lang": "ko"},
    {"region": "AS", "q": "wagyu", "hl": "en-IN", "gl": "IN", "lang": "en"},
    {"region": "AS", "q": "wagyu", "hl": "en-SG", "gl": "SG", "lang": "en"},
    {"region": "AS", "q": "wagyu", "hl": "en-PH", "gl": "PH", "lang": "en"},
    {"region": "AS", "q": "wagyu", "hl": "en-MY", "gl": "MY", "lang": "en"},
    {"region": "AS", "q": "wagyu", "hl": "en-HK", "gl": "HK", "lang": "en"},
    {"region": "AS", "q": "วากิว OR wagyu", "hl": "th", "gl": "TH", "lang": "th"},
    {"region": "AS", "q": "wagyu OR daging wagyu", "hl": "id", "gl": "ID", "lang": "id"},
    {"region": "AS", "q": "wagyu OR thịt bò wagyu", "hl": "vi", "gl": "VN", "lang": "vi"},
    # --- Middle East (English, free — big luxury market) ---
    {"region": "ME", "q": "wagyu", "hl": "en", "gl": "AE", "lang": "en"},
    {"region": "ME", "q": "wagyu", "hl": "en", "gl": "SA", "lang": "en"},
    {"region": "ME", "q": "wagyu", "hl": "en", "gl": "QA", "lang": "en"},
    # --- Africa (English, free — real production) ---
    {"region": "AF", "q": "wagyu", "hl": "en", "gl": "ZA", "lang": "en"},
    # --- South America (translated) ---
    {"region": "SA", "q": "wagyu", "hl": "pt-BR", "gl": "BR", "lang": "pt"},
    {"region": "SA", "q": "wagyu", "hl": "es-419", "gl": "AR", "lang": "es"},
    {"region": "SA", "q": "wagyu", "hl": "es-419", "gl": "CL", "lang": "es"},
    {"region": "SA", "q": "wagyu", "hl": "es-419", "gl": "CO", "lang": "es"},
    {"region": "SA", "q": "wagyu", "hl": "es-419", "gl": "UY", "lang": "es"},
]

# Bing News RSS — a second engine (English, free).
BING_QUERIES = [
    {"region": "US", "q": "wagyu genetics"}, {"region": "US", "q": "wagyu auction sale"},
    {"region": "AU", "q": "wagyu australia sale"}, {"region": "US", "q": "akaushi cattle"},
    {"region": "AS", "q": "wagyu japan"}, {"region": "EU", "q": "wagyu europe"},
]

# GDELT — the global news firehose (100+ languages, catches outlets RSS misses).
GDELT_QUERIES = ["wagyu", "akaushi", "\"kobe beef\""]
_GDELT_REGION = {
    "United States": "US", "Canada": "US", "Mexico": "US",
    "Australia": "AU", "New Zealand": "AU",
    "Japan": "JP",
    "China": "AS", "Taiwan": "AS", "South Korea": "AS", "Korea": "AS", "India": "AS",
    "Singapore": "AS", "Hong Kong": "AS", "Philippines": "AS", "Malaysia": "AS",
    "Thailand": "AS", "Indonesia": "AS", "Vietnam": "AS",
    "United Kingdom": "EU", "Ireland": "EU", "Germany": "EU", "France": "EU", "Spain": "EU",
    "Italy": "EU", "Netherlands": "EU", "Belgium": "EU", "Austria": "EU", "Switzerland": "EU",
    "Denmark": "EU", "Sweden": "EU", "Portugal": "EU", "Poland": "EU",
    "United Arab Emirates": "ME", "Saudi Arabia": "ME", "Qatar": "ME", "Kuwait": "ME", "Bahrain": "ME",
    "South Africa": "AF", "Nigeria": "AF", "Kenya": "AF",
    "Brazil": "SA", "Argentina": "SA", "Chile": "SA", "Colombia": "SA", "Uruguay": "SA", "Peru": "SA",
}


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
        out = chat(f"You translate {src} news headlines about beef cattle into natural, "
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


# Wagyu-domain relevance gate — keep the feed on-topic. A headline must touch
# the breed/beef/genetics world; this rejects the celebrity/sports noise that
# generic queries and the GDELT firehose drag in.
_RELEVANT = (
    "wagyu", "waygu", "akaushi", "kobe beef", "kobe-beef", "matsusaka", "miyazaki",
    "olive wagyu", "japanese black", "japanese beef", "fullblood", "full blood",
    "cattle", "beef", "cow", "bull", "heifer", "steer", "calf", "calv", "herd",
    "semen", "embryo", "genetic", "bloodline", "sire", "marbl", "carcase", "carcass",
    "ranch", "feedlot", "livestock", "brahman", "angus", "cross-bred", "seedstock",
    "和牛", "但馬", "神戸", "松阪", "黒毛",
)
# Obvious off-topic markers that occasionally co-occur with "wagyu" (a restaurant
# review that's really about a celebrity/sports event) — reject when present and
# no strong cattle keyword is.
_OFFTOPIC = ("bieber", "super bowl", "halftime", "fifa", "world cup final",
             "taylor swift", "kardashian", "grammy", "oscars", "box office")


def _relevant(item: dict) -> bool:
    hay = f"{item.get('title','')} {item.get('original_title','') or ''} {item.get('summary','') or ''}".lower()
    from .. import tank as _tk
    breed_terms = tuple(t.lower() for t in (_tk.vocab().get("news_search_terms") or []))
    if not any(k in hay for k in _RELEVANT) and not any(k in hay for k in breed_terms):
        return False
    if any(k in hay for k in _OFFTOPIC) and not any(
            k in hay for k in ("cattle", "beef cattle", "wagyu beef", "genetic", "semen", "embryo", "ranch", "herd")):
        return False
    return True


def _title_key(title: str) -> str:
    """Normalized headline fingerprint for cross-source duplicate detection."""
    t = re.sub(r"[^a-z0-9 ]", "", (title or "").lower())
    t = re.sub(r"\s+", " ", t).strip()
    return t[:70]


def _upsert(db, item: dict) -> bool:
    if not _relevant(item):
        return False
    key = hashlib.sha1(item["source_url"].encode()).hexdigest()[:40]
    if db.query(NewsArticle).filter(NewsArticle.dedup_key == key).first():
        return False
    # Cross-source dedup: same story, different URL/publisher. Compare the
    # normalized title against recently-seen active articles.
    tk = _title_key(item.get("original_title") or item["title"])
    if tk and len(tk) > 12:
        recent = (db.query(NewsArticle.title, NewsArticle.original_title)
                  .filter(NewsArticle.status == "active")
                  .order_by(NewsArticle.first_seen_at.desc()).limit(400).all())
        for (t, ot) in recent:
            if _title_key(ot or t) == tk:
                return False
    from .news_geo import classify_country, region_for_country
    country = classify_country(item["source_name"], item.get("lang"), item.get("region"), item.get("gl"))
    region = region_for_country(country) or item["region"]
    db.add(NewsArticle(
        dedup_key=key, title=item["title"][:400], original_title=item.get("original_title"),
        summary=item.get("summary"), source_name=item["source_name"][:120],
        source_url=item["source_url"], region=region, country=country, language=item["lang"],
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
               "title": title, "is_translated": False, "gl": f.get("gl")}
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


def _parse_gdelt_date(s: str | None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ")
    except Exception:
        return None


def _fetch_gdelt(query: str, limit: int = 60) -> list[dict]:
    """GDELT Doc 2.0 — global news across 100+ languages. English-language results
    only (RSS already covers translated non-English markets); maps source country
    to region. Defensive: GDELT rate-limits and occasionally returns empty."""
    import json as _json
    try:
        r = httpx.get("https://api.gdeltproject.org/api/v2/doc/doc",
                      params={"query": query, "mode": "artlist", "format": "json",
                              "maxrecords": limit, "timespan": "3d", "sort": "datedesc"},
                      headers={"User-Agent": "Mozilla/5.0 (WagyuTankBot)"}, timeout=25)
        if r.status_code != 200 or not r.text.strip().startswith("{"):
            return []
        arts = _json.loads(r.text).get("articles", [])
    except Exception:
        return []
    out = []
    for a in arts:
        if (a.get("language") or "").lower() != "english":
            continue  # keep GDELT clean/free; RSS handles translated markets
        title, url = (a.get("title") or "").strip(), (a.get("url") or "").strip()
        if not title or not url:
            continue
        region = _GDELT_REGION.get(a.get("sourcecountry", ""), None)
        out.append({"region": region or "US", "lang": "en",
                    "source_name": (a.get("domain") or "GDELT")[:120], "source_url": url,
                    "published_at": _parse_gdelt_date(a.get("seendate")),
                    "title": title, "is_translated": False})
    return out


def run(db) -> dict:
    import time as _t
    from . import health
    _TR_BUDGET[0] = 60  # reset per-run translation spike budget
    added = seen = 0
    for f in _feeds():
        fa = 0
        for item in _fetch_feed(f):
            seen += 1
            if _upsert(db, item):
                added += 1; fa += 1
        health.record_source(db, f"news:g:{f['gl']}:{f['lang']}:{f['q'][:16]}", "news_feed",
                             f"Google News {f['gl']} ({f['lang']}) · {f['region']}", fa)
        db.commit()
        _t.sleep(2.5)  # pace to avoid Google News throttling the server IP
    from .. import tank as _tk
    _wagyu = _tk.key() == "wagyu"
    for bq in (BING_QUERIES if _wagyu else []):
        ba = 0
        for item in _fetch_bing(bq):
            seen += 1
            if _upsert(db, item):
                added += 1; ba += 1
        health.record_source(db, f"news:bing:{bq['q'][:20]}", "engine", f"Bing News · {bq['q']}", ba)
        db.commit()
    for gq in (GDELT_QUERIES if _wagyu else []):
        _t.sleep(6)  # GDELT: one request / 5s
        ga = 0
        for item in _fetch_gdelt(gq):
            seen += 1
            if _upsert(db, item):
                added += 1; ga += 1
        health.record_source(db, f"news:gdelt:{gq}", "engine", f"GDELT firehose · {gq}", ga)
        db.commit()
    # keep a deep archive so trending-by-year works over time (retain newest 2000)
    ids = [r[0] for r in db.query(NewsArticle.id).order_by(NewsArticle.first_seen_at.desc())
           .offset(2000).all()]
    if ids:
        db.query(NewsArticle).filter(NewsArticle.id.in_(ids)).update(
            {NewsArticle.status: "archived"}, synchronize_session=False)
        db.commit()
    return {"feeds": len(_feeds()), "seen": seen, "added": added}


def _highlights_sys() -> str:
    from .. import tank
    breed = (tank.brand().get("breed") or "Wagyu").split(" & ")[0].strip()
    return (
        f"You are the editor of a global {breed} news brief. From the list of recent {breed} "
        "headlines, write 4-6 punchy bullet points summarizing the biggest themes and stories "
        f"in world {breed} right now — prices, records, exports, breeding, market trends. "
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
        out = chat(_highlights_sys(), headlines, max_tokens=400)
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
