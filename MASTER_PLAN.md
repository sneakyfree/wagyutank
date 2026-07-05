# WagyuTank.com — Master Plan (the DNA Strand)

**Version:** 1.2 · **Date:** 2026-07-05 · **Owner:** Grant Whitmer
**Domain:** WagyuTank.com (Cloudflare) · **Repo (planned):** sneakyfree/wagyutank · **Sister site:** wagyusale.com (dedicated auction house — see §19)
**Companion doc:** `SPEC.md` (detailed research + schema). This is the holistic genome; SPEC.md is the lab notebook.
*v1.1 changelog at the end.*

---

## 0. North Star

**WagyuTank.com is the world's preferred marketplace for frozen Wagyu genetics — semen, embryos, and cloning/cell-line rights — and the global headquarters of the trade.** We win on three things at once:

1. **The most friction-free way on Earth to list, sell, and get paid** for frozen Wagyu genetics. *A grandma on her phone in a Paris café lists Michifuku semen in 60 seconds, never writes the ad, and shares it to Facebook with one thumb.*
2. **A lifetime brand-building partner for every ranch, breeder, feedlot, and operation** — their WagyuTank storefront is their public persona, reputation, and marketing engine, the way an Amazon store or eBay seller page is (§4).
3. **A truly global venue** — built for Australia, Europe, South America, and beyond from day one, because Wagyu is growing everywhere (§12).

**Three product categories (invariant, co-equal):** ① Frozen semen straws · ② Frozen embryos · ③ Cloning / cell-line rights (the differentiator nobody else has — a full third line, same transaction shape as a straw; see §7B).

**Business model:** Free to list, forever. 0% commission at launch (rails wired, set to zero). Revenue = flat-fee featured placements first, then on-site advertising. Ad space designed in from day one, filled with house promotion until traction.

---

## 1. Product Principles (the genes — never violate)

1. **Simplicity is the moat.** When "simple" fights "feature," simple wins.
2. **The seller never does clerical work a computer can do.** Pedigree, ad copy, photos, shipping, translation — we generate or pre-fill all of it.
3. **One account, buys and sells** (Amazon/eBay/Shopify). No vendor/buyer split.
4. **Don't reinvent solved wheels.** Auctions = eBay. Onboarding/payments = Shopify/Stripe. Ratings = eBay/Amazon. Creativity is spent only on the Wagyu-native magic.
5. **Free to list; monetize attention, not transactions** (until scale).
6. **Trust without gatekeeping.** We're a venue, not a warranty. We make verification trivial (registry link, badges, dual ratings) rather than guaranteeing genetics ourselves.
7. **Mobile-first, one-thumb, normie-first.** If it doesn't work one-handed on a phone for someone who's never sold genetics, it's wrong.
8. **The Animal is the atom.** Every registration number is ONE canonical record (pedigree, photos, videos, history) that listings, offers, cache, registry pages, and SEO all hang off of. Build this spine once and half the features fall out for free (§8, §18).
9. **A marketplace needs gravity, not just supply.** Beautiful listings with no buyer pull or return loop is a ghost town. Invest equally in demand-side discovery and retention (§8).
10. **Global by default.** Currency, language, registry, and shipping are variables from line one, not a US product with international bolted on later (§12).

---

## 2. The Killer Flow — 60-second listing (the core DNA)

The whole company in one screen sequence. Everything else supports this.

1. **Tap "Sell."** Pick category: Semen / Embryo / Cloning rights.
2. **Identify the animal.** One **universal input** accepts: a registration number, a name, a pasted screenshot, a photo of a paper pedigree, or a cert PDF — AI figures out what it got. The number is format-validated and auto-routes to the right registry (FB… → US Helical; AU idents → ABRI; Akaushi → DigitalBeef). Fuzzy match catches typos ("did you mean Michifuku FB1615?").
   - **Foundation animal / already-listed?** → instant from our own **canonical Animal record** (foundation DB or cache). Zero lookup.
   - **Brand-new animal?** → seller opens their animal on the deep-linked registry and **drags in a screenshot** (or shares it to us via the phone share sheet). Vision AI reads it in ~2s. (§9 explains why capture, not silent pull.)
