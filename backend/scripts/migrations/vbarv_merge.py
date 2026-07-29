#!/usr/bin/env python3
"""Merge V-Bar-V 2009 Fall Sire Directory content into WagyuTank foundation bull data.
Run on Veron inside the wagyutank checkout: python3 vbarv_merge.py
"""
import json
from pathlib import Path

ENRICHED = Path("/home/user1-gpu/wagyutank/backend/app/seed/data/foundation_bulls_enriched.json")
PHOTOS = Path("/home/user1-gpu/wagyutank/backend/app/seed/data/animal_photos.json")

SOURCE_NOTE = " (V-Bar-V Semen Services Fall 2009 Sire Directory)"

# ---- 1. Bio append text for existing bulls, keyed by registration_no (or name if none) ----
BIO_APPENDS = {
"FB2907": " The V-Bar-V Semen Services 2009 Sire Directory adds: World K fed 3,800 F1 steers to a 540-day ADG of 0.98kg, with 90% grading 9+ on the Australian scale (three full grades above USDA prime) and the rest 7-9. Breeders there observed him throwing tall, long cattle with good thickness and good dispositions, and noted his semen was already scarce by 2009.",
"FB2501": " Per the V-Bar-V 2009 catalog, World K tested 6,800 F1 progeny with 88% grading 9+ on the Australian scale (540-day ADG 0.95kg) — Sanjirou ranked #3 for marbling in the 2006 U.S. Sire Summary, ahead of his own sire Michifuku. Recorded EBVs: 200-day +6, 400-day +7, 600-day +8, EMA +1.8, IMF% +0.6. Breeders noted his calves carry good thickness and eye appeal with good dispositions.",
"FB1615": " The V-Bar-V 2009 catalog corroborates his standing as formerly the #1 marbling bull in the U.S. Sire Summary: World K fed 12,000 finished steers to an 85% 9+ grading rate on the Australian scale (540-day ADG 1.05kg). Recorded EBVs: 600-day +8, IMF% +0.7, milk -14 — breeders noted the milk trade-off but praised the thickness, marbling and dispositions of his calves.",
"FB1614": " The V-Bar-V 2009 catalog calls him 'probably one of the most underutilized bulls of the breed,' noting he blends 56% Tajima, 13% Itozakura, 19% Shimane and 6% Kedaka rather than pure Tajima — good enough genetics that he was bred to Suzutani, arguably the greatest cow in Wagyu history, producing Shigeshigetani. Breed-plan data had him a trait leader in seven categories from birth weight to growth, and leading 200/400/600-day weights and mature cow size in EMA and IMF. Sold at $30/straw at the time.",
"FB2422": " The V-Bar-V 2009 catalog adds pedigree context: Kitaguni Jr is a son of Kitaguni 7-8 and a grandson of Dai-7 Itozakura and Itozakura, a line whose descendants include Itomichi and Itozurodoi 151. Crossed onto Tajima cows he was noted to increase frame size and enhance growth; sold at $30/straw.",
"FB2892": " Photo swapped 2026-07 for a cleaner color print of the same reference photograph, sourced from the V-Bar-V Semen Services 2009 Sire Directory (prior file was a low-contrast black-and-white scan of the identical image). That catalog also traces his sire to Takaie J142 and grandsire to Yasufuku J930 — who sired three of the highest-marbling sires in Japan and dominated the 2007 Ninth Zenko All Wagyu competition. World K fed 1,200 finished steers to a 540-day ADG of 1.87kg with 68% grading 9+ on the Australian scale. Breeder's note verbatim: 'He put a lot of length in his calves and very good marbling. Don't let the picture fool you.' Sold at $30/straw.",
"FB4697": " The V-Bar-V 2009 catalog notes he is a son of Yasufuku J930, who sired three of Japan's top marbling bulls (one carcass sold for $97,000) and Australian breeders had 'rediscovered' him and were using him heavily by 2009 — 1,200 finished steers graded 78% 9+ on the Australian scale. Breeder's note, verbatim: 'Another one of the great Wagyu sires that has a terrible picture... he throws much better cattle than his picture would lead you to believe, with good bodies and very good marbling.' Sold at $40/straw.",
"FB2289": " Per the V-Bar-V 2009 catalog, he is out of Haruki 2 and the cow Okutani; World K fed 2,000 finished steers to a 65% 9+ Australian-scale grading rate (540-day ADG 1.05kg), a good combination of Yasumi Doi and Shigeshigenami for marbling with Itozakura/Kedaka on the female side for carcass weight and growth. Sold at $30/straw.",
"FB2101": " The V-Bar-V 2009 catalog underscores his rarity: only 300 straws were reported available at the time ('some of the last that will be sold'). He traces twice to Yasumi Doi J10328 and twice to the cow Kikutsuru J978542, known as 'the Hyogo cow.' Recorded EBVs there: 600-day -19, IMF% -0.1 — consistent with his reputation for smaller-framed, lower-growth offspring that cross well onto Shimane bloodlines with very good dispositions.",
"FB2126": " The V-Bar-V 2009 catalog notes he was still living in the U.S. at the time, estimated over 2,000 lbs, and credits him with increasing mature size and growth rate without sacrificing marbling. Recorded EBVs: 600-day +18, EMA +2.8, IMF% +0.2. Sold at $60/straw.",
"TF147": " The V-Bar-V 2009 catalog traces Dai-30 Noboru back roughly 300 years to Okayama's original bull Takenotani Tsuru, later called Noboru and used generation after generation in the Okayama strain — explaining TF147's 56% Shimane / 41% Okayama / 3% Kedaka blend. Leading Australian breeder David Blackmore is quoted calling 147's daughters his favorite brood cows, able to 'make a living on pasture.' Australian fullblood carcass data there showed an average carcass weight of 1,150 lbs and average marbling score of 8.5/9. Sold at $60/straw.",
"TF148": " The V-Bar-V 2009 catalog notes TF148 was bred by double-crossing Shigekanenami on both the sire and dam side specifically to enhance marbling, one of three historic Tajima strains (Okudoi, Nakadoi, Nami) with Shigekanenami a typical Nami-strain bull. Australian fullblood carcass data recorded there: average carcass weight 970 lbs, average marbling score 8.6/9. Sold at $60/straw.",
"TF151": " Note on the photograph: the V-Bar-V 2009 catalog's own print of this bull is captioned 'picture of original 151, not the clone' — semen sold from 2009 onward came from a DNA-identical clone after the original bull's death. That catalog quotes an unnamed 'leading Wagyu expert' stating flatly that '151 beat Michifuku in every statistical category in fullblood Wagyu carcasses,' and notes the original was a 2,400 lb bull whose daughters were prized by major Australian breeders for size and maternal traits.",
"FB2102": " The V-Bar-V 2009 catalog adds that Yasutanisakura was 'overlooked for the most part in the U.S.,' bringing body mass structure and top maternal traits — daughters noted for milk and brood-cow quality, sons for passing on the same growth and balance. Sold at $40/straw.",
"FB2100": " The V-Bar-V 2009 catalog confirms Kikuyasu-400 as 'by far the largest Tajima sire ever exported from Japan,' weighing 1,980 lbs and holding the record for largest ribeye area at the time, with a reputation for tall-framed but lower-milk offspring. Sold at $45/straw.",
}

