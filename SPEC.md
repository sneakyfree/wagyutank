# WagyuTank.com — Research + MVP Spec (v1)

**Date:** 2026-07-05
**Owner:** Grant Whitmer
**Domain:** WagyuTank.com (Cloudflare account)
**One-liner:** The world's go-to marketplace for frozen Wagyu genetics — semen straws, embryos, and cloning/cell-line rights — plus a small set of tightly-related services.
**Session decisions:** Research + plan only (no code yet). MVP includes BOTH fixed-price and no-reserve auctions.

---

## PART A — MARKETPLACE RESEARCH (design patterns)

### The competitive opening (the "why now")
- Existing Wagyu-genetics sellers use one-off Shopify/Wix stores (nuwagyu.com, Bovine Elite) or email/PDF catalogs.
- The only real aggregator — **SIRE BUYER** (sirebuyer.com/wagyu-semen) — is a bare classifieds board: **no filtering, no EPD/pedigree data on listings, no online checkout, no trust layer.** Buying is email-inquiry.
- **The opening:** be the aggregator that actually filters (by bloodline + EPD/EBV + export eligibility), has real checkout, and has a trust layer. Nobody combines these.

### Patterns to copy (source → lesson)
- **Etsy** → dead-simple 4-step onboarding, listings live immediately, no business license to start.
- **Reverb** → free listings always; pre-fill product data so sellers never face a blank form.
- **eBay** → dual buyer/seller feedback; no-reserve auctions as a traffic driver; hidden reserve option.
- **GunBroker** → regulated-goods playbook: can't ship to the buyer's home, so route through a licensed intermediary. Genetics move **tank-to-tank between accredited facilities**; model this as first-class in checkout.
- **StockX / GOAT** → escrow + authentication for high-value goods; "verified" fast-lane for trusted sellers.
- **1stDibs / Chairish** → seller vetting + curated storefronts for high-value items.
- **Superior Livestock / DVAuction** → live + timed video auction events with lot catalogs (for marquee genetics).
- **Escrow.com** → funds held → inspection period (1–30 days) → buyer accepts → release; verify accounts >$3k.

### Reality check that shapes phasing
Cross-border frozen-genetics logistics is genuinely hard: APHIS import permits, 14-day embryo entry windows, IATA liquid-nitrogen dry shippers, USDA-accredited vet health certificates, Australia's 28-day donor quarantine + approved collection centres. **Decision: do NOT own LN logistics or authentication in the MVP.** Connect buyers and sellers, surface the compliance data, offer optional escrow later, and let accredited facilities + customs brokers move the goods.

---

## PART B — BREED HISTORY RESEARCH (for the "History of the Breed" section)

### Verified headline numbers (Wagyu International audited figures — most rigorous)
- **221 total** foundation Wagyu form the genetic basis of all full-blood Wagyu outside Japan.
- **188 Black** (167 live + 21 calves born after export) + **22 Red** (16 live + 6 calves).
- **183 live animals** shipped. ~26–33 were bulls → **roughly 150–170 imported females.**
- Present "~26 bulls / ~170 cows" as **approximations** anchored to these audited numbers.

### Timeline
- **1976** — first four bulls (no females), imported by **Morris Whitney** (an individual): **Mazda** (Black, Tottori/Kedaka), **Mt. Fuji** (Black, Hyogo — Fujiyoshi/Tajima), **Rueshaw** and **Judo** (both Red, Kumamoto). CSU did research/semen only; bulls bred to Angus/Hereford/Holstein in Texas; later sold to vet Dennis Wendt.
- **1991** — semen of a 5th bull, **Itotani**, to Canada (Lakeside, Alberta).
- **1993–1997** — the wave that created global full-blood Wagyu (females finally arrived, so full-blood breeding abroad became possible). Key consignments: Mannett/World K's (Michifuku, Haruki 2, Kenhanafuji, Yasufuku Jr), JVP (Fukutsuru 068, Kikuyasu-400), Takeda Farms (the TF-series incl. Itoshigenami TF148), Wood/HeartBrand (Akaushi/Red), Westholme/Chris Walker (largest female import → seeded Australia).
- **1997** — Japan declares Wagyu a national treasure and bans live/genetic export. Verified year: **1997**.

