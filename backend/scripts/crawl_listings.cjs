#!/usr/bin/env node
/**
 * WagyuTank JS-rendering listing crawler — runs on Windy 0 (residential IP,
 * Playwright/Chromium already installed). Renders the JavaScript that static
 * fetch can't see on modern SPA seller sites, extracts the rendered visible
 * text, and follows a bounded set of same-domain product/pagination links.
 *
 * It stores NOTHING itself — it outputs {source_url, source_site, text} for the
 * Python side to run through the existing LLM extractor (facts + our neutral
 * summary + link-back only; never the seller's ad copy or images).
 *
 *   node crawl_listings.cjs --seeds seeds.json --out rendered_pages.json
 *        [--per-site 8] [--concurrency 4] [--max-pages 600]
 */
const fs = require("fs");
// Resolve Playwright portably so the crawler runs on ANY node (Veron, Windy 0, VPS):
// PLAYWRIGHT_PATH env → local `playwright` (npm i playwright) → Windy 0 legacy path.
const { chromium } = (() => {
  const tries = [process.env.PLAYWRIGHT_PATH, "playwright",
    "/home/grantwhitmer/Desktop/Grant's Folder/windy-pro/node_modules/playwright"].filter(Boolean);
  for (const p of tries) { try { return require(p); } catch (_) {} }
  throw new Error("Playwright not found — set PLAYWRIGHT_PATH or `npm i playwright` in backend/");
})();

function arg(name, def) {
  const i = process.argv.indexOf(`--${name}`);
  return i > -1 && process.argv[i + 1] ? process.argv[i + 1] : def;
}
const SEEDS = arg("seeds", "seeds.json");
const OUT = arg("out", "rendered_pages.json");
const PER_SITE = parseInt(arg("per-site", "8"), 10);
const CONC = parseInt(arg("concurrency", "4"), 10);
const MAX_PAGES = parseInt(arg("max-pages", "600"), 10);

// Link classification. STRONG hits are always followed (unambiguous genetics
// listing pages). COMMERCE paths (Shopify/Woo /products//collections/) are
// followed ONLY when they also carry a genetics HINT — otherwise a shop's
// heat-detection stickers and merch get crawled and burn LLM budget. SKIP
// hard-filters non-genetics commerce (dairy-breed catalogs, beef/meat, merch).
const STRONG = /semen|embryo|straw|\bdose|sperma|genetik|genetic|for.?sale|nettbutikk/i;
const COMMERCE = /product|collection|shop|store|katalog|catalog/i;
// Per-tank breed terms: TANK_TERMS env = pipe-joined lowercase terms (set by
// deploy/tank-crawl.sh from the tank's tank.json). Without it, defaults to the
// Wagyu terms so the original wagyu crawl is unchanged. The breed terms feed
// the HINT (what makes a commerce link worth following) and are STRIPPED from
// SKIP (so e.g. an AngusTank crawl doesn't skip its own breed).
const BREED_TERMS = (process.env.TANK_TERMS || "wagyu|akaushi|michifuku|itoshigenami|tajima|fukutsuru|shigeshigenami")
  .toLowerCase().split("|").map(s => s.trim()).filter(Boolean);
const HINT = new RegExp(BREED_TERMS.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") +
  "|semen|embryo|straw|sperma|genetik|genetic|\\bsire\\b|\\bbull\\b|\\bdam\\b", "i");
const SKIP_BREEDS = ["holstein", "jersey", "angus", "hereford", "charolais", "simmental", "brahman"]
  .filter(b => !BREED_TERMS.some(t => t.includes(b)));
const SKIP = new RegExp("\\b(login|cart|account|checkout|privacy|terms|contact|about|blog|news|faq|policy|cookie|newsletter|wishlist|compare)\\b" +
  "|beef|meat|fleisch|rindfleisch|carne|steak|" + SKIP_BREEDS.join("|") +
  "|dairy|\\bmilk\\b|restaurant|recipe|cook|butcher|wholesale|gift|apparel|merch", "i");

function follow(clean, t) {
  if (STRONG.test(clean) || STRONG.test(t)) return true;
  if ((COMMERCE.test(clean) || COMMERCE.test(t)) && (HINT.test(clean) || HINT.test(t))) return true;
  return false;
}

function hostOf(u) { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return ""; } }

