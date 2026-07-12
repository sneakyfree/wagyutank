# WagyuTank — Breed Impactors, the Impact Ranking & the Hall of Fame
### Vision & build plan · crystallized 2026-07-12

> This is a canonical vision doc. It is deliberately verbose so the whole idea
> survives even if we don't build it for months. Names here are the agreed names.

---

## 0. The one-sentence version

Recreate the breed's **entire parentage graph** from publicly-available registry
data, and off that single asset build a self-marketing scoreboard — continental
medals, an all-time impact ranking, a Hall of Fame, and shareable certificates —
that gives every breeder a number to chase and a reason to come to WagyuTank.

## 1. The core insight — the asset is the *graph*, not the numbers

Every registered fullblood/purebred Wagyu descends from ~26 foundation bulls and
~180 foundation cows. Each animal's registry record links to its sire and dam, so
the whole population is **one connected tree**. If a residential-IP browser walks
that tree, we reconstruct the **complete parentage graph** on our own server.

Once we own the graph, everything else falls out of it for free:

- **Progeny counts** = count inbound sire/dam edges. No estimation.
- **The all-time ranking** = sort by that count.
- **Medals** = threshold that count, per registry.
- **"Hall-of-Famers in this animal's pedigree"** = walk its ancestors and tally.
- **Better everything-else:** instant pedigree auto-fill on listings, animal
  verification, bloodline price indexes — all sharpen once the graph exists.

No competitor has a WagyuTank-computed, continent-by-continent impact ranking
built from cold registration data. That uniqueness is the "check out WagyuTank" hook.

## 2. Two orthogonal dimensions (this resolves "Michifuku is a foundation bull AND a platinum")

Every animal sits on **two independent axes**:

- **Origin** — where it sits in history. *Fixed forever.*
  `Foundation → Influential (bred outside Japan) → Modern`.
- **Impact** — medals from registered progeny, *per continent*. *Grows over time.*

Medals decorate **every** animal, foundation included. The **Breed Impactors**
page is the leaderboard of *modern* (non-foundation) animals that earned medals —
the aspirational arena — but the badges themselves also appear on foundation and
influential animals. Michifuku: Foundation origin, global-platinum impact.

## 3. The system — one name, five surfaces

Pillar name: **Breed Impactors.** Core metric: **Impact Score** = registered progeny.

1. **The Impact Ranking** — every animal, #1 to last, all-time. Sortable by
   continent, bloodline, and modern-only. The cold-hard-numbers spine.
2. **Continental Medals** — 🥉 Bronze / 🥈 Silver / 🥇 Gold / 💠 Platinum, awarded
   **per registry**. An animal wears a row: 🇺🇸 Platinum · 🇦🇺 Platinum · 🇪🇺 Gold · 🇨🇳 Bronze.
   *Per-continent is deliberate:* it means we never reconcile a global number —
   each registry's own count becomes that continent's medal. The data limitation
   becomes the design.
