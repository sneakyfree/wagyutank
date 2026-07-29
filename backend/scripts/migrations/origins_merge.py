#!/usr/bin/env python3
"""Grant's 2026-07-21 corrections to the WagyuTank foundation roster.

 1. Reclassify bulls that are NOT original Japan imports (born US/AU) so they
    drop out of the "Original import foundation sires" section.
 2. Stamp every bull with birth_country + importer + import_year, sourced from
    Grant's two Wagyu International export charts.
 3. Attach the official 16/16 bloodline analysis (units out of 16) where a
    sourced figure exists — Grant's 16/16 chart first, V-Bar-V 2009 catalog as
    fallback. Never invented.

Run on Veron: python3 origins_merge.py
"""
import json
from pathlib import Path

ENRICHED = Path("/home/user1-gpu/wagyutank/backend/app/seed/data/foundation_bulls_enriched.json")

# ---------------------------------------------------------------- origins ---
# birth_country, importer, import_year, bred_outside_japan.
# JP rows come straight off the two "exported from Japan" charts.
IMPORTS = {
    # --- 1976 Morris Whitney (2 black + 2 red) ---
    "Mazda":            ("JP", "Morris Whitney", 1976),
    "Mt. Fuji":         ("JP", "Morris Whitney", 1976),
    "Judo":             ("JP", "Morris Whitney", 1976),
    "Rueshaw":          ("JP", "Morris Whitney", 1976),
    # --- 1993 Mannett ---
    "Haruki 2":         ("JP", "Mannett", 1993),
    "Michifuku":        ("JP", "Mannett", 1993),
    # --- 1994 Japanese Venture Partners ---
    "Fukutsuru 068":    ("JP", "Japanese Venture Partners", 1994),
    "Kikuyasu-400":     ("JP", "Japanese Venture Partners", 1994),
    "Yasutanisakura":   ("JP", "Japanese Venture Partners", 1994),
    # --- 1994 Mannett ---
    "Kenhanafuji":      ("JP", "Mannett", 1994),
    "Takazakura":       ("JP", "Mannett", 1994),
    # --- 1994 Al & Marie Wood (Akaushi) ---
    "Hikari":           ("JP", "Al & Marie Wood", 1994),
    "Shigemaru":        ("JP", "Al & Marie Wood", 1994),
    "Tamamaru":         ("JP", "Al & Marie Wood", 1994),
    # --- 1995 Takeda Farms ---
    "Itohana 2":        ("JP", "Takeda Farms", 1995),
    "Itomichi 1/2":     ("JP", "Takeda Farms", 1995),
    "Kikuhana":         ("JP", "Takeda Farms", 1995),
    "Kinto":            ("JP", "Takeda Farms", 1995),
    "Terutani":         ("JP", "Takeda Farms", 1995),
    # --- 1997 Westholme (live bulls) ---
    "Hirashigetayasu":  ("JP", "Westholme", 1997),
    "Itomoritaka":      ("JP", "Westholme", 1997),
    "Kitateruyasudoi":  ("JP", "Westholme", 1997),
    # --- 1997 Westholme (SEMEN only — never left Japan alive) ---
    "Dai 6 Seizan":     ("JP", "Westholme (semen)", 1997),
    "Kitatsurukiku Doi": ("JP", "Westholme (semen)", 1997),
    "Shigefuku":        ("JP", "Westholme (semen)", 1997),
    # --- 1997 Takeda Farms ---
    "Itoshigefuji":     ("JP", "Takeda Farms", 1997),
    "Itoshigenami":     ("JP", "Takeda Farms", 1997),
    "Itozuru Doi":      ("JP", "Takeda Farms", 1997),
    "Kikuterushige":    ("JP", "Takeda Farms", 1997),
    "Kikutsuru Doi":    ("JP", "Takeda Farms", 1997),
    "Mitsuhikokura":    ("JP", "Takeda Farms", 1997),
    # --- 1997 Mannett ---
    "Yasufuku Jr":      ("JP", "Mannett", 1997),
    # --- off-chart Japan-born imports (documented elsewhere) ---
    "Kamui":            ("JP", "Takeda Farms", 1997),
    "Itotani":          ("JP", "Lakeside Industries (Canada)", 1991),
}