3. **Confirm + assign role.** "We found **FB137246 · Sanda 5023** — use as: the semen animal / sire of the embryo / dam of the embryo / clone source?" (Embryos need both sire and dam.)
4. **AI writes the ad** from pedigree + photo; seller edits or regenerates. Registry link, history, and canonical animal page auto-attached.
5. **Price it.** Fixed price *or* simple auction (reserve / no-reserve — eBay mechanics), in the seller's **currency** (§12). Quantity + visibility toggle (§7).
6. **Storage & shipping auto-defaults** (§6): pick the facility from a **typeahead directory** ("Ha" → Hawkeye). "It stays at [facility]; when it sells they ship, buyer pays at cost — you don't handle logistics."
7. **Publish + share** with one thumb (§13).

**Never block publish on pedigree.** If the seller has only a reg number and a price (driving, no screenshot handy), let them publish a **lite listing now**; the pedigree auto-enriches later from cache or when they add a screenshot. A live listing beats a perfect one that never posts.

**Result:** typed a number, maybe dragged one screenshot, tapped confirm, set a price, hit share. Under a minute. Never wrote a word or hunted a fact.

---

## 3. Accounts & Identity (minimal friction, still covered)

Model: Amazon/eBay/Shopify — **escalating verification tied to action**, not a wall at signup.

- **Create account (browse/watch/follow/save):** email + password (or Google/Apple SSO) + display name. Verify email. Anti-bot = email verify + rate limits + hCaptcha. *(Requiring a card just to sign up is MORE friction than Amazon/eBay impose — gate it to transaction time.)*
- **To SELL / get paid:** onboard **Stripe Connect Express** — one step that both pays them and does KYC (real human/business). We store no payment PII; Stripe does.
- **To BID / BUY:** payment method on file → verifies human, auto-charges auction winners.
- **CYA at listing time:** accept ToS + **seller representations** (own/authorized to sell; pedigree accurate; will honor sale). Timestamped, versioned.

**Trust badge ladder (visible + earnable):** Email-verified → Stripe-verified seller → Registry-linked listing → (later) Registry-API-verified → Facility-verified storage. Gives sellers a ladder to climb and buyers a signal to read.

**Ratings:** one profile, **two scores** (seller + buyer) with feedback and genetics-specific sub-scores (as-described/pedigree accuracy, communication, arrived-frozen, optional fertility/viability).

---

## 4. Seller Storefronts & Brand Persona (a core pillar, basic version in MVP)

*This is elevated from a V2 afterthought to a first-class pillar — it's how WagyuTank becomes a lifetime partner, not a classifieds board.*

- **Every seller gets a public storefront** at a clean custom URL (`wagyutank.com/rockingw` or a chosen handle): logo + banner, ranch bio + location + story, all their active listings and auctions, their ratings/feedback, and their verification badges. It's their Amazon-store / eBay-seller page.
- **Shareable + SEO'd** — the storefront is its own marketable asset; a ranch can put "find our genetics at wagyutank.com/rockingw" on a business card, and it ranks.
- **Follow a ranch.** Buyers follow storefronts and get notified of new listings/auctions — retention + repeat demand (§8).
- **MVP scope = the basic public profile** (handle, branding, listings, ratings, follow). Richer storefront theming, custom domains, and vendor tiers come later. Cheap to ship because a seller profile page *is* a storefront.

---

## 5. Payments (Stripe)

- **Stripe Connect Express** for direct seller payouts; WagyuTank never holds funds or stores card/bank PII.
- **Buyer pays the Stripe fee**, grossed up to fully cover ~2.9%+30¢ (we never go negative). Framed as a familiar **"buyer's premium"** — normal in livestock auctions.
- **0% platform commission at launch**, but the take-rate is wired via `application_fee_amount` (a config value) so it can flip to any % later with zero rebuild.
- **Multi-currency (§12):** sellers price in their own currency; Stripe handles presentment/settlement across AUD, EUR, BRL, GBP, USD, etc.
- **Auctions:** payment method required to bid; winner auto-charged (kills no-pay fraud).
- **Optional escrow, available earlier for high-value/cross-border:** not built by us — integrate a provider (e.g., Escrow.com) as an opt-in toggle above a threshold (say, transactions over ~$5k or international). The highest-value stranger-to-stranger deals are exactly where "venue, as-is" is weakest; give them a safety option without making everyone use it.

---

## 6. Storage, Shipping & the Facility Directory (the industry already works our way)