3. **Combination Honors** — Double/Triple Platinum, Quad Gold, Double-Platinum-
   Double-Gold, etc. These define the Hall-of-Fame strata. The first triple-
   platinum bull is a title someone will chase (Asia/EU populations are young, so
   triple-platinum probably doesn't exist yet — a land-grab).
4. **The Hall of Fame** — the curated elite (top ranks + multi-continental
   platinum). Auto-generated after Veron's first deep pass.
5. **Pedigree Pride** — on any animal page: *"3 Hall-of-Famers and 5 Platinums in
   this pedigree."* Every breeder checks their own herd. The retention loop.

## 4. Tier thresholds — SET FROM DATA, not from vibes

Bulls and cows need different physics: a bull can sire thousands; a cow produces
~8–15 calves naturally (more via ET/IVF), so cow thresholds sit far lower.

**Draft starting point (final numbers set after the scout sees the distribution):**

| Tier | Sire (bull) progeny | Dam (cow) progeny |
|------|--------------------:|------------------:|
| 🥉 Bronze   | 10  | 5  |
| 🥈 Silver   | 50  | 10 |
| 🥇 Gold     | 100 | 20 |
| 💠 Platinum | 500 *(TBD — see note)* | 30 |

**Open calibration question:** "100 progeny" is Grant's emotional milestone and
should always earn a certificate — but 100+ AU progeny is more common than it
feels, so a flat "100 = platinum everywhere" would mint too many platinums in the
mature Australian registry. Leaning: keep **Gold = 100** (the milestone + cert),
push **Platinum higher (≈500)** so it stays elite; let the per-continent overlay
carry the prestige. The scout's sample distribution decides the exact cutoffs.
Thresholds are flat across registries for legibility (a young registry being
"harder" tells a true breed-development story), and are per-tank configurable.

## 5. Certificates — free digital first, physical as the upsell

- **Digital E-certificate (free):** a beautiful, high-res, printable PDF —
  *"WagyuTank congratulates [Bull] on achieving American Platinum + Australian
  Gold — 250 registered progeny, verified [date]"* with the WagyuTank seal.
  Auto-emailed to the **verified owner** (plugs into claim-your-profile +
  verified-email, already built). They print/frame/post it → free marketing, zero cost.
- **Physical gold-leaf laminated version ($10, later):** print-on-demand + mail;
  costs nothing until ordered. Digital ships first; physical is a switch we flip.

Why it's the flywheel: the medal makes them **proud**, claiming the certificate
makes them a **user**, the paper copy makes them a **customer**.

## 6. The data doctrine (legal / ethical — READ BEFORE CRAWLING)

The registry search pages are publicly available. Our posture is **good-actor
index, not leech**:

- **Respect robots.txt and Terms of Service.** Check them before crawling at
  scale. If a source disallows it, that continent's medals come from
  verified-submission instead, and nothing else breaks.
- **Rate-limit and crawl in the overnight window.** Politeness over speed.
- **Store facts only** — reg number, name, sex, birth year, sire, dam, progeny,
  EPDs, registry. Facts aren't copyrightable.
- **Never re-serve their raw database dynamically.** We compute our **own**
  analysis (rankings, charts, medals) from the facts — which anyone could produce
  by hand and which every site does. We do **not** offer a live mirror of their
  data for others to pull.
- **Link every animal back** to its source registry record; credit the
  associations as sources. We drive attention *to* the breed and *to* them.

## 7. Capture EVERYTHING (don't pre-decide what's interesting)

While Veron walks the tree, record the **entire** animal record, raw — we present
later. At minimum, per animal: registration number, name, **sex**, **birth year**,
sire (+reg), dam (+reg), **progeny list/count**, breed/bloodline, registry/country,
**EPD/EBV data** (breeders love EPDs), owner/breeder if shown, colour, and any
performance/carcass data on the page. Store the raw extracted record; curate the
presentation afterward.

This unlocks fascinating derived data, e.g.:
- The **complete list of the original foundation cows** and each one's offspring
  count (currently we only have ~180 as a number — we could name them all).
- Same for every foundation bull.
- Sex ratios, birth-year cohorts, line growth over time, EPD distributions —
  endless charts and rankings, none of which require re-serving raw data.

## 8. The engine

- **Veron 1** (24-core i9 285K, 251 GB RAM, RTX 5090, residential fiber) runs the
  crawl **nightly midnight–~7am** (idle window; residential IP that registries
  don't block). Same Playwright→extract→VPS pipeline as the Roundup crawler.
  We do **not** need Browserbase or any paid cloud browser — Veron is our browser
  farm, free, and residential.
- **VPS** stores the parentage graph + computes progeny, medals, rankings.
- **WindyMind free lane** for any LLM extraction — no metered cost.
- **Cadence:** progeny grows slowly, so a full refresh monthly/quarterly with
  incremental top-ups. Recoverable: all crawler code lives in the git repo so it
  survives any single machine dying.

## 9. Sources (registries), by continent

Start with the two richest, architect for all:

- 🇺🇸 **American Wagyu Association** — `wagyu.org` → **Digital Beef** platform
  (public animal search by name/reg; pedigree drill-back to foundations).
- 🇦🇺 **Australian Wagyu Association** — BREEDPLAN / ABRI (rich, public).
- 🇨🇦 Canada, 🇪🇺 UK/EU bodies, 🇯🇵 Japan (mostly closed), emerging 🇨🇳 Asia,
  🇳🇿 NZ, 🇿🇦 South Africa, + assorted national mini-registries.

## 10. Crawl architecture — the one fork the scout settles

Depends on whether a Digital Beef animal page shows **progeny (descendants)** or
only **ancestry (sire/dam)**:

- **Progeny visible →** start at the 26 founders, walk *downward*; every animal is
  reachable. Lighter.
- **Ancestry only →** enumerate animals another way (registration-number sweep or
  search), visit each once, record sire/dam, then compute progeny by **inverting**
  the edges. Heavier (touch every animal) but this literally *recreates the entire
  database*. Likely path.

Either way the durable asset is the same: the full parentage graph on our VPS.

## 11. Build plan — staged so nothing is a cliff

1. **Scout (1 Veron night):** confirm Digital Beef public surface + robots.txt/ToS;
   whether progeny is visible or must be reconstructed; the reg-number scheme for
   enumeration; the full field set on an animal page. Pull a ~200-animal sample →
   real progeny distribution → **set the tier numbers from data.**
2. **Graph engine:** Veron nightly sweep → VPS parentage graph → compute progeny,
   medals, rankings. AWA-US first, then Australia.
3. **Surfaces:** Impact Ranking page → medal badges on every animal page → Hall of
   Fame → "in your pedigree" pride.
4. **Certificates:** E-cert generator + verified-owner claim hook.
5. **Expand + templatize:** add Canada / UK-EU / Japan / mini-registries; per-tank
   config so every clone inherits it.

## 12. Template integration (all clones)

- Feature flag `breed_impactors` (on for breeds with real registries; off for
  niches without formal progeny records).
- Per-tank in `tank.json`: tier thresholds (sire/dam per metal), `registries`
  list ({continent, name, url, access: public|gated}), certificate seal/template.
- The graph engine + medal logic are breed-agnostic; only config changes per tank.

## 13. Naming glossary (agreed)

- **Breed Impactors** — the pillar / the leaderboard page.
- **Impact Score** — an animal's registered-progeny count (per continent + total).
- **Impact Ranking** — the #1-to-last all-time list.
- **Medals** — Bronze / Silver / Gold / Platinum, per continent.
- **Combination Honors** — Double/Triple Platinum, Quad Gold, etc.
- **Hall of Fame** — the curated elite subset.
- **Pedigree Pride** — the "Hall-of-Famers in this pedigree" panel.

---

## 14. SCOUT FINDINGS (2026-07-12) — the sourcing landscape changed; DO NOT crawl the registries

A Veron scout of the actual registry sites found the crawl-the-registries plan is
**blocked at the platform level.** The key facts:

- **AWA (USA) has migrated OFF Digital Beef.** `wagyu.digitalbeef.com` is now just
  a contact placeholder ("Please contact the American Wagyu Association…").
- **Both AWA (USA) and AWA-AU (Australia) now run on Helical** (`app.helicalco.com`).
  A single SaaS platform now hosts both registries' data.
- **Helical's robots.txt is `User-agent: * / Disallow: /`** — it forbids *all*
  automated crawling of the entire platform, public paths included.
- **USA** (`americanwagyu.helicalco.com`) is **login-gated** — every animal page
  redirects to "Continue with Google / passkey / email."
- **Australia** (`app.helicalco.com/public/au-wagyu/animals`) is **human-viewable
  without login**, but still under the same `Disallow: /` robots policy.
- The associations' *marketing* sites (`wagyu.org.au` robots = allow) are fine, but
  the animal *data* lives on Helical.

**Decision: we will not crawl Helical.** Respecting robots.txt and not breaching a
members' login is both the ethical line and the way to stay off the hook legally
(a core WagyuTank value). The "spider every registry and recreate the whole tree"
acquisition model is off the table as long as the data lives behind Helical.

### 14a. The pivot — legitimate data acquisition (vision UNCHANGED)

The medals / Impact Ranking / Hall of Fame / Pedigree Pride / certificate system
is **fully intact** — only the *data pipeline* changes, from bulk-crawl to:

1. **Verified breeder submission (primary):** breeders add their own animals'
   progeny/EPD data with proof (a public link or screenshot we verify). Pull, not
   scrape. Legal, clean, self-marketing — the person *wants* their bull ranked.
   This is the same "pull, don't push" model already chosen for the Atlas directory.
2. **Association public reports** where robots allow — AWA-PTP progeny-test sire
   results, trait-leader / sire-summary pages on the assoc's own site. Limited to
   tested/notable sires, but legitimate and crawlable.
3. **Independent public aggregators** (e.g. the Wagyu International encyclopedia,
   robots-open) for foundation + notable animals — needs a closer scout to confirm
   it's genuinely independent and not a Helical mirror.
4. **Official route:** request a Helical/AWA **public-data API or partnership**.
   They deliberately built a "public database" view, so a sanctioned integration is
   plausible and is the *right* way to get comprehensive data.
5. **On-demand single-animal verification** (human-triggered when a breeder submits
   a claim) rather than bulk enumeration — far more defensible than mass-harvest.

Net: build the whole medal/ranking/Hall-of-Fame/certificate system on a
**seed + submit + partner** pipeline. Start the ranking from what breeders submit
and what public reports list; let it grow the way the Atlas grows.

## 15. World registry inventory (scout 2026-07-12)

The whole Western Wagyu world funnels its animal data through **two crawler-hostile
platforms**, and there is exactly **one** genuinely open source.

**The two walls:**
- **Helical** (`app.helicalco.com`) — `Disallow: /`; USA login-gated, AU public-in-
  browser but bot-403. Hosts USA + Australia (+ downstream: UK, Spain, Denmark,
  Ireland, China all register via AWA).
- **ABRI / BREEDPLAN** (`abri.une.edu.au`, `i4.abri.au`) — `Disallow: /`, actively
  blocks ClaudeBot, 403s bots. Hosts NZ, South Africa, Namibia, legacy Australia.

**The one open source:**
- **Wagyu International — `wagyuinternational.co`** (NB: the `.international` TLD is
  parked/dead). robots.txt fully open (`Disallow:` empty). Independent global Wagyu
  encyclopedia run by **Steve Bennett (ex-AWA Executive Officer)** since 2013 — not
  an association arm. Already organizes **sire/animal/bloodline pages by country**
  with EBVs, recessive-condition results, and a semen/embryo directory. It's a
  *derived/secondary* source (not a primary registry), but it's the only
  crawl-permissive Wagyu data host on earth — and it already does the
  country-by-country aggregation we want. **This is our legitimate seed + a natural
  partnership target** (credible, aligned, ex-AWA insider).

**Marginal / dead ends:**
- 🇨🇦 Canada **CLRC** (`clrc.ca`, breed code WC) — real public pedigree lookup,
  Google-indexed, but WAF 403s non-browser clients; small/stale herd. Possible with
  a real browser, low ROI.
- 🇯🇵 Japan **NLBC** (`id.nlbc.go.jp`) — no robots.txt, but only ID-verifies
  registration; no browsable pedigree/progeny tree. Permissive but useless for ranking.
- No open herdbook at all: Germany, Netherlands (CRV login-only), Brazil, France,
  Argentina (cert expired), Chile (DNS down), Spain. No "European Wagyu Association"
  herdbook exists; World Wagyu Council = coordination only, no DB.

**DNA-chain note (why AWA was uniquely valuable):** only the AWA holds DNA samples
on the original foundation imports, so only an AWA pedigree can assert an unbroken
DNA-verified chain to the founders. Other registries "picked up where they left
off" — less rigorous, but still a real *popularity/impact* signal per country.

**Conclusion:** "spider every registry" is dead — the data consolidated behind
Helical + ABRI, both closed to crawlers. Path forward = **(1) index Wagyu
International (`wagyuinternational.co`) respectfully as the seed, (2) grow by
verified breeder submission, (3) pursue official partnerships (Steve Bennett /
Helical / AWA).**

### 15a. Wagyu International structure scout (2026-07-12) — it's an encyclopedia, not a dataset

Scouted the one open source directly. It is **server-rendered PHP, robots-open, but
only ~37 pages** (its own sitemap): ~15 per-country narrative pages
(`global_usa.php`, `global_australia.php`, `global_japan.php`, …), `foundation.php`,
`genetics.php`/`recessives.php`, and a handful of individual `semen_*.php` sire
pages. `foundation.php` mentions progeny ~28 times but all **narrative** ("51
progeny", "progeny that graded Marble Score 9") — prose about a few dozen founders,
not a structured per-animal table. Country pages carry **no** sire rankings or
progeny counts.

**Hard truth:** there is **no legitimately-crawlable source for comprehensive
per-animal registered-progeny counts** anywhere. The registries that have it
(Helical, ABRI) are closed; the one open aggregator is editorial. So the
"auto-rank every bull #1-to-last from cold numbers" version **cannot be crawled
into existence.** What's realistic:

- **Wagyu International** = great for foundation/notable-animal *enrichment* and
  per-country breed *narrative* — dozens of animals, sparse numbers. A seed for the
  Foundation/Influential tiers, not the modern ranking.
- **Verified breeder submission = the actual engine.** Breeders supply their own
  animal's progeny count + registry proof; we verify → medal + certificate. This is
  the ONLY route to comprehensive, current data, and it's self-marketing.
- **Official Helical/AWA partnership = the only route to the authoritative complete
  dataset** (and the DNA-verified US tree). The swing-for-the-fences upside.

Net: launch the medal/Hall-of-Fame/certificate system as a **submission-first**
product (seeded with foundation + notable animals), and pursue partnership for the
full dataset. It starts smaller than "the whole breed on day one," but it's clean,
legal, and grows the way the Atlas grows.
