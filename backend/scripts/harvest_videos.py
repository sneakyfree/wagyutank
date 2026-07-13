#!/usr/bin/env python3
"""WagyuTank video harvest — runs on Windy 0 (residential IP), NOT the VPS.

Discovers Wagyu YouTube videos with yt-dlp search, using a query pool generated
from the live site's own data (foundation animals + sale events) plus fixed
category and Japanese terms. Extracts registration numbers from titles
(permanently — never discarded), filters for relevance, checks embeddability
via oEmbed, and writes candidates to videos.json for ingest on the VPS:

  python3 scripts/harvest_videos.py --out /tmp/videos.json [--per-query 8] [--quick]

Then:  scp videos.json vps:/root/wagyutank/backend/ && ssh vps '... -m app.jobs.ingest_videos videos.json'
"""
import argparse
import concurrent.futures as cf
import json
import re
import subprocess
import sys
import time
import urllib.request

import os
API = os.environ.get("HARVEST_API", "https://api.wagyutank.com")

# ---- tank identity (fetched from the target tank's own /api/config) ----------
# The harvest is breed-agnostic: the breed word in every query, the relevance
# words, and the category queries all come from the tank this run targets, so a
# MurrayGreyTank harvest searches "<bull> murray grey", never "wagyu".
_TANK_CFG = None

def tank_cfg():
    global _TANK_CFG
    if _TANK_CFG is None:
        try:
            _TANK_CFG = get_json(f"{API}/api/config")
        except Exception:
            _TANK_CFG = {}
    return _TANK_CFG

def breed_word() -> str:
    b = (tank_cfg().get("brand") or {}).get("breed") or "Wagyu"
    return b.split(" & ")[0].strip().lower()

def is_wagyu_tank() -> bool:
    return (tank_cfg().get("key") or "wagyu") == "wagyu"

def relevance_words() -> tuple:
    if is_wagyu_tank():
        return WAGYU_WORDS
    v = tank_cfg().get("vocab") or {}
    words = {breed_word()}
    for term in (v.get("video_search_terms") or []) + (v.get("news_search_terms") or []):
        words.add(term.strip().lower())
    return tuple(sorted(w for w in words if w))

def category_queries() -> list:
    if is_wagyu_tank():
        return CATEGORY_QUERIES
    b = breed_word()
    return [
        (f"{b} bull sale auction", "sale"), (f"{b} auction results", "sale"),
        (f"{b} genetics sale lot", "sale"), (f"{b} semen lot", "sale"),
        (f"{b} embryo sale", "sale"),
        (f"{b} artificial insemination", "education"), (f"{b} embryo transfer", "education"),
        (f"raising {b} cattle", "education"), (f"starting a {b} herd", "education"),
        (f"{b} stud", "ranch"), (f"{b} cattle farm tour", "ranch"),
    ]

CATEGORY_QUERIES = [
    # sales / auctions
    ("wagyu bull sale auction", "sale"), ("wagyu auction results", "sale"),
    ("Elite Wagyu Sale", "sale"), ("wagyu genetics sale lot", "sale"),
    ("wagyu semen lot", "sale"), ("wagyu embryo sale", "sale"),
    # education / how-to
    ("wagyu artificial insemination", "education"), ("wagyu embryo transfer", "education"),
    ("raising fullblood wagyu", "education"), ("wagyu feeding program", "education"),
    ("wagyu carcass grading marbling", "education"), ("starting a wagyu herd", "education"),
    # ranch / story
    ("fullblood wagyu ranch", "ranch"), ("wagyu cattle farm tour", "ranch"),
    ("akaushi cattle ranch", "ranch"),
    # japan (Japanese-language)
    ("和牛 種雄牛", "japan"), ("和牛 飼育", "japan"), ("和牛 セリ 市場", "japan"),
    ("但馬牛", "japan"), ("松阪牛", "japan"), ("和牛 枝肉", "japan"),
    # cooking / cutting
    ("wagyu butchery cutting", "cooking"), ("how to cook wagyu", "cooking"),
    ("japanese wagyu chef", "cooking"),
]

WAGYU_WORDS = ("wagyu", "akaushi", "和牛", "但馬", "松阪", "黒毛", "kobe beef", "japanese black",
               "fullblood", "full blood", "marbling", "kuroge")
OFFTOPIC = ("minecraft", "fortnite", "asmr mukbang", "slime")

# Registration-number extraction: canonical prefixes + herd-prefix ear-tag style.
REG_PATTERNS = [
    re.compile(r"\b(?:FB|TF|PB|AF|EAF|IMUFN|IMJFA)\s?\d{2,7}\b", re.I),
    re.compile(r"\b[A-Z]{4,8}[FMS]\d{4,6}\b"),          # e.g. MCKFM01470, M6RFS108J
    re.compile(r"\b[A-Z]{2,5}\d{4,6}[A-Z]?\b"),          # e.g. U0659-style w/ herd prefix
]
REG_NOISE = re.compile(r"^(HD|UHD|MP|FPS|4K|1080|720|2160)", re.I)