**Key finding:** frozen genetics live in liquid-nitrogen tanks at third-party facilities in a per-owner inventory account. **The seller doesn't ship — they instruct the facility, and the buyer pays shipping at cost.** Our default just formalizes reality.

**Seeded Facility Directory (typeahead, the concrete feature):** pre-populate the major crossroads so a seller types "Ha" and picks **Hawkeye Breeders (Adel, IA)** — never hand-typing. Seed set (verify exact roster):
- **US:** Hawkeye Breeders (Adel, IA) · Trans Ova Genetics (Sioux Center, IA + satellites) · Bovine Elite (College Station, TX) · Champion Genetics (Canton, TX) · Elgin Breeding Service (Elgin, TX — east of Austin) · Great Lakes Sires (MI) · SEK Genetics (Galesburg, KS) · ORIgen (Huntley, MT) · ST Genetics (Navasota, TX) · Genex/URUS · Premier Reproductive Services.
- **Global (for §12):** AU — Agri-Gene, Genetics Australia, ABS Australia; Brazil/South America and EU centers curated per region.
- **Cloning companies (for §7B clone-rights):** ViaGen / Bovance (Austin, TX + Trans Ova, Sioux Center, IA), Clone International (AU), In Vitro Brasil (BR). A facility can offer multiple services — Trans Ova is storage + embryos + cloning at once, so `facility` carries a `services` list, not a single type.
- Each entry carries **name + location + geocode** (drives tank-to-tank matching, local-pickup radius, and shipping estimates). Sellers can **add a facility if missing** (light moderation), and on-farm-tank is an option too.

**Default shipping model (pre-filled; seller just confirms):** *"Your genetics stay at [facility]. When you sell, [facility] ships to the buyer and the buyer pays shipping at cost — you don't handle logistics."*
- Facility ships on the seller's **written release** — WagyuTank generates the signed release/authorization at checkout (the de-facto transfer instrument).
- Buyer pays: freight + handling/release (~$25–35) + per-unit transfer (~$10) + **dry-shipper rental** (MVE SC 4/2V vapor shipper, ~10–13 day hold, IATA-compliant UPS/FedEx overnight; ~$580 all-in; ~$700 refundable deposit; daily late fee).
- **Tank-to-tank / local pickup auto-offered** when buyer and seller share (or have nearby) facilities — cheapest, zero-thaw path.
- **Buyer attests** they can receive (account + LN2 tank/AI-vet) — closes the #1 failure (thaw).
- Full field list in SPEC.md.

---

## 7. Listings: fixed-price + SIMPLE auctions (eBay parity; heavy auctions live at wagyusale.com)

- **Sell types:** Fixed price · Simple auction (reserve or **no-reserve**) · (later) Make-Offer.
- **Auctions = don't reinvent eBay:** start price, optional hidden reserve, duration, last-minute auto-extend, proxy bidding, watchlist, ending-soon alerts. Promote **no-reserve "$1 start"** lots as the steal-hunting traffic engine.
- **Scope boundary (streamlining):** WagyuTank runs only lightweight **always-on eBay-style auctions as a listing format.** Dedicated/scheduled **live and in-person auction events** (Superior-Livestock-style, catalogs, ring, video) are **wagyusale.com's job** (§19), NOT WagyuTank's. This keeps WagyuTank simple and avoids duplicate build.
- **Guardrails:** pay-to-bid, winner auto-charged, non-payment strikes, shill monitoring.
- **Quantity visibility toggle:** EXACT / RANGE / IN-STOCK-ONLY (default) / HIDDEN. True count tracked internally; enum governs display only. Optional per-buyer cap.

---

## 7B. Cloning / Cell-Line Rights — the third product line (full MVP, not staged)

*Grant's correction (correct): a clone-right is structurally identical to a straw — a banked asset with one owner who alone can authorize its release. It's arguably SIMPLER than semen (nothing frozen ships to the buyer). Fold it in as a co-equal line.*