# ---- 2. Shigefuku gets a fuller merge since it's a headline new-photo bull ----
SHIGEFUKU_APPEND = " The V-Bar-V Semen Services 2009 Sire Directory profiles this same bull as '005 Shigefuku,' by their count one of only two sons and two daughters of Shigefuku J1822 in the world at the time. It quotes the Westholme group calling him 'the most promising bull at that time in the world' on first sight, and records him as 44% Kedaka — among the highest Kedaka content of any bull in Australia — combined with 31% Tajima and 12% Tottori. All calves killed to that point graded BMS 8-10 (prime+ to prime++). Sexed and unsexed semen were both listed, at $75 and $50 per straw respectively."

ITOHANA_APPEND = " The V-Bar-V 2009 catalog gives him a full profile as 'TF Itohana 2': Dai-7 Itozakura appears in all four corners of his pedigree, adding frame size, and his dam was the great cow Aino 6 — 17 calves out of the Aino cow group were slaughtered and every one graded A5 on the Japanese scale, the highest grade possible. His daughters are noted for excellent maternal traits, good milking ability and good mature cow size. Recorded EBVs there: 600-day +16, EMA +0.6. Sold at $60/straw."

# ---- 3. Brand-new bull profiles sourced entirely from the catalog ----
NEW_BULLS = [
{
 "registration_no": None, "name": "Donarudo",
 "aliases": ["Donarudo (V-Bar-V 2009)"],
 "animal_type": "bull", "breed": "Fullblood Black",
 "bloodline": "Tajima", "bloodline_detail": "Predominantly Tajima (Yasumi Doi / Kikumi Doi) with a minor Okayama component.",
 "birth_year": None, "importer": None, "import_year": None, "prefecture": None,
 "sire": "Terutani", "dam": "Nakayuki",
 "au_progeny": 800,
 "marbling_note": "Heavy Yasumi Doi/Kikumi Doi content noted for high marbling ability; suited to high-growth females and F1 production.",
 "bio": "Donarudo appears in the V-Bar-V Semen Services 2009 Fall Sire Directory, sired by Terutani (out of the Kikuteru Doi/Kiknori Doi lines) and out of the cow Nakayuki. The catalog's 16/16 analysis places him at roughly 88% Tajima and 13% Okayama, with heavy Yasumi Doi and Kikumi Doi content that the compilers credited with high marbling ability, suitable for high-growth females and F1 production. World K fed 800 finished steers behind him to a 540-day ADG of 0.85kg, with 70% grading 9+ on the Australian marbling scale and 20% grading 7-9. Semen was offered at $30 per straw, available in the United States, South America, Australia, Mexico and Canada.",
 "photo_urls": ["/foundation/donarudo.jpg"],
 "photo_note": "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory.",
 "confidence": "medium",
 "notes": "Added 2026-07 from the V-Bar-V Semen Services Fall 2009 Sire Directory (vbarvwagyu.com); not independently cross-verified beyond that source.",
},
{
 "registration_no": None, "name": "Kage",
 "aliases": ["Kage (V-Bar-V 2009)"],
 "animal_type": "bull", "breed": "Fullblood Black",
 "bloodline": "Itozakura", "bloodline_detail": "High Itozakura content (56%) via Kitaguni 7-8, blended with Tajima, Kedaka and Shimane.",
 "birth_year": None, "importer": None, "import_year": None, "prefecture": None,
 "sire": "Kikuhana", "dam": "Reiko",
 "au_progeny": 1200,
 "marbling_note": "High Itozakura content for growth and heavy carcass weight; Kitaguni 7-8 is regarded in Japan as the leading Fujiyoshi-line bull for high marbling.",
 "bio": "Kage is profiled in the V-Bar-V Semen Services 2009 Fall Sire Directory, sired by Kikuhana (out of the Itohana/Nayori 1 lines) and out of the cow Reiko (by Kitaguni 7-8 out of Okahan). The catalog's 16/16 analysis puts him at roughly 56% Itozakura with 12% each of Tajima, Kedaka and Shimane — high Itozakura content the compilers linked to good growth and heavy carcass weight, calling Kitaguni 7-8 'the most famous bull in Japan for high marbling' in the Fujiyoshi line and rating Kage a great maternal sire for fullblood production. World K fed 1,200 finished steers behind him to a 540-day ADG of 1.0kg, with 70% grading 9+ on the Australian scale and 15% grading 7-9. Semen was offered at $30 per straw, available in the United States, South America, Australia, Mexico and Canada.",
 "photo_urls": ["/foundation/kage.jpg"],
 "photo_note": "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory.",
 "confidence": "medium",
 "notes": "Added 2026-07 from the V-Bar-V Semen Services Fall 2009 Sire Directory (vbarvwagyu.com); not independently cross-verified beyond that source.",
},
{
 "registration_no": None, "name": "SR Y13 Sanji",
 "aliases": ["Sanji", "SR Y13 Sanji (V-Bar-V 2009)"],
 "animal_type": "bull", "breed": "Fullblood Black",
 "bloodline": "Tajima", "bloodline_detail": "Line-bred Yasumi Doi/Shigekanenami through Sanjirou, crossed with the Kitateruyasudoi 003 marbling line.",
 "birth_year": None, "importer": None, "import_year": None, "prefecture": None,
 "sire": "Sanjiro", "dam": "Kitatemako 003",
 "au_progeny": None,
 "marbling_note": "High Tajima combination of Yasumi Doi/Shigekanenami with Terunaga Doi from ETJ003 — ideal for F1 production or high-growth fullblood females.",
 "bio": "SR Y13 Sanji, called simply 'Sanji' in the V-Bar-V Semen Services 2009 Fall Sire Directory, is a cross of the line-bred-Yasumi-Doi bull Sanjirou onto a daughter of Kitateruyasudoi 003, one of the great marbling bulls of the era; his dam is a full sister to 005 Shigefuku 13M's dam, described in the catalog as 'a tremendous cow family.' Being a Sanjirou son, he was noted as well balanced with great thickness and length — the thickest loin of any of Sanjirou's sons — and, carrying the Kitateruyasudoi bloodline, threw exceptional marbling: more than 500 of his calves had been harvested by 2009 with none grading below prime. Greg Gibbons of the AAA in Australia is quoted calling him 'the best bull I have seen outside of Japan' after using him in the AAA program. By the time of the catalog Sanji was deceased and semen was described as becoming very limited; both sexed ($75/straw) and unsexed ($50/straw) semen were offered, available in South America, Australia, Mexico and Canada.",
 "photo_urls": ["/foundation/sr-y13-sanji.jpg"],
 "photo_note": "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory.",
 "confidence": "medium",
 "notes": "Added 2026-07 from the V-Bar-V Semen Services Fall 2009 Sire Directory (vbarvwagyu.com); not independently cross-verified beyond that source.",
},
{
 "registration_no": None, "name": "UKB Dia 6 Kitaseki",
 "aliases": ["Kitaseki", "UKB Dia 6 Kitaseki (V-Bar-V 2009)"],
 "animal_type": "bull", "breed": "Fullblood Black",
 "bloodline": "Tottori/Kedaka", "bloodline_detail": "Tottori/Kedaka growth-and-maternal base with Itozakura for carcass weight; a total outcross to established North/South/Central American herds.",
 "birth_year": None, "importer": None, "import_year": None, "prefecture": None,
 "sire": "Dai 6 Seizan", "dam": "Kitasekihiro",
 "au_progeny": None,
 "marbling_note": "Growth and maternal characteristics from the Tottori/Kedaka line, carcass weight from Itozakura; noted grower rather than marbling specialist.",
 "bio": "UKB Dia 6 Kitaseki is presented in the V-Bar-V Semen Services 2009 Fall Sire Directory as a total genetic outcross to every established herd in North, South and Central America at the time — sired by Dai 6 Seizan out of the cow Kitasekihiro. One Wagyu expert quoted in the catalog called him 'the answer to the growth issues within the Wagyu breed': extreme growth, great length, a strong loin, correct feet and legs, and excellent depth of body. The compilers' own observation was that his progeny were big, thick calves with great dispositions, and that his daughters were big, correct cows with plenty of milk; every calf harvested by 2009 graded BMS 8-10 (prime+ to prime++). Semen was offered at $75 per straw, available in the United States.",
 "photo_urls": ["/foundation/ukb-dia6-kitaseki.jpg"],
 "photo_note": "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory.",
 "confidence": "medium",
 "notes": "Added 2026-07 from the V-Bar-V Semen Services Fall 2009 Sire Directory (vbarvwagyu.com). Sire listed as 'Dai 6 Seizan' in the source pedigree — not confirmed to be the same individual as the separately-documented Westholme import bull of that name already in this roster; presented as given in the source without assuming identity.",
},
{
 "registration_no": None, "name": "RSC Fuku-Yasu 2613",
 "aliases": ["2613", "RSC Fuku-Yasu 2613 (V-Bar-V 2009)"],
 "animal_type": "bull", "breed": "Fullblood Black",
 "bloodline": "Tajima", "bloodline_detail": "94% Tajima — heavy Yasutani-Doi/Yasumi-Doi line breeding combining Fukutsuru 068 and Yasufuku Jr in one pedigree.",
 "birth_year": None, "importer": None, "import_year": None, "prefecture": None,
 "sire": "Fukutsuru 068", "dam": "BR Ms Yasufuku 0608",
 "au_progeny": None,
 "marbling_note": "Heavy line-breeding of Yasutani-Doi/Yasumi-Doi; high marbling ability, suited for F1 production or terminal use.",
 "bio": "RSC Fuku-Yasu 2613 is profiled in the V-Bar-V Semen Services 2009 Fall Sire Directory as carrying both Fukutsuru 068 (Dai 2 Yasutsuru Doi line) and Yasufuku Jr (via his dam BR Ms Yasufuku 0608) in a single pedigree, at 94% Tajima. The catalog reports a 17.99-inch ribeye at 20 months and calls him 'the total package' — length, depth, marbling, a strong loin and good feet and legs. One noted Wagyu expert is quoted saying he 'has a very good chance to be the next Mich or Sanjirou.' His first calves — fullbloods plus F1 Angus, Braunvieh and Holstein crosses — were on the ground at the time of the catalog, described as 'the thickest Wagyu cattle we have ever seen' with good length, extreme depth and good dispositions. Semen was offered at $100 per straw, available in South America, Australia, Mexico and Canada.",
 "photo_urls": ["/foundation/rsc-fukuyasu-2613.jpg"],
 "photo_note": "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory.",
 "confidence": "medium",
 "notes": "Added 2026-07 from the V-Bar-V Semen Services Fall 2009 Sire Directory (vbarvwagyu.com); not independently cross-verified beyond that source.",
},
{
 "registration_no": None, "name": "Bar R Sanjirou 44K",
 "aliases": ["44K", "Bar R Sanjirou 44K (V-Bar-V 2009)"],
 "animal_type": "bull", "breed": "Fullblood Black",
 "bloodline": "Tajima (Sanjirou)", "bloodline_detail": "A Sanjirou son, giving him the same marbling-line pedigree as World K's Sanjirou, out of Bar R Wagyu's own Miss Bar R 18H.",
 "birth_year": None, "importer": None, "import_year": None, "prefecture": None,
 "sire": "Sanjirou", "dam": "Miss Bar R 18H",
 "au_progeny": None,
 "marbling_note": "Sanjirou son; brings marbling plus good frame, and was reported climbing the AWA marbling rankings as more progeny data came in.",
 "bio": "Bar R Sanjirou 44K is profiled in the V-Bar-V Semen Services 2009 Fall Sire Directory as ranked 11th in the AWA Sire Summary for marbling at the time — sired by Sanjirou (the same marbling-line bull behind World K's Sanjirou) and out of Bar R Wagyu's own cow Miss Bar R 18H. Breeder Jerry Reeves of Bar R Wagyu is quoted in the catalog explaining that the ranking undersold him: with limited progeny data gathered so far, he expected the bull to climb rapidly in the standings as more results came in. Being a Sanjirou son he was noted to bring good frame alongside marbling, throwing correct, thick, good-topline progeny, and had already seen extensive use in commercial Angus crossbreeding programs for carcass-contest steers. Semen was offered at $40 per straw, available in the United States.",
 "photo_urls": ["/foundation/bar-r-sanjirou-44k.jpg"],
 "photo_note": "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory.",
 "confidence": "medium",
 "notes": "Added 2026-07 from the V-Bar-V Semen Services Fall 2009 Sire Directory (vbarvwagyu.com); not independently cross-verified beyond that source.",
},
{
 "registration_no": None, "name": "Z278 Hirashigetayasu",
 "aliases": ["Z278", "Z278 Hirashigetayasu (V-Bar-V 2009)"],
 "animal_type": "bull", "breed": "Fullblood Black",
 "bloodline": "Kedaka/Fujiyoshi/Tajima composite", "bloodline_detail": "A son of the Westholme import bull Hirashigetayasu 001, uniquely carrying all three original Westholme import bulls (001/002/003) in his pedigree.",
 "birth_year": None, "importer": None, "import_year": None, "prefecture": None,
 "sire": "Hirashigetayasu J2351", "dam": "X106 Ohyurihime",
 "au_progeny": None,
 "marbling_note": "Well-balanced Tajima/Kedaka combination; high growth and good marbling sire from the Westholme program.",
 "bio": "Z278 Hirashigetayasu is a distinct bull from the Westholme foundation sire Hirashigetayasu '001' already on this roster — he is 001's son, profiled separately in the V-Bar-V Semen Services 2009 Fall Sire Directory. His dam, X106 Ohyurihime, is a daughter of Kitateruyasudoi '003,' and his great-grandsire is Itomoritaka '002' — meaning Z278 uniquely carries all three original Westholme import bulls in a single pedigree, a great balance of Kedaka, Fujiyoshi and Tajima. The catalog describes him as very thick and correct, with daughters noted for good udders; his calves were reported born easily despite being somewhat larger-framed than the Wagyu average. Semen was offered at $50 per straw, available in the United States, South America, Mexico and Canada.",
 "photo_urls": ["/foundation/z278-hirashigetayasu.jpg"],
 "photo_note": "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory. This is a different animal from the existing 'Hirashigetayasu' (FB670) profile on this roster — Z278 is that bull's son, not the same individual; the two photographs are of visibly different animals.",
 "confidence": "medium",
 "notes": "Added 2026-07 from the V-Bar-V Semen Services Fall 2009 Sire Directory (vbarvwagyu.com); not independently cross-verified beyond that source. Do not merge with FB670 Hirashigetayasu — confirmed distinct individual (son vs. sire) both by pedigree text and by photo comparison.",
},
{
 "registration_no": None, "name": "Kalanga Red Star C402",
 "aliases": ["Kalanga Red Star C402 (V-Bar-V 2009)"],
 "animal_type": "bull", "breed": "Akaushi (Japanese Red)",
 "bloodline": "Red/Akaushi", "bloodline_detail": "Descends from Heart Brand Red Star and the Hikari/Judo Akaushi lines already represented in this roster.",
 "birth_year": None, "importer": None, "import_year": None, "prefecture": None,
 "sire": "Heart Brand Red Star", "dam": "Kalanga Hikohomare VW36",
 "au_progeny": None,
 "marbling_note": "Reported by the compilers to beat Shigemaru, Hikari and Heartbrand Red Emperor in breed-plan EBVs; Reds noted for exceptional rate of gain on grass or feed.",
 "bio": "Kalanga Red Star C402 is billed in the V-Bar-V Semen Services 2009 Fall Sire Directory as 'finally a fullblood Red Wagyu bull available for the U.S. as well as South and Central America and Mexico' — sired by Heart Brand Red Star and out of Kalanga Hikohomare VW36, a cow tracing through Hikari and Judo (both already foundation sires on this roster) and JVP 27 Homare. The catalog states he 'beats Shigemaru, Hikari and Heartbrand Red Emperor handily in the breed plan EBVs,' and frames the whole Red/Akaushi group as bringing size, meat and milk to the breed along with exceptional rate of gain on grass or feed — Reds were being used in Brazil at the time crossed onto Angus, Hereford and Nelore with first-rate carcasses from both grass and feedlot. Semen was described as limited, offered at $65 per straw, available in the United States, South America, Australia, Mexico and Canada.",
 "photo_urls": ["/foundation/kalanga-red-star-c402.jpg"],
 "photo_note": "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory.",
 "confidence": "medium",
 "notes": "Added 2026-07 from the V-Bar-V Semen Services Fall 2009 Sire Directory (vbarvwagyu.com); not independently cross-verified beyond that source.",
},
{
 "registration_no": None, "name": "UKB Mr. Ume Homaru",
 "aliases": ["UKB Mr. Ume Homaru (V-Bar-V 2009)"],
 "animal_type": "bull", "breed": "Akaushi (Japanese Red)",
 "bloodline": "Red/Akaushi", "bloodline_detail": "Son of Umermaru and grandson of Hikari on the paternal side, out of an own daughter of Judo.",
 "birth_year": None, "importer": None, "import_year": None, "prefecture": None,
 "sire": "Visi Umenaru", "dam": "JVP 702 Homare-27",
 "au_progeny": None,
 "marbling_note": "Positioned by the compilers as the ideal cross onto Kalanga Red Star daughters, giving breeders full coverage of the available Red genetics.",
 "bio": "UKB Mr. Ume Homaru is presented in the V-Bar-V Semen Services 2009 Fall Sire Directory as a young Red Wagyu (Akaushi) bull — a son of Umermaru and grandson of Hikari on the paternal side, out of an own daughter of Judo (both foundation sires already on this roster). The catalog calls him 'another genetically superior power-packed bull of the Red Wagyu strain,' expected to cross extremely well on Kalanga Red Star daughters: 'between the two bulls in this book, you will have very good coverage of the Red genetics.' It anticipates him siring correct, extremely thick, high-marbling calves, with daughters likely to become herd favorites, and notes he was also expected to cross well onto Black genetics. Semen was offered at $65 per straw, available in the United States, South America, Australia, Mexico and Canada.",
 "photo_urls": ["/foundation/ukb-mr-ume-homaru.jpg"],
 "photo_note": "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory.",
 "confidence": "medium",
 "notes": "Added 2026-07 from the V-Bar-V Semen Services Fall 2009 Sire Directory (vbarvwagyu.com); not independently cross-verified beyond that source.",
},
]