# Born outside Japan. `foundation`=True means it still belongs in the original
# import section because the export chart itself lists it (a calf born to an
# imported dam, in-utero on the boat); False means it moves to the
# "bred outside Japan" section.
OUTSIDE = {
    # Chart-listed calf born to the imported dam Nakayuki, 1994 Mannett group.
    "Kitaguni Jr":            ("US", "Mannett", 1994, True),
    # World K's home-bred sires — already outside, just stamping the country.
    "World K's Sanjirou":     ("US", None, None, False),
    "World K's Shigeshigetani": ("US", None, None, False),
    "World K's Beijirou":     ("US", None, None, False),
    "Genjiro":                ("US", None, None, False),
    # --- Grant's 2026-07-21 correction: V-Bar-V catalog bulls that are NOT imports ---
    "Bar R Sanjirou 44K":     ("US", None, None, False),
    "RSC Fuku-Yasu 2613":     ("US", None, None, False),
    "SR Y13 Sanji":           ("US", None, None, False),
    "UKB Dia 6 Kitaseki":     ("US", None, None, False),
    "Donarudo":               ("US", None, None, False),
    "Kage":                   ("US", None, None, False),
    "UKB Mr. Ume Homaru":     ("US", None, None, False),
    "Z278 Hirashigetayasu":   ("AU", None, None, False),
    # Origin country not established — shown as "bred outside Japan", no flag.
    "Kalanga Red Star C402":  (None, None, None, False),
}

# ------------------------------------------------------- 16/16 analysis -----
# Units out of 16. Source A = Grant's "16/16 Analysis" chart (authoritative).
# Source B = V-Bar-V Semen Services Fall 2009 Sire Directory (fallback only).
BLEND_A = {
    "Hirashigetayasu": ("C", {"Tajima": 4, "Kedaka": 6, "Tottori": 2, "Okayama": 4}),
    "Itomoritaka":     ("D", {"Kedaka": 7, "Tottori": 5, "Itozakura": 2, "Okayama": 2}),
    "Kitateruyasudoi": ("B", {"Tajima": 16}),
    "Shigefuku":       ("C", {"Kedaka": 12, "Tottori": 4}),
    "Dai 6 Seizan":    ("C", {"Tajima": 4, "Itozakura": 3, "Shimane": 1, "Okayama": 8}),
    "Kitatsurukiku Doi": ("B", {"Tajima": 16}),
    "Kikutsuru Doi":   ("B", {"Tajima": 16}),
    "Itoshigefuji":    ("C", {"Itozakura": 12, "Okayama": 4}),
    "Itoshigenami":    ("B", {"Itozakura": 4, "Kumanami": 12}),
    "Kikuterushige":   ("B", {"Tajima": 16}),
    "Itozuru Doi":     ("C", {"Tajima": 8, "Kedaka": 4, "Itozakura": 4}),
    "Itomichi 1/2":    ("C", {"Tajima": 2, "Itozakura": 8, "Shimane": 2, "Okayama": 1,
                              "Hiroshima": 2, "Kumanami": 1}),
    "Kikuhana":        ("C", {"Kedaka": 1, "Itozakura": 14, "Shimane": 1}),
    "Itohana 2":       ("A", {"Itozakura": 13, "Shimane": 1, "Hiroshima": 1, "Other": 1}),
    "Terutani":        ("B", {"Tajima": 16}),
    "Fukutsuru 068":   ("B", {"Tajima": 16}),
    "Haruki 2":        ("D", {"Tajima": 8, "Kedaka": 4, "Hiroshima": 2, "Other": 2}),
    "Kenhanafuji":     ("C", {"Kedaka": 2, "Tottori": 2, "Itozakura": 6, "Shimane": 4, "Other": 2}),
    "Kikuyasu-400":    ("B", {"Tajima": 16}),
    "Michifuku":       ("B", {"Tajima": 16}),
}
BLEND_B = {
    "World K's Shigeshigetani": ("D", {"Tajima": 12, "Kedaka": 2, "Hiroshima": 1, "Other": 1}),
    "World K's Sanjirou":      ("B", {"Tajima": 16}),
    "World K's Beijirou":      ("C", {"Tajima": 9, "Kedaka": 2, "Itozakura": 3,
                                      "Hiroshima": 1, "Other": 1}),
    "Kitaguni Jr":             ("C", {"Tajima": 6, "Kedaka": 2, "Itozakura": 4,
                                      "Shimane": 2, "Okayama": 2}),
    "Takazakura":              ("C", {"Tajima": 6, "Okayama": 4, "Hiroshima": 2, "Other": 4}),
    "Yasutanisakura":          ("C", {"Tajima": 8, "Itozakura": 2, "Shimane": 2, "Other": 4}),
    "Yasufuku Jr":             ("B", {"Tajima": 16}),
    "Donarudo":                ("B", {"Tajima": 14, "Okayama": 2}),
    "Kage":                    ("C", {"Tajima": 2.4, "Kedaka": 2.0, "Tottori": 0.3,
                                      "Itozakura": 9.4, "Shimane": 1.5, "Other": 0.5}),
    "SR Y13 Sanji":            ("D", {"Tajima": 10, "Kedaka": 2, "Itozakura": 2.3,
                                      "Okayama": 0.8, "Other": 1.0}),
    "UKB Dia 6 Kitaseki":      ("C", {"Tajima": 2.0, "Kedaka": 1.9, "Tottori": 4.0,
                                      "Itozakura": 2.6, "Shimane": 0.5, "Okayama": 4.0}),
    "RSC Fuku-Yasu 2613":      ("C", {"Tajima": 15.0, "Itozakura": 0.3, "Okayama": 0.3,
                                      "Other": 0.5}),
    "Z278 Hirashigetayasu":    ("C", {"Tajima": 7.1, "Kedaka": 4.0, "Tottori": 1.8,
                                      "Itozakura": 0.5, "Okayama": 2.3, "Hiroshima": 0.1,
                                      "Other": 0.3}),
}