### Foundation bulls — most-influential (by Australian progeny counts, ~Aug 2020)
- **Itoshigenami TF148** — most prolific foundation sire, ~6,220 AU progeny; ~75% Tajima; marbling 8.6/9. **Photo-adjacent (breeder pages).**
- **Michifuku FB1615** — "best overall carcass bull to leave Japan," former US #1 marbling, ~5,597 AU progeny; 94% Tajima. **Photo exists (Wagyu Intl).**
- **Kitateruyasudoi "003"** (~4,101), **Itoshigefuji TF147** (~4,168), **Hirashigetayasu "001"** (~3,246), **Itohana 2** (~3,014), **Itozuru Doi TF151** (~2,632), **Itomichi 1/2** (~1,136 AU + 629 US, **photo exists**), **Fukutsuru 068** (b. 29 May 1992, verified), **Yasufuku Jr** (~908, son of famed Yasufuku J930), **Kikuyasu-400** (large Tajima outcross), **Kenhanafuji FB2461** (the "International Bull of Mystery" — see stories).
- Red/Akaushi bulls: **Rueshaw, Judo** (1976); **Shigemaru, Tamamaru, Hikari** (1994, Wood → HeartBrand).
- Only **3** foundation animals have photos on Wagyu International: **Michifuku, Itomichi 1/2, Kamui** (the Mishima bull, B115, b. 28 Aug 1991).

### Bloodlines (keito)
- **Tajima** (Hyogo) — the marbling engine; ~53.6% of avg outside genetics; foundation of Kobe. Trade-off: smaller frame/slower growth.
- **Fujiyoshi (Shimane)** — balanced marbling + maternal/milk (~5%).
- **Kedaka (Tottori)** — growth, frame, feed efficiency, yield; prized outcross.
- **Itozakura** — 2nd-most prominent abroad (~16%); growth + carcass + milk.
- **Kumamoto (Red/Akaushi)** — bigger/faster, more milk, healthier fat profile (oleic), grass-suited; lower marbling ceiling.
- Modern pedigrees linebreed Tajima for marbling, outcross to Kedaka/Itozakura to recover frame/growth/vigor and manage the ~221-animal founding bottleneck (near-universal Yasumi Doi J10328 influence).

### ⚠️ PUBLISH-READINESS CORRECTIONS (do not print the popular version)
1. **"Mikimoto"** is NOT a 1976 bull → the 4th bull is **Judo**.
2. **"Morris family / Colorado State import"** → it was **Morris Whitney** (individual); CSU only did research/semen.
3. **"Akaushi from the Takeda/WSU program"** → wrong; Akaushi came via **Dr. Al & Marie Wood → HeartBrand**; Takeda's program was **Black** Wagyu.
4. **"Terutani = TF148"** → Terutani is **TF40**; **TF148 = Itoshigenami**; **TF147 = Itoshigefuji**.
5. **Grant's recollection: "6-month quarantine on an island at LaGuardia"** → NOT supported. Documented US quarantine for the 1993 Northwest 747 (Narita→NY) shipment was **30 days in New York** (mainland USDA NYAIC, Rock Tavern/Newburgh). The **180-day (6-month)** figure belongs to the **Canada-bound red Wagyu** (Ontario). The only island import facility was **Fleming Key, FL (Truman center, closed 1998)** — its use for these Wagyu is unverified. **Do not publish the LaGuardia/island claim.** (Worth re-checking with Bruce Hemingson directly before printing his account.)
6. **"Anchorage, Alaska"** → plausible **refueling stop** on the great-circle 747 route; NOT a quarantine site.
7. **Kenhanafuji story** → DOCUMENTED that he sold for **$150,000** (highest-selling Wagyu bull ever, per breeder sources) after arriving in America; the motive "bought to control his semen" is **anecdotal inference** — label it as such.
8. **Sanjirou, WK's Shigeshigetani** → US-bred, NOT imports. **Monjiro, Shigeshigenami, Dai 20 Hirashige** → Japanese ancestral sires, not physical exports. **"Ok5"** → unverified, likely a garbled female name.
9. Don't publish specific **birth years** for Michifuku/Itoshigenami (unverified; use "c. early 1990s"). Verified: Fukutsuru 068 = 29 May 1992; Kamui = 28 Aug 1991; Shigeshigenami = 1972.

