"""Assembles the weekly "Wagyu Wire" digest email from live site data — the
retention loop that pulls people back into the marketplace."""
from ..models import Listing, ListingStatus, MarketQuote, NewsArticle, NotableSale
from . import price_index

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
    rows = (db.query(Listing).filter(Listing.status == ListingStatus.ACTIVE)
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


def build_body(db) -> str:
    intro = ("<p style='font-size:15px;color:#444'>Your weekly window into the world of Wagyu — "
             "the news, the market, and the genetics moving right now.</p>")
    return intro + _news(db) + _market(db) + _listings(db) + _record(db)