# ---- 4. animal_photos.json additions ----
PHOTO_MAP_ADDS = {
 "FB2892": "/foundation/FB2892.jpg",
 "Itohana 2": {
   "primary": "/foundation/itohana-2.jpg",
 },
 "Shigefuku": {
   "primary": "/foundation/shigefuku.jpg",
   "gallery": [
     {"src": "/foundation/shigefuku-005.jpg", "caption": "Full-body reference photo — V-Bar-V Semen Services Fall 2009 Sire Directory"},
     {"src": "/foundation/shigefuku-005-son.jpg", "caption": "A son of Shigefuku (‘005 son at side’) — V-Bar-V Semen Services Fall 2009 Sire Directory"},
   ],
 },
 "Donarudo": "/foundation/donarudo.jpg",
 "Kage": "/foundation/kage.jpg",
 "SR Y13 Sanji": "/foundation/sr-y13-sanji.jpg",
 "UKB Dia 6 Kitaseki": "/foundation/ukb-dia6-kitaseki.jpg",
 "RSC Fuku-Yasu 2613": "/foundation/rsc-fukuyasu-2613.jpg",
 "Bar R Sanjirou 44K": "/foundation/bar-r-sanjirou-44k.jpg",
 "Z278 Hirashigetayasu": "/foundation/z278-hirashigetayasu.jpg",
 "Kalanga Red Star C402": "/foundation/kalanga-red-star-c402.jpg",
 "UKB Mr. Ume Homaru": "/foundation/ukb-mr-ume-homaru.jpg",
}