**Best single source:** Wagyu International foundation + USA pages (use working mirror `wagyuinternational.co`), corroborated by Rocking 711, Reserve Cattle Co., and Texas Monthly.

---

## PART C — MVP SPEC (buildable)

### Product principle
Simplicity is the moat. When "simple" and "feature" conflict, simple wins. Three product categories, one unified account, a Wagyu-native listing form, real search, dual ratings, and a pre-loaded foundation-bull section that makes the site authoritative on day one.

### Account model
- **One unified account** = can both buy and sell (no separate vendor/buyer accounts).
- **Two reputation scores** per account: buyer rating + seller rating, with feedback (eBay-style rolling 12-month positive % + detailed sub-scores).
- Seller verification: registry membership (American Wagyu Association / AWA-Australia number); facility-accreditation check only required to claim export eligibility.

### The three product categories (hard-wired)
1. **Semen straws**
2. **Embryos**
3. **Cloning / cell-line rights** ← the unique differentiator; the PR hook.

### Onboarding (Etsy-simple, 5 steps)
1. Create account (email, password, display name)
2. Become a seller (ranch/farm name, country/state, Stripe Connect payout, agree to terms)
3. Start a listing → product type + **sire name OR registration number** (the pre-fill hook)
4. Auto-fill + confirm (pull breed/pedigree/EPD from sire registration or a prior listing; seller edits)
5. Price & quantity (unit price, quantity + visibility toggle, fixed-price OR auction, storage location)
- **6 required fields to publish:** product type, sire name/registration, unit price, quantity available, ship-from location, agreement to health/export-representation terms. Everything else optional/enrichable. Listings are always free to create.

### Listing schema (core fields)
- **Genetics:** sire name, sire registration #, dam name/reg (embryos), breed (Fullblood Black/Red, F1–F4, Purebred), blood %, registry (AWA / AWA-AU / JP), pedigree chart, EBV JSON, EPD JSON (marbling, CW, REA, BW, WW, YW), genomic test, horn/defect status.
- **Product spec:** semen_type (conventional/sexed-F/sexed-M) OR embryo_grade + embryo_sex, straws_per_unit/cane size, quantity_available, **quantity_visibility enum**.
- **Pricing & sale:** sale_type (FIXED / AUCTION / CALL_FOR_PRICE), unit_price, bulk_tiers, min_order_qty, auction fields (start_price, reserve_price?, no_reserve bool, end_time), currency.
- **Logistics & compliance:** storage_location, ships_from_facility, **export_eligibility multiselect (AUS/EU/CAN/US-only)** tied to health_status, freight_terms, permit_notes.
- **Media:** photos/video, optional description.

### Search & filter facets (ordered by breeder priority)
1. Product type (top-level tab) 2. Breed & blood % 3. **Bloodline/lineage** (Tajima, Michifuku, Kitaguni, etc. — the killer Wagyu-specific facet nobody else has) 4. **Genetic-merit range sliders** (marbling, CW, REA, BW) 5. Sexed vs conventional / embryo grade+sex 6. **Export eligibility** 7. Price range + sale type 8. Location/ship-from + in-stock 9. Sort (relevance, price, ending-soonest, highest marbling, newest).
- Plus a **side-by-side sire comparison** view (select 2–4 sires, compare EPDs/EBVs).

