"""Assembles the weekly "Wagyu Wire" digest email from live site data — the
retention loop that pulls people back into the marketplace."""
import time
from datetime import timedelta

from ..models import Listing, ListingStatus, MarketQuote, NewsArticle, NotableSale, utcnow
from . import price_index
from .ai import chat

_EDITORIAL_SYS = (
    "You are the editor of The Wagyu Wire, WagyuTank.com's weekly letter to Wagyu "
    "breeders worldwide. Write this week's 'State of the Wagyu' — a short editor's "
    "letter (2-3 paragraphs, 130-200 words total) synthesizing the week from the "
    "data provided. Plain, confident, rancher-to-rancher voice. No hype, no "
    "emojis, no greetings or sign-offs, no headings. CRITICAL: use ONLY facts "
    "present in the data below — never invent numbers, names, or events. If a "
    "theme spans several headlines, call out the trend. Output plain text "
    "paragraphs separated by blank lines."
)

BASE = "https://www.wagyutank.com"
GOLD = "#8a6d2b"


def _money(n):
    try:
        return "$" + f"{float(n):,.0f}"
    except Exception:
        return "—"


def _section(title, inner):
    return (f"<div style='margin:26px 0 0'>"
            f"<div style='font-size:12px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;"
            f"color:{GOLD};margin-bottom:10px'>{title}</div>{inner}</div>")


def _news(db) -> str:
    rows = (db.query(NewsArticle).filter(NewsArticle.status == "active")
            .order_by(NewsArticle.published_at.desc().nullslast(), NewsArticle.first_seen_at.desc())
            .limit(4).all())
    if not rows:
        return ""
    flag = {"US": "🇺🇸", "AU": "🇦🇺", "JP": "🇯🇵", "EU": "🇪🇺", "SA": "🌎"}
    items = "".join(
        f"<div style='margin-bottom:12px'>"
        f"<a href='{BASE}/news/' style='color:#1a1a1a;text-decoration:none;font-weight:600;font-size:15px;line-height:1.4'>{a.title}</a>"
        f"<div style='color:#999;font-size:12px'>{flag.get(a.region,'🌍')} {a.source_name}"
        f"{' · 🌐 translated' if a.is_translated else ''}</div></div>"
        for a in rows)
    return _section("📰 This week in Wagyu", items)


def _market(db) -> str:
    idx = price_index.compute(db)
    m = idx.get("market", {})
    if not m.get("semen_avg"):
        return ""
    cut = (db.query(MarketQuote).filter(MarketQuote.category == "cutout",
           MarketQuote.label.like("Choice%")).first())
    sires = idx.get("sires", [])[:3]
    sire_html = " · ".join(f"<b>{s['sire']}</b> {_money(s['avg'])}" for s in sires)
    inner = (
        f"<div style='background:#faf7f0;border-radius:10px;padding:14px 16px'>"
        f"<div style='font-size:15px'>Wagyu semen index: <b style='color:{GOLD}'>{_money(m['semen_avg'])}/straw</b> "
        f"avg across {m.get('semen_count',0)} listings</div>"
        + (f"<div style='color:#555;font-size:13px;margin-top:6px'>{sire_html}</div>" if sire_html else "")
        + (f"<div style='color:#555;font-size:13px;margin-top:6px'>Choice boxed beef cutout: <b>{_money(cut.value)}/cwt</b></div>" if cut and cut.value else "")
        + f"<a href='{BASE}/market/' style='color:{GOLD};font-size:13px;font-weight:700'>See the data center →</a></div>")
    return _section("📈 Market pulse", inner)


def _listings(db) -> str:
    rows = (db.query(Listing).filter(Listing.status == ListingStatus.ACTIVE,
                                     Listing.is_sample == False)  # noqa: E712
            .order_by(Listing.created_at.desc()).limit(4).all())
    if not rows:
        return ""
    def _row(li):
        price = f" — <span style='color:{GOLD}'>{_money(li.unit_price)}</span>" if li.unit_price else ""
        return (f"<a href='{BASE}/listing/?id={li.id}' style='display:block;color:#1a1a1a;"
                f"text-decoration:none;padding:8px 0;border-bottom:1px solid #eee'>"
                f"<b style='font-size:14px'>{li.title}</b>{price}</a>")
    return _section("🧬 Fresh on the marketplace", "".join(_row(li) for li in rows))


def _record(db) -> str:
    s = (db.query(NotableSale).filter(NotableSale.is_record == True)  # noqa: E712
         .order_by(NotableSale.usd_approx.desc()).first())
    if not s:
        return ""
    sym = {"JPY": "¥", "AUD": "A$"}.get(s.currency, "$")
    price = f"{sym}{s.price/1e6:.0f}M" if s.currency == "JPY" else f"{sym}{s.price:,.0f}"
    inner = (f"<div style='font-size:15px'><b style='color:{GOLD}'>{price}</b> {s.unit or ''} — {s.headline}</div>"
             f"<a href='{BASE}/sales/' style='color:{GOLD};font-size:13px;font-weight:700'>The Hall of Records →</a>")
    return _section("🏆 From the record books", inner)


def _editorial(db) -> str:
    """LLM-written 'State of the Wagyu' editor's letter from the week's data."""
    week_ago = utcnow() - timedelta(days=7)
    arts = (db.query(NewsArticle).filter(NewsArticle.status == "active")
            .order_by(NewsArticle.published_at.desc().nullslast(),
                      NewsArticle.first_seen_at.desc())
            .limit(16).all())
    idx = price_index.compute(db)
    m = idx.get("market", {})
    new_listings = (db.query(Listing)
                    .filter(Listing.status == ListingStatus.ACTIVE,
                            Listing.is_sample == False,  # noqa: E712
                            Listing.created_at >= week_ago).count())
    facts = []
    if arts:
        facts.append("This week's headlines:\n" + "\n".join(
            f"- [{a.region}] {a.title}" for a in arts))
    if m.get("semen_avg"):
        sires = " · ".join(f"{s['sire']} ${s['avg']:,.0f}" for s in idx.get("sires", [])[:4])
        facts.append(f"Wagyu semen index: ${m['semen_avg']:,.0f}/straw average across "
                     f"{m.get('semen_count', 0)} tracked listings. Marquee sires: {sires}")
    cut = (db.query(MarketQuote).filter(MarketQuote.category == "cutout",
           MarketQuote.label.like("Choice%")).first())
    if cut and cut.value:
        facts.append(f"Choice boxed beef cutout: ${cut.value:,.2f}/cwt")
    if new_listings:
        facts.append(f"{new_listings} new listing(s) posted on WagyuTank this week.")
    if not facts:
        return ""
    # The free LLM lane rate-limits under burst (news crawls share it). The
    # digest is a weekly oneshot, so wait out 429s rather than skip the letter.
    letter = None
    for attempt in range(5):
        if attempt:
            time.sleep(45)
        try:
            letter = chat(_EDITORIAL_SYS, "\n\n".join(facts), max_tokens=500)
            break
        except Exception:
            continue
    if not letter or len(letter.strip()) < 80:
        return ""
    paras = "".join(f"<p style='font-size:15px;color:#333;line-height:1.65;margin:0 0 14px'>{p.strip()}</p>"
                    for p in letter.split("\n\n") if p.strip())
    return _section("🖋 The State of the Wagyu", paras)


def build_body(db) -> str:
    intro = ("<p style='font-size:15px;color:#444'>Your weekly window into the world of Wagyu — "
             "the news, the market, and the genetics moving right now.</p>")
    return intro + _editorial(db) + _news(db) + _market(db) + _listings(db) + _record(db)