def main():
    bulls = json.loads(ENRICHED.read_text())
    by_reg = {b.get("registration_no"): b for b in bulls if b.get("registration_no")}
    by_name = {b["name"]: b for b in bulls}

    changed = 0
    for key, text in BIO_APPENDS.items():
        b = by_reg.get(key)
        if b is None:
            print(f"WARN: no bull found for reg {key}")
            continue
        b["bio"] = b["bio"].rstrip() + text
        changed += 1

    shigefuku = by_name.get("Shigefuku")
    if shigefuku:
        shigefuku["bio"] = shigefuku["bio"].rstrip() + SHIGEFUKU_APPEND
        shigefuku["photo_urls"] = ["/foundation/shigefuku.jpg"]
        shigefuku["photo_note"] = "Primary photo provided directly by Grant Whitmer (2026-07); additional reference photos from the V-Bar-V Semen Services Fall 2009 Sire Directory in the gallery below."
        changed += 1
    else:
        print("WARN: Shigefuku not found")

    itohana = by_name.get("Itohana 2")
    if itohana:
        itohana["bio"] = itohana["bio"].rstrip() + ITOHANA_APPEND
        itohana["photo_urls"] = ["/foundation/itohana-2.jpg"]
        itohana["photo_note"] = "Sourced from the V-Bar-V Semen Services Fall 2009 Sire Directory."
        changed += 1
    else:
        print("WARN: Itohana 2 not found")

    existing_names = {b["name"] for b in bulls}
    added = 0
    for nb in NEW_BULLS:
        if nb["name"] in existing_names:
            print(f"SKIP (already exists): {nb['name']}")
            continue
        bulls.append(nb)
        added += 1

    ENRICHED.write_text(json.dumps(bulls, indent=1, ensure_ascii=False))
    print(f"Bio appends applied: {changed}. New bulls added: {added}. Total bulls now: {len(bulls)}.")

    photos = json.loads(PHOTOS.read_text())
    photos.update(PHOTO_MAP_ADDS)
    PHOTOS.write_text(json.dumps(photos, indent=1, ensure_ascii=False))
    print(f"animal_photos.json now has {len(photos)} entries.")


if __name__ == "__main__":
    main()