### Inventory visibility control (per-listing enum)
- `EXACT` ("37 straws") · `RANGE` ("50–100") · `IN_STOCK_ONLY` ("In stock / Low / Sold out" — recommended default) · `HIDDEN` ("Contact for availability" — for whales sitting on thousands).
- Always track true quantity internally (prevent overselling); enum governs display only. Optional per-buyer purchase cap to throttle without revealing depth.

### Auctions (IN the MVP, per decision)
- **Two modes:** always-on eBay-style auctions (with Buy-It-Now option) for the long tail; scheduled live/timed **featured events** (Superior Livestock model) for marquee genetics later.
- **No-reserve "$1 start" featured auctions** actively promoted as the traffic/liquidity engine — the "come find a steal" hook.
- **Hidden-reserve** option for sellers who need a floor (bidders see "reserve not met," never the number).
- **Guardrails (must ship with auctions):** pre-authorized/required payment before lots close; funds captured on win; non-payment → strike system; shill-bid monitoring; the "as-described" dispute lever (below). Q&A the no-reserve-truly-sells-for-any-price claim in policy so "10 cents means 10 cents" is real and enforceable.

### Trust & disputes
- **Dual eBay-style feedback**: rolling 12-mo positive %, star tier, 1–5 star sub-scores adapted to genetics: item-as-described (pedigree/EPD accuracy), communication, packaging/shipping (arrived frozen), fertility/viability (optional post-breeding).
- **Verified-Storage badge** (StockX analog): listings shipping tank-to-tank from an accredited facility earn a badge — the facility is the de-facto chain-of-custody authenticator.
- **Dispute flow** (V2 with escrow): buyer opens claim in inspection window → funds frozen → evidence (tank temp logs, count/registry mismatch) → refund/partial/release. DNA parentage verification on progeny is the ultimate backstop against mislabeled straws.

### Fraud risks to design around
Non-delivery/seller default · misrepresented genetics (wrong EPDs/bloodline) · counterfeit/mislabeled straws · export-eligibility misrepresentation · cross-border payment fraud/chargebacks · shill bidding. Mitigations: registry-# verification, tank-to-tank accredited transfer, export badge gated on health_status, escrow >$3k (V2), DNA backstop, auction integrity monitoring.

### Seed content (day-one authority + SEO)
Pre-load the foundation-bull database from Part B: the ~26 black + red foundation bulls with bloodline, importer, progeny influence, and photos where available (Michifuku, Itomichi, Kamui have Wagyu-Intl photos; more on breeder pages). Plus a "History of the Breed" narrative using the verified timeline + stories (with the corrections above). Every listing links its sire's pedigree back to these profiles. This is both credibility and an SEO magnet — these bull names are searched constantly with no single good source.

### Recommended tech stack
A marketplace needs a real backend (accounts, search, payments), so this is NOT a static CF Pages site like the other windy sites. Recommended, matching the existing platform pattern for maintainability:
- **Frontend:** React/Next.js on **Cloudflare Pages** (fits the auto-deploy ecosystem).
- **Backend:** FastAPI + Postgres (matches IDKit/Streamura/facemortgage pattern) OR Cloudflare Workers + D1 for a leaner single-cloud stack. **Recommendation: FastAPI + Postgres** for the richer relational listing/pedigree schema and faceted search; add Meilisearch/Typesense for the search facets.
- **Payments:** Stripe Connect (marketplace payouts) from day one; escrow provider integration in V2.
- **Repo:** sneakyfree GitHub, new repo `wagyutank`.