- **The asset:** a cryopreserved **cell line** banked at a cloning company (tissue → cultured into millions of cells → frozen). Cloneable effectively unlimited times.
- **The owner** of the cell line is the ONLY party who can authorize a clone — exactly like the owner of straws is the only one who can release them.
- **The listing:** "Rights to clone [animal]." Seller sets how many clone-rights to sell and the price per right; **exclusivity is a first-class option** ("exclusive — the only clone ever made" vs. one of many) and a premium pricing lever. The quantity-visibility toggle governs how many rights are shown vs. held back — same mechanic as hiding straw depth.
- **Two-part cost, always disclosed (the one thing that makes it correct):** the **rights fee** (to the seller, transacted on WagyuTank) + the **cloning company's production cost** (paid to the lab to actually gestate and birth the calf; historically ~$15–20k for bovine). Buyer sees both and the total up front — no surprise. WagyuTank's transaction is the *rights*; the buyer arranges production with the named lab (parallel to how a semen buyer arranges receiving with the storage facility). Example: $10,000 rights to one Fujiko clone + ~$20,000 ViaGen production = buyer knows the ~$30k all-in.
- **Authorization document:** WagyuTank auto-generates a **Clone Rights License / Authorization** (seller grants buyer the right to N clones from cell line [ID] at [lab]; seller notifies the lab) — the same template mechanism as the semen shipping-release, not a bespoke legal negotiation.
- **Facility = cloning company** (directory §6): **ViaGen** (Austin, TX; livestock cloning leader; a Trans Ova division, recently acquired by Colossal Biosciences) and its bovine JV **Bovance**; **Clone International** (Australia); **In Vitro Brasil** (South America). "Cell line banked at ViaGen" = a verified-storage trust badge, like "stored at Hawkeye."
- **Expectation disclosure:** a clone is a live birth months out via surrogate, with biological variability and no absolute guarantee (ViaGen cites ~80% success). Plain-language note on the listing; not a blocker.
- **Net:** semen, embryos, and clones are three co-equal lines. The only clone-specific additions are the two-part cost disclosure, the exclusivity/quantity semantics, the license-doc template, and the live-birth disclosure — all schema/copy, zero new architecture.

---

## 8. Demand-Side Gravity & Retention (the missing half — now first-class)

*A listing tool becomes a marketplace only when buyers arrive and both sides come back. This is the engine for that.*

- **Canonical Animal pages.** Each registration number is one public page — pedigree, photos, videos, history, and **every live offer for that animal aggregated**: *"Michifuku (FB1615) — 12 sellers offering semen from $70/straw."* Buyers compare offers; sellers get discovered; Google gets a page that ranks. This falls out of Principle #8 for free and is the biggest SEO and buyer-discovery lever in the plan.
- **Saved searches + alerts (in MVP).** "Notify me when sexed Tajima semen under $X is listed." Cheap to build, and it's the return-visit hook a marketplace lives on.
- **Follow graph.** Follow a ranch (§4), a bloodline, or an animal → email/push when something new matches. Turns one-time listers into a returning audience.
- **Want-ads / buyer requests.** A buyer posts "looking for Itoshigenami embryos, marbling EPD > X"; sellers see live demand and can respond. Creates liquidity from the demand side, not just supply.
- **Watchlists + ending-soon / outbid notifications** (auction standard) round out the re-engagement loop.

---

## 9. Pedigree Auto-Fill & Compute (the magic, honestly)

