"""Seed the Beef Market Data Center with current figures from USDA AMS (public
domain) and published Wagyu benchmarks. Re-runnable — replaces all rows.

  python -m app.jobs.seed_market

When a USDA MARS API key is configured (admin setting `usda_api_key`), a future
live-refresh service will keep the commodity figures current automatically.
"""
from .. import models  # noqa: F401
from ..db import Base, SessionLocal, engine
from ..models import MarketQuote

AMS = "https://www.ams.usda.gov/market-news/livestock-poultry-grain"

QUOTES = [
    # --- Feeder cattle ---
    dict(category="feeder", label="CME Feeder Cattle Index", value=371.25, unit="$/cwt", change=-5.74,
         as_of="2026-07-01", source="CME / USDA AMS", source_url=AMS, sort_order=1,
         note="750–800 lb steers"),
    dict(category="feeder", label="Feeder Cattle — 2026 avg (forecast)", value=364.0, unit="$/cwt",
         as_of="2026 forecast", source="USDA ERS", source_url="https://www.ers.usda.gov/topics/animal-products/cattle-beef/market-outlook",
         note="+13% over 2025's record $322/cwt", sort_order=2),
    dict(category="feeder", label="Feeder Cattle — Q3 2026 (projected)", value_text="$410–415", unit="$/cwt",
         as_of="2026 Q3", source="Industry outlook", source_url=AMS, sort_order=3),

    # --- Fed / live cattle ---
    dict(category="fed", label="Slaughter Steers — live (cash)", value=255.50, unit="$/cwt",
         as_of="2026-06", source="USDA AMS", source_url=AMS, sort_order=1,
         note="North cash trade $255–256 live"),
    dict(category="fed", label="Slaughter Steers — dressed", value=403.0, unit="$/cwt",
         as_of="2026-06", source="USDA AMS", source_url=AMS, sort_order=2),
    dict(category="fed", label="Slaughter Steers — 2026 avg (forecast)", value=250.16, unit="$/cwt",
         as_of="2026 forecast", source="USDA ERS", source_url="https://www.ers.usda.gov/topics/animal-products/cattle-beef/market-outlook", sort_order=3),

    # --- Boxed beef cutout ---
    dict(category="cutout", label="Choice Boxed Beef Cutout", value=398.94, unit="$/cwt", change=-1.37,
         as_of="2026-06-24", source="USDA AMS (LM_XB403)", source_url="https://www.ams.usda.gov/mnreports/lsddcbs.pdf", sort_order=1),
    dict(category="cutout", label="Select Boxed Beef Cutout", value=378.14, unit="$/cwt", change=-2.92,
         as_of="2026-06-24", source="USDA AMS (LM_XB403)", source_url="https://www.ams.usda.gov/mnreports/lsddcbs.pdf", sort_order=2),
    dict(category="cutout", label="Choice–Select Spread", value=20.80, unit="$/cwt",
         as_of="2026-06-24", source="USDA AMS", source_url=AMS, sort_order=3),

    # --- Wagyu premium benchmarks (retail / carcass / breeding) ---
    dict(category="wagyu", label="American Wagyu (retail)", value_text="$50–80", unit="/lb",
         as_of="2026", source="Retail survey", source_url="", sort_order=1),
    dict(category="wagyu", label="Australian Fullblood (retail)", value_text="$70–120", unit="/lb",
         as_of="2026", source="Retail survey", source_url="", sort_order=2),
    dict(category="wagyu", label="Japanese A4/A5 (retail)", value_text="$120–200", unit="/lb",
         as_of="2026", source="Retail survey", source_url="", sort_order=3),
    dict(category="wagyu", label="Authentic Kobe (retail)", value_text="$200–300", unit="/lb",
         as_of="2026", source="Retail survey", source_url="", sort_order=4),
    dict(category="wagyu", label="Fullblood carcass (hanging weight)", value_text="$15–17", unit="/lb",
         as_of="2026", source="Producer pricing", source_url="", sort_order=5),
    dict(category="wagyu", label="Fullblood Wagyu ground", value=11.85, unit="/lb",
         as_of="2026", source="Producer pricing", source_url="", sort_order=6),
    dict(category="wagyu", label="Fullblood breeding female", value_text="$5,000–6,000+", unit="head",
         as_of="2026", source="Seedstock market", source_url="", sort_order=7),

    # --- Market context / commentary ---
    dict(category="context", label="US cattle herd at a multi-decade low", value=86.2, unit="M head",
         as_of="Jan 2026", source="USDA NASS", source_url="https://www.usda.gov", sort_order=1,
         note="Tightest supply in generations — the tailwind under every price above."),
    dict(category="context", label="US–Mexico border closed to live cattle", value_text="−1.2–1.5M", unit="head/yr",
         as_of="2026", source="USDA / APHIS", source_url="https://www.aphis.usda.gov", sort_order=2,
         note="New World screwworm containment removed ~1.2–1.5M head of annual supply."),
    dict(category="context", label="Domestic beef demand", value_text="Strongest since 1983", unit="",
         as_of="2026", source="USDA ERS", source_url="https://www.ers.usda.gov/topics/animal-products/cattle-beef/market-outlook", sort_order=3,
         note="Demand strength is meeting record-low supply — historically bullish for genetics."),
]


def _rows():
    """USDA cattle-market rows are breed-generic; the 'wagyu' category rows are
    Wagyu retail prices — only the wagyu tank seeds those."""
    from .. import tank
    if tank.key() == "wagyu":
        return QUOTES
    return [q for q in QUOTES if q.get("category") != "wagyu"]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(MarketQuote).delete()
        for q in _rows():
            db.add(MarketQuote(**q))
        db.commit()
        print(f"Seeded {len(_rows())} market quotes across "
              f"{len(set(q['category'] for q in _rows()))} categories.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