### Phasing
- **MVP (0–6 mo):** unified accounts; 3 categories; full listing schema w/ registry pre-fill; real faceted search (bloodline + EPD + export); Stripe checkout; **fixed-price AND no-reserve auctions**; dual feedback + registry verification; quantity-visibility controls; ship-from-facility field; foundation-bull seed + breed history.
- **V2 (6–15 mo):** optional escrow w/ inspection period; scheduled live auction events; Verified-Storage/Verified-Seller badges via facility partnerships (Trans Ova, Premier Reproductive Services, Global Reproduction Solutions AU); sire comparison tool; structured disputes; seller storefronts.
- **V3 (15+ mo):** GunBroker-grade accredited-facility network (select receiving facility at checkout); assisted export (customs brokers, dry-shipper partners, permit tracking); cloning-rights licensing contracts + royalties; DNA parentage verification program; equipment/tank + cryo-storage sub-marketplace; vet-services directory; the on-farm "collection-and-freezing kit" farmer-in-a-box package.

---

## Registry auto-fill (type reg# → pedigree pre-fill) — feasibility (2026-07-05)

**Premise shifted:** The American Wagyu Association **left DigitalBeef/701x ~June 2026** and migrated to **Helical** ("genetics operating system," helicalco.com, founder Dan Garrick). `wagyu.digitalbeef.com` is now a dead placeholder. So the integration target is **Helical, not DigitalBeef** — which is *better* for us: Helical is an API-first JSON platform that productizes "Integrations & APIs."

**One integration covers the world:** Both **US AWA** (`americanwagyu.helicalco.com`) and the **Australian AWA** (`awa.helicalco.com`) are on Helical. Most European fullbloods register *through* AWA-Australia. So a single Helical integration = the bulk of both major registries globally. (AU genetics engine is Single-Step BREEDPLAN via ABRI/AGBU; legacy ABRI `i4.dll` enquiry still exists but is being superseded.)

**The data is behind a walled JSON API:** `GET https://americanwagyu.helicalco.com/api/public/i/animal/search?q=<regno>` returns `401 — API Key must be supplied in X-API-KEY header`. Public search is a SvelteKit SPA behind a Cloudflare `/public/validate` gate that mints a rotating session key. **Scraping is hostile + against ToS**: robots.txt explicitly Disallows crawlers incl. ClaudeBot and CloudflareBrowserRenderingCrawler, and invokes EU 2019/790 Art. 4 data-reservation. Do NOT build on scraping.

**Path (ranked):**
- **(a) Official Helical partner API key + AWA blessing — PURSUE FIRST.** Low-moderate engineering (REST to `/api/public/i/animal/search` + `/animal/<id>` + `/pedigree`), gated on a business conversation (~1–8 wks). This is the durable "type FB# → auto-fill verified pedigree/EPDs" feature done right, and it makes the data *registry-verified*, which is also a trust badge.
- **(c) Manual-assisted fallback for day one:** seller types reg#, deep-link to the official Helical detail page, seller pastes pedigree OR uploads the AWA registration certificate PDF (OCR/parse). Show "seller-provided, not yet registry-verified" badge; swap in the API feed once (a) lands. Ships now, zero legal risk.
- **(b) Scraping — do NOT; ToS/robots violation + Cloudflare cat-and-mouse + burns the partner relationship.**