- **Why capture, not silent pull:** browsers forbid one site reading another's page (same-origin), and the US fullblood registry (Helical) hides data behind a key even from a direct fetch. So data is captured in the seller's own view (screenshot/cert/paste) or via an official API (a bonus we don't count on).
- **Four sources, best first:** ① Foundation DB → ② Cache (canonical animal) → ③ Screenshot + vision AI → ④ URL-paste for DigitalBeef breeds.
- **Compute is not a cost problem.** Fractions of a cent to a few cents per read; **paid per unique animal once** (cache), foundation animals free. Even 50k unique animals ≈ $50–2,500/yr.
- **Two AI jobs, split by stakes:** Job 1 **pedigree extraction** (accuracy/latency-critical) → strong commercial vision API with JSON-schema output, seller-confirm as backstop. Job 2 **ad copy + translation** (forgiving/regenerable) → **Windy Mind** free-compute. Never put free compute in Job 1's critical path. Self-host GLM later for sovereignty, not economics.

---

## 10. Content Engine: Registry, Photos, Videos, History

The day-one authority, the SEO moat, a long-term asset — and it IS the canonical Animal graph (§8).

- **Foundation & registry database.** Pre-load the ~26 foundation bulls + foundation cows + famous descendants (bloodline, importer, progeny influence, photos). Corrections in SPEC.md (Morris Whitney not "Morris family," Judo not "Mikimoto," LaGuardia-island quarantine unverified).
- **History of the Breed** — rich, cited narrative anchored to Wagyu International's audited 221-animal figures.
- **Photo harvesting — copyright-safe (do not skip).** Harvest FB-matched images into an **internal candidate index** (source + attribution); **do not auto-publish.** Suggest to the animal's verified owner to confirm/license; prefer seller-uploaded photos (ToS license); public-domain/press tier is lower risk; DMCA/takedown path. A suggestion engine, not a republisher. Re-crawl periodically.
- **YouTube/social video embeds** (allowed — embedding, not copying); match FB-numbered videos to animals; one-click embed into ads.

---

## 11. Search & Discovery

- **Facets by breeder priority:** product type → breed & blood% → **bloodline/lineage** (the killer facet) → **genetic-merit range sliders** (marbling, carcass wt, ribeye, birth wt) → sexed/conventional or embryo grade+sex → **export eligibility** → price + sale type → location/ship-from → in-stock. Sorts incl. ending-soonest, highest-marbling.
- **Side-by-side sire comparison** (2–4 animals, EPD/EBV table).
- **Engine:** Meilisearch/Typesense.

---

## 12. Global / International (built in, not bolted on)

*"Global HQ" has to be true on day one, cheaply, where it's cheap.*

- **Multi-currency (MVP):** sellers price in their own currency; buyers see it (and optional converted view). Stripe handles it.
- **AI listing translation (MVP-ish, near-free with our AI):** auto-translate any listing into the buyer's language on view (cache the translation). A Brazilian buyer reads an Australian seller's Michifuku listing in Portuguese. Huge, cheap differentiator for a global marketplace — nobody in this niche does it.
- **Multi-registry from launch:** US (Helical), Australia (ABRI/Helical); EU fullbloods largely register via AU AWA. Reg-number routing already handles this (§2).
- **Global facility directory + transportation solutions (§6):** seed AU/EU/South-America storage/collection centers; surface cross-border dry-shipper + customs-broker guidance and (later) partners. Export eligibility is a first-class listing facet and filter.
- **Target regions:** Australia (largest herd outside Japan), Brazil/South America (fast-growing), EU/UK. Localize currency, language, and facility options per region.
- **Hard logistics (health certs/permits) stay "surfaced, not owned"** early; assisted-export partnerships are a later, traction-gated upgrade.

---

## 13. Social Distribution (do it right, but stage it)

- **MVP — share intents + rich cards (90% value, ~5% effort, zero platform approval):** one-thumb share to Facebook/X/WhatsApp/Instagram (native share sheet)/TikTok/email/copy-link. Every listing + storefront + animal page renders beautiful **Open Graph / Twitter cards** so a pasted link auto-unfurls anywhere.
- **V2 — first-party API posting** (auto-post/schedule to connected accounts). Honest flag: Meta/TikTok/X posting APIs need app review + policy compliance — real work, not a checkbox.
- **Inbound embeds:** YouTube/FB/IG videos into ads (§10).

---

## 14. Seller Analytics

The dashboard breeders have never had: views, unique viewers, watchlist/follow adds, click-throughs to registry, shares, bids over time, and **traffic source by social channel.** Delights sellers and creates the appetite for paid promotion (§15).

---

## 15. Monetization (built in from day one, dark until traction)

- **Phase 0 (launch): free everything; ad slots run house promotion.** Design banner/hero/featured inventory into the layout now.
- **First revenue — flat-fee "Featured" placements (DECIDED, not a bid auction yet):** one-tap "Feature this listing," pick duration, pay a fixed price (placeholders: homepage hero $19/wk, top-of-bloodline-search $12/wk, auction bump $5). Normie-simple; auctions need slot scarcity that won't exist early; days to build vs. months.
- **Evolution — simplified sealed-bid slot auction only when slots get contested** ("N hero slots this week; name your price; top N win").
- **Separate later product — third-party display advertising (CPM):** banner inventory to genetics-adjacent advertisers once traffic exists. Different from seller self-promotion.
- **Later (optional):** flip the 0% platform fee; premium storefront/vendor tiers; escrow fees.

---

## 16. Growth & SEO Flywheel

- **Canonical Animal pages + foundation profiles + breed history** = an SEO magnet for searches with no good source today; each cross-links to live offers.
- **Cache flywheel** makes the product more magical as it's used.
- **Storefronts + social sharing** turn every seller into a distributor and a landing page.
- **Saved searches + follows + want-ads** bring both sides back.
- **Free + effortless** is inherently viral in a tight-knit, chatty breeder community.

---

## 17. Legal / Compliance / CYA

- **Posture: venue, not warrantor** (early). ToS disclaims genetic quality/authenticity/fertility liability; buyer-beware + verify-at-registry; seller representations (§3).
- Prohibited-use + content policy; dispute/feedback process; strikes.
- **Export compliance surfaced, not owned** — flags + APHIS/DAFF links; export via qualified centers.
- **Photo IP** — the candidate-index/owner-confirm/DMCA design (§10).
- **PII minimized** — Stripe holds payment KYC; standard privacy policy; note cross-border data (GDPR/AU) for a global user base.
- **Registry data** — seller-supplied facts are clean; no bulk registry scraping.

---

## 18. Tech Architecture

- **Frontend:** Next.js (React), mobile-first, Cloudflare Pages. Rich OG/Twitter cards per listing/storefront/animal.
- **Backend:** FastAPI + Postgres (matches ecosystem pattern; relational fit). Meilisearch/Typesense for search. Redis for sessions/queues/alerts.
- **Data spine — the canonical Animal (Principle #8):** `Animal(registration_no PK)` ← Listings, Offers, Photos, Videos, PedigreeEdges, History all reference it. Cache, foundation DB, registry pages, multi-seller aggregation, and SEO pages are all *views* of this one table. Get this right first.
- **AI:** commercial vision API (Job 1) + Windy Mind (Job 2: copy & translation).
- **Payments:** Stripe Connect (Express), multi-currency.
- **Media:** Cloudflare R2 (images, screenshots, cert PDFs).
- **Repo:** sneakyfree/wagyutank; Actions → CF Pages (frontend); backend on a fleet box or VPS (per machine-split). Ad slots are first-class layout components.

---

## 19. wagyusale.com — Sister Auction House (scope boundary + seam)

Grant owns **wagyusale.com** as a **separate platform specialized in online + in-person auction events.** Keep the split clean:
- **WagyuTank.com** = always-on marketplace (fixed-price + simple eBay-style auctions), storefronts, discovery. The "eBay/Amazon."
- **wagyusale.com** = curated/scheduled **auction house** (live ring, in-person + online, lot catalogs, video, timed sale events). The "Superior Livestock / auction company."
- **Build WagyuTank standalone NOW (Grant's call).** Do NOT design the cross-platform seam yet. The *only* thing we carry forward today is the scope discipline: keep heavy/live-auction machinery OUT of WagyuTank (§7) so a future wagyusale.com has a clean lane. When wagyusale.com is actually started, we'll design the shared-login / cross-post seam then — not now.

---

## 20. Build Phasing (growth stages of the organism)

**MVP — "the marketplace that actually works" (0–4 mo)**
Unified accounts (email → Stripe Connect to sell → card to bid) + trust-badge ladder; **all three lines fully — semen, embryos, AND cloning/cell-line rights** (§7B; a clone-right is the same owner-authorizes-release transaction as a straw); the 60-second flow (universal input, foundation DB + cache, screenshot AI, AI ad-writing, progressive/lite publish); **canonical Animal pages + multi-seller aggregation**; fixed-price + simple no-reserve auctions; dual ratings; quantity-visibility toggle; **basic seller storefronts + Follow + saved-search alerts**; storage/shipping default + **seeded facility directory** + release generation; faceted search + sire compare; **multi-currency + AI listing translation**; History-of-the-Breed + foundation seed; share-intents + OG cards; basic analytics; house-ad slots; verify-at-registry links.

**V2 — "trust, distribution & first revenue" (4–10 mo)**
Flat-fee featured placements (first $) + preferred ranking; optional escrow for high-value/international; verified-storage badges via facility partnerships; first-party social API posting; photo candidate-index/owner-confirm library; want-ads/buyer-requests; richer storefront theming + analytics; wagyusale.com SSO + cross-post seam.

**V3 — Opportunity Backlog (traction-sequenced, NOT a committed sprint)**
Pull forward by demand, defer the rest explicitly: Registry API integration (Helical/AWA) → auto-verified badges; accredited-facility receiving network (select-a-facility at checkout); assisted export (customs/dry-shipper partners, permit tracking); equipment/tank + cryo-storage sub-marketplace; on-farm collection-and-freezing kit ("farmer-in-a-box"); vet-services directory; display-ad (CPM) network; custom storefront domains + vendor tiers.

---

## 21. Open Decisions for Grant

1. ✅ Stripe fee → buyer pays (buyer's premium); 0% platform fee wired dark.
2. ✅ Featured model → flat-fee first; sealed-bid later; CPM display separate/later.
3. ✅ Photo approach → candidate-index + owner-confirm + DMCA.
4. **Flat featured prices** — confirm/adjust placeholders (hero $19, bloodline-search $12, bump $5).
5. **Backend hosting box** (fleet machine vs. VPS).
6. **Custom storefront handles** — reserved-word/impersonation policy (e.g., can someone grab "michifuku"? reserve foundation/brand names).
7. **AWA/Helical outreach** — proceed as a bonus; don't gate the build.
8. ✅ wagyusale.com → **build WagyuTank standalone now**; no cross-platform seam designed yet; just keep heavy/live auctions out of WagyuTank for a future clean lane (§19).
9. ✅ Cloning/cell-line → **full third product line in MVP** (§7B), not staged.

---

## 22. Honest Risk Flags

- **Demand-side cold start** — the new §8 engine (animal pages, alerts, follows, want-ads) is the antidote; don't let it slip out of MVP or you ship a beautiful ghost town.
- **Scope creep from elevating storefronts/global** — keep MVP versions *basic* (a profile page, a currency field, on-view translation); resist gold-plating.
- **Photo scraping copyright** — mitigated by §10; do not skip.
- **Social auto-posting APIs** are heavy — MVP uses share intents.
- **Auction fraud on a free platform** — mitigated by pay-to-bid + auto-charge.
- **Buyer-can't-receive thaw** — mitigated by attestation checkbox.
- **Registry auto-fill is capture, not silent pull** — a screenshot is one thumb-tap, not zero.
- **"Free forever"** needs featured/ad revenue to materialize — design slots now so it's a flip.
- **Cloning-rights done right** — in MVP as a full line (§7B). The three things that keep it clean: (1) always disclose the **two-part cost** (rights fee + lab production ~$15–20k) so buyers aren't blindsided; (2) auto-generate the **clone-rights license** (template, like the semen release); (3) a plain **live-birth-variability disclosure** (~80% success, months out, no guarantee). Not a blocker — just build these three in.

---

## v1.2 changelog
**Cloning/cell-line rights promoted to a full co-equal MVP product line (§7B)** — a clone-right = the same owner-authorizes-release transaction as a straw (arguably simpler; nothing ships). Added cloning-company facilities (ViaGen/Bovance, Clone International AU, In Vitro Brasil) to the directory; two-part cost disclosure (rights fee + ~$15–20k lab production); auto-generated clone-rights license; live-birth disclosure. **wagyusale.com → build WagyuTank standalone now**, no cross-platform seam designed yet (§19). Removed the V2 "cloning full build" item.

## v1.1 changelog (Fable review pass)
**Added/elevated:** canonical Animal as architectural spine (Principles #8, §8, §18); demand-side gravity & retention engine — animal pages w/ multi-seller aggregation, saved-search alerts, follow graph, want-ads (§8); Seller Storefronts as a core pillar in MVP (§4); global-first — multi-currency + AI listing translation + regional facilities/registries (§12, Principle #10); seeded facility typeahead directory (§6); trust-badge ladder (§3); universal input + progressive/lite publish (§2); optional escrow earlier for high-value (§5).
**Streamlined/cut:** heavy/live auction events removed from WagyuTank → defined wagyusale.com boundary + seam (§19, §7); cloning/cell-line staged to "coming soon" in MVP, full build V2 (differentiator preserved, complexity deferred); V3 relabeled from committed sprint to traction-sequenced backlog (§20).

---

*This is the genome. Build from it and the organism assembles itself: a normie types a number, drags one screenshot, and in a minute has a professional, shareable, registry-linked, any-language Wagyu genetics listing — on their own branded storefront, discoverable by the whole world, for free — on the site the breed uses everywhere.*