async function robotsAllows(ctx, origin) {
  // Light robots check: only block if the file explicitly Disallows "/" for all.
  try {
    const p = await ctx.newPage();
    const r = await p.goto(`${origin}/robots.txt`, { timeout: 12000 }).catch(() => null);
    const body = r && r.ok() ? await p.content() : "";
    await p.close();
    const txt = (body || "").toLowerCase();
    if (/user-agent:\s*\*/.test(txt) && /disallow:\s*\/\s*$/m.test(txt)) return false;
    return true;
  } catch { return true; }
}

const GOTO_TIMEOUT = parseInt(arg("goto-timeout", "22000"), 10);

async function renderPage(page, url) {
  // domcontentloaded ALWAYS fires quickly; then give the SPA a bounded window to
  // hydrate. networkidle alone hangs forever on tracker/chat-widget-heavy sites.
  // Slow site-builder hosts (Wix/Squarespace) can exceed the first budget under
  // concurrency contention, so retry once with more headroom before giving up.
  let lastErr;
  for (const t of [GOTO_TIMEOUT, GOTO_TIMEOUT + 15000]) {
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: t });
      lastErr = null;
      break;
    } catch (e) { lastErr = e; }
  }
  if (lastErr) throw lastErr;
  await page.waitForLoadState("networkidle", { timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(1200);
  const text = await page.evaluate(() => (document.body ? document.body.innerText : "").slice(0, 18000));
  const links = await page.evaluate(() => Array.from(document.querySelectorAll("a[href]")).map((a) => ({ href: a.href, t: (a.textContent || "").trim().slice(0, 60) })));
  return { text, links };
}

async function crawlSite(browser, seed, budget, out) {
  const site = hostOf(seed.url);
  if (!site) return;
  const ctx = await browser.newContext({
    userAgent: `Mozilla/5.0 (compatible; ${process.env.TANK_BOT || "WagyuTankBot/1.0; +https://www.wagyutank.com/roundup"})`,
    viewport: { width: 1280, height: 1600 },
  });
  try {
    const origin = new URL(seed.url).origin;
    if (!(await robotsAllows(ctx, origin))) { await ctx.close(); return; }
    const page = await ctx.newPage();
    const visited = new Set();
    const queue = [seed.url];
    let count = 0;
    while (queue.length && count < PER_SITE && budget.n > 0) {
      const url = queue.shift();
      if (visited.has(url)) continue;
      visited.add(url);
      let r;
      try { r = await renderPage(page, url); } catch { continue; }
      budget.n--; count++;
      if (r.text && r.text.length > 60) out.push({ source_url: url, source_site: site, text: r.text });
      // enqueue same-domain listing/pagination links
      for (const { href, t } of r.links) {
        if (queue.length + visited.size >= PER_SITE + 6) break;
        if (hostOf(href) !== site) continue;
        const clean = href.split("#")[0];
        if (visited.has(clean) || queue.includes(clean)) continue;
        if (/[<>{}]|%3c|%7b|\?php|esc_url|\{\{/i.test(clean)) continue;  // skip unrendered-template link leaks
        if (SKIP.test(clean) || SKIP.test(t)) continue;
        if (follow(clean, t)) queue.push(clean);
      }
    }
    await page.close();
  } catch { /* site failed — move on */ } finally {
    await ctx.close();
  }
}

async function pool(items, worker, concurrency) {
  const q = [...items];
  const runners = Array.from({ length: concurrency }, async () => {
    while (q.length) { const it = q.shift(); await worker(it); }
  });
  await Promise.all(runners);
}

(async () => {
  const seeds = JSON.parse(fs.readFileSync(SEEDS, "utf8"));
  console.log(`Crawling ${seeds.length} seed sites (per-site ${PER_SITE}, conc ${CONC}, cap ${MAX_PAGES})…`);
  const browser = await chromium.launch({ headless: true });
  const out = [];
  const budget = { n: MAX_PAGES };
  let done = 0;
  await pool(seeds, async (seed) => {
    await crawlSite(browser, seed, budget, out);
    done++;
    if (done % 10 === 0) console.log(`  ${done}/${seeds.length} sites · ${out.length} pages rendered · budget ${budget.n}`);
  }, CONC);
  await browser.close();
  fs.writeFileSync(OUT, JSON.stringify(out));
  console.log(`Rendered ${out.length} pages from ${seeds.length} sites → ${OUT}`);
})().catch((e) => { console.error("FATAL", e.message); process.exit(1); });
