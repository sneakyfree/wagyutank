"""Seed the Notable Sales tracker — record-setting Wagyu genetics and cattle sales,
each with a date and a source. Re-runnable (replaces all rows).

  python -m app.jobs.seed_notable_sales
"""
from .. import models  # noqa: F401
from ..db import Base, SessionLocal, engine
from ..models import NotableSale

BC = "https://www.beefcentral.com/genetics/"

SALES = [
    # --- Semen ---
    dict(category="semen", animal_name="Mayura Itoshigenami Jnr", is_record=True,
         headline="World-record Wagyu semen — $68,000 for a single straw",
         price=68000, currency="AUD", usd_approx=45000, unit="per straw", country="AU",
         sale_venue="Mayura Wagyu Sale", buyer="Double 8 Cattle Co (Arizona, USA)",
         note="A world record for bovine semen at the time — one straw of the legendary "
              "Mayura Itoshigenami Jnr, bound for Arizona.",
         source="Beef Central", source_url=BC + "world-record-for-semen-set-during-mayura-wagyu-sale/",
         sort_order=1),
    dict(category="semen", animal_name="Coates Itoshigenami G113 (Macquarie Wagyu)",
         headline="$37,500 for three straws at the Elite Wagyu Sale",
         price=37500, currency="AUD", usd_approx=24800, unit="for 3 straws", country="AU",
         sale_venue="AWA Elite Wagyu Sale",
         note="Semen grossed nearly $500,000 across 156 straws at that single auction.",
         source="Beef Central", source_url=BC, sort_order=2),

    # --- Embryo ---
    dict(category="embryo", animal_name="World K's Kanadagene 100 × WSI Tai Ms Ito DG007W", is_record=True,
         headline="Record Wagyu embryo — $23,000 apiece",
         price=23000, currency="AUD", usd_approx=15200, unit="per embryo", country="AU",
         sale_venue="AWA Elite Wagyu Sale", buyer="Scott de Bruin, Mayura Wagyu (SA)",
         seller="Ken Kurosawatsu, Wagyu Sekai (Ontario, Canada)",
         note="Four embryos described as “a royal marriage of World K's Suzutani with World K's "
              "Okutani — which will never be offered again.”",
         source="Queensland Country Life", source_url="https://www.queenslandcountrylife.com.au/story/6745035/elite-wagyu-sale-hits-105000-high/",
         sort_order=1),

    # --- Female ---
    dict(category="female", animal_name="Sunnyside S0014", is_record=True,
         headline="$400,000 heifer — the top seedstock price ever paid in Australia",
         price=400000, currency="AUD", usd_approx=264000, unit="head", country="AU",
         sale_venue="AWA Elite Wagyu Sale, Melbourne", date_label="May 2022", year=2022,
         note="A 13-month-old unjoined Fullblood Wagyu heifer — the highest price ever paid in "
              "Australia for a seedstock animal of either sex.",
         source="Nutrien Ag Solutions", source_url="https://www.nutrienagsolutions.com.au/wagyu-heifer-sells-400000-and-sets-new-australian-record",
         sort_order=1),
    dict(category="female", animal_name="Elite Wagyu Sale females",
         headline="Registered Fullblood females to $105,000",
         price=105000, currency="AUD", usd_approx=69000, unit="head", country="AU",
         sale_venue="AWA Elite Wagyu Sale",
         note="Elite female genetics now rival — and often exceed — bull prices, thanks to their "
              "impact in embryo programs.",
         source="Beef Central", source_url=BC + "registered-females-sell-to-105000-in-elite-wagyu-sale/",
         sort_order=2),

    # --- Bull ---
    dict(category="bull", animal_name="Sahara Park Yasufuku R153", is_record=True,
         headline="$240,000 for a 16-month Yasufuku Jr son",
         price=240000, currency="AUD", usd_approx=158000, unit="head", country="AU",
         sale_venue="AWA Elite Wagyu Sale", date_label="May 2022", year=2022,
         seller="Dean & Sam Pollard, Sahara Park (Rockhampton, QLD)",
         buyer="Que Hornery, Bar H Grazing (Moranbah, QLD)",
         note="A son of the high-marbling sire World K's Yasufuku Jr.",
         source="Beef Central", source_url=BC + "australian-stud-beef-cattle-breed-record-prices-at-a-glance/",
         sort_order=1),
    dict(category="bull", animal_name="Mayura Fullblood bull",
         headline="$122,500 — Australian fullblood bull record",
         price=122500, currency="AUD", usd_approx=80800, unit="head", country="AU",
         sale_venue="Mayura Wagyu Sale", date_label="Oct 2023", year=2023,
         source="Stock Journal", source_url="https://www.stockjournal.com.au/story/7685124/",
         sort_order=2),

    # --- Carcass / whole cow (Japan) ---
    dict(category="carcass", animal_name="“Yoshitoyo” (Matsusaka)", is_record=True,
         headline="¥50 million (~$488,000) for a single Matsusaka cow",
         price=50000000, currency="JPY", usd_approx=488000, unit="head", country="JP",
         sale_venue="Matsusaka Beef Contest, Japan",
         note="A 687 kg “super cow” — worth about 50× the average Matsusaka animal. Japanese "
              "branded beef routinely tops any Western genetics sale.",
         source="Pursuit Farms", source_url="https://pursuitfarms.com/blogs/news/matsusaka-wagyu-the-pinnacle-of-japanese-beef",
         sort_order=1),
    dict(category="carcass", animal_name="Queen of Matsusaka (annual top)",
         headline="~$300,000 for the champion at the annual Matsusaka auction",
         price=300000, currency="USD", usd_approx=300000, unit="head", country="JP",
         sale_venue="Matsusaka Beef Contest (November)",
         note="The grand-champion cow typically sells for 4–5× the runner-up.",
         source="Pursuit Farms", source_url="https://pursuitfarms.com/blogs/news/matsusaka-wagyu-the-pinnacle-of-japanese-beef",
         sort_order=2),
]


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        db.query(NotableSale).delete()
        for s in SALES:
            db.add(NotableSale(**s))
        db.commit()
        print(f"Seeded {len(SALES)} notable sales across "
              f"{len(set(s['category'] for s in SALES))} categories.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