def get_json(url):
    dom = API.split("://", 1)[-1].replace("api.", "", 1)
    req = urllib.request.Request(url, headers={"User-Agent": f"TankHarvest/1.0 (+https://www.{dom})"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def build_query_pool(quick=False):
    pool = []
    animals = get_json(f"{API}/api/animals/foundation")
    bulls = [a for a in animals if a.get("animal_type") == "bull"]
    for a in bulls:
        name = a["name"].strip()
        pool.append((f"{name} {breed_word()}", "sire", {"animal_reg": a.get("registration_no"), "animal_name": name}))
    # notable cows (photo'd / marquee dams) — cow videos are rarer, sample a few
    cows = [a for a in animals if a.get("animal_type") == "cow"][: (0 if quick else 12)]
    for a in cows:
        pool.append((f"{a['name']} {breed_word()} cow", "sire", {"animal_reg": a.get("registration_no"), "animal_name": a["name"]}))
    # sales from our own database
    try:
        evs = get_json(f"{API}/api/sale-events?limit=200")
        names = []
        for e in (evs if isinstance(evs, list) else evs.get("events", [])):
            n = (e.get("sale_name") or "").strip()
            base = re.sub(r"\b(19|20)\d{2}\b", "", n).strip()
            if base and base.lower() not in [x.lower() for x in names]:
                names.append(base)
        for n in names[: (5 if quick else 25)]:
            pool.append((f"{n} {breed_word()}", "sale", {}))
    except Exception as e:
        print(f"  (sale-events fetch failed: {e})", file=sys.stderr)
    cqs = category_queries()
    for q, cat in (cqs[:6] if quick else cqs):
        pool.append((q, cat, {}))
    return pool


def yt_search(query, n):
    try:
        out = subprocess.run(
            ["yt-dlp", f"ytsearch{n}:{query}", "--flat-playlist", "--dump-json", "--no-warnings"],
            capture_output=True, text=True, timeout=90)
        rows = []
        for line in out.stdout.splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append({
                "video_id": d.get("id"), "title": (d.get("title") or "").strip(),
                "channel": d.get("channel") or d.get("uploader"),
                "channel_id": d.get("channel_id"), "views": d.get("view_count"),
                "duration": d.get("duration"),
                "description": (d.get("description") or "")[:1200],
            })
        return rows
    except Exception:
        return []


def extract_regs(text):
    regs = []
    for pat in REG_PATTERNS:
        for m in pat.findall(text or ""):
            m = m.replace(" ", "").upper()
            if not REG_NOISE.match(m) and m not in regs and 4 <= len(m) <= 14:
                regs.append(m)
    return regs[:10]


CATTLE_CONTEXT = ("cattle", "bull", "cow", "beef", "calf", "heifer", "steer", "semen",
                  "embryo", "stud", "ranch", "herd", "lot ", "genetics", "sire", "dam")


def relevant(item, query_meta):
    hay = f"{item['title']} {item.get('channel') or ''} {item.get('description') or ''}".lower()
    if any(k in hay for k in OFFTOPIC):
        return False
    if any(k in hay for k in relevance_words()):
        return True
    # Animal-name fallback: common-word names (Judo, Mt. Fuji, Mazda…) collide
    # with the wider world — require cattle context or a registration number too.
    an = (query_meta.get("animal_name") or "").lower()
    if not (an and an.split()[0] in hay):
        return False
    if any(k in hay for k in CATTLE_CONTEXT):
        return True
    return bool(extract_regs(f"{item['title']} {item.get('description') or ''}"))


def check_embeddable(video_id):
    try:
        req = urllib.request.Request(
            f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json",
            headers={"User-Agent": "Mozilla/5.0"})
        urllib.request.urlopen(req, timeout=12)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="videos.json")
    ap.add_argument("--per-query", type=int, default=8)
    ap.add_argument("--quick", action="store_true", help="small pool for smoke testing")
    args = ap.parse_args()

    pool = build_query_pool(quick=args.quick)
    print(f"Query pool: {len(pool)} queries")
    seen, out = set(), []
    for i, (q, cat, meta) in enumerate(pool):
        rows = yt_search(q, args.per_query)
        kept = 0
        for r in rows:
            if not r["video_id"] or r["video_id"] in seen:
                continue
            if not relevant(r, meta):
                continue
            if (r.get("duration") or 0) and r["duration"] < 15:
                continue
            seen.add(r["video_id"])
            regs = extract_regs(f"{r['title']} {r.get('description','')}")
            out.append({**r, "query": q, "category_hint": cat,
                        "query_animal_reg": meta.get("animal_reg"),
                        "query_animal_name": meta.get("animal_name"),
                        "extracted_regs": regs})
            kept += 1
        print(f"  [{i+1}/{len(pool)}] {q[:44]:46} +{kept}")
        time.sleep(1.2)  # pace politely

    print(f"\nCandidates: {len(out)} — checking embeddability…")
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        flags = list(ex.map(lambda v: check_embeddable(v["video_id"]), out))
    for v, ok in zip(out, flags):
        v["embeddable"] = ok
    emb = sum(flags)
    json.dump(out, open(args.out, "w"), ensure_ascii=False, indent=1)
    print(f"Wrote {len(out)} candidates ({emb} embeddable) → {args.out}")


if __name__ == "__main__":
    main()