SRC_A = "16/16 Analysis chart (Wagyu International)"
SRC_B = "V-Bar-V Semen Services Fall 2009 Sire Directory"


def main():
    bulls = json.loads(ENRICHED.read_text())
    by_name = {b["name"]: b for b in bulls}

    missing = []
    for name in list(IMPORTS) + list(OUTSIDE) + list(BLEND_A) + list(BLEND_B):
        if name not in by_name:
            missing.append(name)
    if missing:
        print("WARN — names not found in roster:", sorted(set(missing)))

    n_imp = n_out = n_blend = 0

    for name, (cc, importer, year) in IMPORTS.items():
        b = by_name.get(name)
        if not b:
            continue
        b["birth_country"] = cc
        b["importer"] = importer
        b["import_year"] = year
        b["bred_outside_japan"] = False
        n_imp += 1

    for name, (cc, importer, year, foundation) in OUTSIDE.items():
        b = by_name.get(name)
        if not b:
            continue
        b["birth_country"] = cc
        b["importer"] = importer
        b["import_year"] = year
        b["bred_outside_japan"] = not foundation
        n_out += 1

    for src, table in ((SRC_A, BLEND_A), (SRC_B, BLEND_B)):
        for name, (grp, units) in table.items():
            b = by_name.get(name)
            if not b:
                continue
            # Chart A wins — never let the fallback overwrite it.
            if b.get("blend") and b.get("blend_source") == SRC_A:
                continue
            total = round(sum(units.values()), 1)
            b["blend"] = {k: v for k, v in units.items() if v}
            b["blend_total"] = total
            b["blend_group"] = grp
            b["blend_source"] = src
            n_blend += 1

    ENRICHED.write_text(json.dumps(bulls, indent=1, ensure_ascii=False))

    jp = sum(1 for b in bulls if b.get("birth_country") == "JP")
    us = sum(1 for b in bulls if b.get("birth_country") == "US")
    au = sum(1 for b in bulls if b.get("birth_country") == "AU")
    unk = sum(1 for b in bulls if not b.get("birth_country"))
    outside = sum(1 for b in bulls if b.get("bred_outside_japan"))
    print(f"origins stamped: {n_imp} imports + {n_out} outside; blends attached: {n_blend}")
    print(f"birth country → JP {jp} · US {us} · AU {au} · unknown {unk}")
    print(f"section split  → import section {len(bulls)-outside} · bred-outside-Japan {outside}")
    for b in bulls:
        if not b.get("birth_country"):
            print("   no birth_country:", b["name"])


if __name__ == "__main__":
    main()