**First concrete steps (this week):**
1. Email **Helical** (`helicalco.com/contact`, Dan Garrick's team): request read-only partner API key to look up animals by registration# for AWA-US and AWA-AU tenants and auto-fill pedigree/EPDs.
2. In parallel, email/call **AWA** (`office@wagyu.org`, +1 208-262-8100) for their blessing + intro to their Helical rep; pitch WagyuTank as a verified-sales/lead channel that keeps AWA reg numbers front-and-center. AWA sign-off unlocks the Helical key for their tenant.

**Verified endpoints:** US public search `https://americanwagyu.helicalco.com/public/i`; AU `https://awa.helicalco.com/public/i`; walled API `https://americanwagyu.helicalco.com/api/public/i/animal/search?q=<regno>` (needs X-API-KEY).

## Smart Listing — permission-INDEPENDENT auto-fill (2026-07-05, primary design)

**Decision: do NOT depend on AWA/Helical.** The association is slow + risk-averse + may want $$$; treat any API deal as a bonus upgrade, not a dependency. Grant's instinct (seller does the lookup, we do the rest) is correct — build that.

**Why fully-automatic pull is blocked (it's technical, not legal):** For black fullblood Wagyu (FB#s) the live registry is now **Helical**, a JS SPA whose data sits behind an `X-API-KEY` + Cloudflare gate — the data is NOT in the page HTML, so our server can't read it even one page at a time. The seller's *browser* can read it; our *server* can't. (Old DigitalBeef was server-rendered HTML and readable; Akaushi/red Wagyu is still on DigitalBeef.) iframing the registry search is blocked by X-Frame-Options/CSP + same-origin (can't extract data from a cross-origin iframe). So the "last inch" must happen in the seller's browser or via seller-supplied data.

**Legal read:** pedigree = facts (not ownable; Feist). A seller providing info/certs about their OWN animal = clean. Bulk scraping by us = ToS/robots violation (Helical invoked EU 2019/790 Art.4; robots blocks crawlers) AND technically blocked. So the winning design has the SELLER supply the data — legally bulletproof and technically unblocked.

**The Smart Listing flow (needs zero permission):**
1. Seller picks product type (semen/embryo/clone) + enters registration number.
2. **Get pedigree from seller, best option first:**
   - (a) **Upload registration certificate PDF** (seller owns it; authoritative) → AI OCR/parse fills all fields. THE WINNER — better than an API pull (source-of-truth doc).
   - (b) **Paste pedigree** — deep-link seller to their animal on the correct registry (Helical=black FB, DigitalBeef=Akaushi/red, ABRI/Helical-AU=Australia), seller copies pedigree block, pastes into one box → AI structures it.
   - (c) **Browser add-on (Phase 2)** — one-click grab off the animal's page in the seller's own browser (legal + unblocked); nicety for high-volume sellers, not a dependency.
3. **AI auto-writes the whole ad** from pedigree + photo (marquee value-add, 100% in our control, no permission).
4. **Trust w/o a data deal:** every ad carries a **deep link to the animal's public registry page** → buyer self-verifies against source of truth in 2 sec. Badge = "Seller-provided · verify at registry."
5. **Auto-upgrade path:** if Helical API deal lands later, listings silently gain a green "Registry-verified ✓" badge and cert-upload becomes optional. API = upgrade, never dependency.

### The mobile "phone in Paris, no papers" scenario — how it actually works
**Hard wall to be honest about:** WagyuTank's code can NEVER read another website's tab (browser same-origin policy — bedrock security, desktop AND mobile). So "seller clicks link, it opens the registry, and WagyuTank reads it from there" is categorically impossible from a web app. On top of that, Helical hides the data behind an API key even from a direct URL fetch. There are exactly TWO ways across the wall: (1) get the key (permission), or (2) capture the data in the seller's OWN view. Everything else is a variant. Cert-PDF is capture-in-seller-view; so is screenshot/paste. (A native-app in-app WebView could inject a reader script — but that's scraping-in-disguise: ToS/Cloudflare cat-and-mouse + requires an app. Not the starting path.)

**Winning combo for the no-papers/mobile outcome (all permission-free):**
- **A. Foundation animals = instant, zero lookup.** We pre-build the full DB for the ~26 foundation bulls + famous descendants. Seller types "Michifuku"/FB1615 → full pedigree + AI write-up, no registry touch. Covers a large share of high-value semen listings (foundation genetics = what people actually sell/search).
- **B. Cache/learn flywheel.** The first time ANY seller lists an animal (via screenshot/cert/paste), we parse + store that pedigree. Every later seller of that same FB# gets it **instant from our own DB** — no lookup. The site gets more magical as it grows; 100% permission-free (sellers gave us the data). Turns cold-start into a compounding asset.
- **C. New/unknown animal = one screenshot (the mobile hero, reframed).** On a phone the seller is already looking at the pedigree on the Helical page; a 2-button screenshot is a reflex (less work than typing anything), they attach it (or share-sheet it to WagyuTank), our multimodal AI reads the whole pedigree in ~2s + writes the ad. Accept via share target too. Screenshot on mobile is elegant, not the clunky desktop "find a file" he pictured.
- **D. Red Wagyu / other DigitalBeef breeds = true URL paste.** DigitalBeef is server-rendered HTML, so seller pastes the animal's URL → our server fetches + parses (works for Akaushi/red + non-Wagyu breeds; NOT Helical/black-FB).

**Confirm + role-assign dialog (build regardless of capture method):** after capture, show "We found FB137246 · Sanda 5023 — use as: semen animal / sire of embryo / dam of embryo / clone source?" (embryos need BOTH sire + dam). The role picker + confirm is fully ours; only the SOURCE of the identity (screenshot/cache/cert) differs, never a silent registry read.

## Compute / AI cost strategy (2026-07-05)

**Not a cost problem — don't let it shape architecture.** Reading a pedigree screenshot (vision OCR → structured JSON) costs ~a fraction of a cent (cheap tier: Haiku/Gemini-Flash/GPT-mini class) up to ~a nickel (frontier). AND we pay **per UNIQUE animal, once** (cache flywheel), not per listing; foundation animals = zero AI (pre-built DB). So real footprint ≈ number of distinct animals ever listed. Even 50k unique animals ≈ $50–$2,500/yr total — a rounding error vs marketplace fees. **Optimize for quality + speed + reliability, not price.**

**Split the two AI jobs (the real decision):**
- **Job 1 — pedigree extraction from screenshot** = accuracy-critical, trust-critical, latency-sensitive (Paris, ~2s, must not flake). → **Pay for a frontier/strong vision API.** Use structured-output/JSON-schema (Claude tool-use or equivalent) so fields come back clean. Human-confirm dialog (seller verifies "yes, Sanda 5023, right sire") is the accuracy backstop → a strong-but-cheap tier is safe; wrong reads caught before publish. Optional cheap insurance: 2-model cross-check on the SIRE field for high-value lots.
- **Job 2 — ad copy generation** = creative, forgiving, regenerable (seller edits if meh). → **Perfect for free/cheap compute** (Windy Mind, or eventual self-host). If output is mediocre, no harm.

**On Windy Mind (Grant's free-compute marketplace):** great fit for Job 2 and as an eventual cost-optimizer + dogfooding — but do NOT put a free-tier aggregator in the CRITICAL PATH of the hero UX moment (first-listing extraction). Free tiers rate-limit, vary in quality, and go down; the seller's first listing is the one moment flakiness is unaffordable. Use it where latency/quality slack exists.

**Self-host GLM/open vision model (Grant has GPU on Veron 1, 10.10.0.6):** viable long-term for sovereignty/dogfooding, but economics don't justify it here — you'd spend ops effort to save lunch money. Do it for principle, not the bill.

**Warm-up recommendation (Grant's instinct = correct):** launch Job 1 on a frontier vision API for high quality + reliability from day one (pennies); route Job 2 to Windy Mind; revisit self-host only when principle/volume justifies.

## Open items for Grant
- Take rate / commission (research didn't pin competitor benchmarks — decide our %).
- Named accredited facilities to pre-onboard for the V2 Verified-Storage badge (Trans Ova, Premier Reproductive Services, Global Reproduction Solutions surfaced as candidates).
- Re-check the Bruce Hemingson transport/quarantine account against the documented 30-day-NY / 180-day-Canada facts before printing.
- Confirm build trigger: when ready, next step is scaffold repo `wagyutank` (sneakyfree) + FastAPI/Postgres backend + Next.js/CF-Pages frontend.
