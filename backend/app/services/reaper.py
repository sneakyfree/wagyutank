"""Stale-link reaper for the Roundup.

The aggregator delists a listing when it vanishes from a source we successfully
re-crawled. But if a seller's SITE stays up while one LISTING page 404s, an
extraction-based crawl never notices (the dead URL simply stops appearing). This
reaper closes that gap with a cheap, direct HTTP check of every active listing's
`source_url` — no LLM cost.

Classification (deliberately conservative — a false delist is worse than a slow
one, and the weekly crawl reactivates anything that reappears):

  alive        2xx, or a redirect chain ending 2xx      -> dead_streak = 0
  hard-dead    404 / 410                                 -> delist now
  soft-dead    DNS failure, connection refused, timeout,
               5xx                                       -> dead_streak += 1;
                                                            delist at >= 2
  inconclusive 401 / 403 / 429 (bot-block / auth wall)   -> leave unchanged

Runs weekly (see jobs.reap_links), so "two soft-dead checks" ~= two weeks of a
site being unreachable before we pull its listings — while a genuine 404/410
(the page was removed) is pulled on the first pass.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

from ..models import AggregatedListing

# A real browser UA — many seller sites 403 non-browser agents, and we don't
# want a bot-block masquerading as a dead link.
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_HARD_DEAD = {404, 410}
_INCONCLUSIVE = {401, 403, 429}
_TIMEOUT = 12.0
_WORKERS = 8


def _probe(url: str) -> str:
    """Return one of: 'alive' | 'hard' | 'soft' | 'skip'."""
    if not url or not url.startswith(("http://", "https://")):
        return "skip"
    headers = {"User-Agent": _UA, "Accept": "*/*"}
    try:
        with httpx.Client(follow_redirects=True, timeout=_TIMEOUT, headers=headers) as c:
            try:
                r = c.head(url)
                # Some servers don't implement HEAD (405/501) — confirm with GET.
                if r.status_code in (405, 501):
                    r = c.get(url)
            except httpx.HTTPError:
                r = c.get(url)  # retry once as GET before judging
        code = r.status_code
        if code in _HARD_DEAD:
            return "hard"
        if code in _INCONCLUSIVE:
            return "skip"
        if code >= 500:
            return "soft"
        return "alive"  # 2xx / 3xx-resolved / other 4xx we won't act on
    except httpx.HTTPError:
        # DNS failure, connection refused, timeout, SSL error -> soft-dead.
        return "soft"


def reap(db, *, limit: int | None = None) -> dict:
    """Check every active, non-flagged listing's source URL and age out dead ones.

    Returns a summary dict. Idempotent and safe to run repeatedly."""
    q = db.query(AggregatedListing).filter(
        AggregatedListing.status == "active",
        AggregatedListing.flagged == False,  # noqa: E712
    )
    if limit:
        q = q.limit(limit)
    rows = q.all()
    if not rows:
        return {"checked": 0, "alive": 0, "hard_dead": 0, "soft_dead": 0,
                "delisted": 0, "skipped": 0}

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        verdicts = list(pool.map(lambda r: (r, _probe(r.source_url)), rows))

    alive = hard = soft = delisted = skipped = 0
    for row, verdict in verdicts:
        if verdict == "alive":
            alive += 1
            if row.dead_streak:
                row.dead_streak = 0
        elif verdict == "hard":
            hard += 1
            row.status = "delisted"
            delisted += 1
        elif verdict == "soft":
            soft += 1
            row.dead_streak = (row.dead_streak or 0) + 1
            if row.dead_streak >= 2:
                row.status = "delisted"
                delisted += 1
        else:  # skip / inconclusive
            skipped += 1
    db.commit()
    return {"checked": len(rows), "alive": alive, "hard_dead": hard,
            "soft_dead": soft, "delisted": delisted, "skipped": skipped}
