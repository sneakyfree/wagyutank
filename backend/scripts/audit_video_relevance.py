#!/usr/bin/env python3
"""Which approved videos have nothing to do with cattle?

RESULT 2026-07-30: zero, out of 515 approved. The one genuinely off-topic video
(a KINTO clay-pot unboxing) was already status=hidden. Kept as a reusable guard
for future ingest, and as the record of how the check had to be built.

The shelf carries a KINTO clay-pot unboxing. Nothing gates what gets approved,
so the harvest's off-topic hits ride straight onto a breeder-facing page.

DELIBERATELY CONSERVATIVE. Today's language audit went wrong twice by being
clever, and unapproving a real breeder's video is far worse than leaving one
clay pot up. So a video is flagged ONLY when it scores ZERO across every scrap
of text we hold — title, translated title, description, editorial, channel name,
the harvest query that found it, AND its full transcript. One single hit
anywhere and it stays. Registration numbers (matched_regs) are an automatic
keep: those only appear on real pedigree content.

Vocabulary spans en/ja/zh because the shelf does. 牛 (cattle) and 肉 (meat)
carry most of the CJK signal on their own.

usage: relevance.py [--apply]   (default: dry run)
"""
import re
import sys

from app.db import SessionLocal
from app.models import Animal, VideoTranscript, WagyuVideo

APPLY = "--apply" in sys.argv

VOCAB = re.compile(
    # English
    r"wagyu|akaushi|angus|beef|cattle|\bcows?\b|\bbulls?\b|heifer|steer|\bcalf\b|calves|"
    r"ranch|farm|herd|\bsire\b|\bdam\b|semen|embryo|straw|breed|butcher|steak|brisket|"
    r"ribeye|sirloin|loin|marbl|kobe|matsusaka|tajima|yakiniku|livestock|abattoir|"
    r"slaughter|carcass|graz|pasture|feedlot|bms|\ba[1-5]\b|genetic|pedigree|stud|"
    # Japanese / Chinese (牛 cattle, 肉 meat carry most of it)
    r"和牛|牛|肉|但馬|松阪|神戸|神戶|黒毛|黑毛|畜産|畜牧|種雄|牧場|焼肉|燒肉|霜降|"
    r"枝肉|精肉|飼育|飼養|繁殖|子牛|母牛|blood|赤身|A5|A4",
    re.I)


def blob(v, tx):
    # NOT v.query and NOT v.channel — both are circular or misleading.
    # `query` is the harvest search that FOUND the video, so it carries the breed
    # term by construction: the clay-pot video's query is literally "Kinto wagyu",
    # which made every video score a hit and the first run of this audit return a
    # confident, useless zero. `channel` describes the publisher, not the video —
    # a wagyu channel posting cookware is still cookware.
    return " ".join(filter(None, [
        v.title, v.title_en, v.description, v.editorial, tx]))


# A registration number IS cattle content: LRXF23U303L, FB16684, JP123456.
REG = re.compile(r"\b[A-Z]{2,5}[-\s]?\d{3,}[A-Z0-9]*\b")

db = SessionLocal()
try:
    # The site already knows its own sire and dam names — 134 of them — so use
    # that instead of a hand-written vocabulary. The first version of this audit
    # would have hidden THREE real breeding videos whose titles are nothing but
    # animal names: "Shigefuku and Kikuyasu 400 sons of Chisahime 208" (Grant's
    # own upload), "LRXF23U303L - LRX-TX MS CHIYOTAKE U303L (ET)", and
    # "Rokki and Rikitani" — Rikitani is in this very table. A pure-pedigree title
    # is the MOST on-topic thing on the shelf, and the naive check scored it zero.
    ANIMALS = set()
    for a in db.query(Animal).all():
        for nm in [a.name] + list(a.aliases or []):
            nm = (nm or "").strip().lower()
            if len(nm) >= 4:                 # 3-char names are too collision-prone
                ANIMALS.add(nm)
        if a.registration_no:
            ANIMALS.add(a.registration_no.strip().lower())
    tx = {}
    for t in db.query(VideoTranscript).filter(
            VideoTranscript.is_source == True):          # noqa: E712
        tx[t.video_id] = " ".join(c["x"] for c in (t.cues or []))[:20000]

    vids = db.query(WagyuVideo).filter(WagyuVideo.status == "approved").all()
    flagged = []
    for v in vids:
        if v.matched_regs:                              # pedigree content — never touch
            continue
        text = blob(v, tx.get(v.video_id or "", ""))
        low = text.lower()
        hits = set(m.group(0).lower() for m in VOCAB.finditer(text))
        if not hits and not REG.search(text) and not any(a in low for a in ANIMALS):
            flagged.append(v)

    print(f"approved videos: {len(vids)}")
    print(f"ZERO cattle vocabulary anywhere: {len(flagged)}\n")
    for v in sorted(flagged, key=lambda x: (x.lang or "", x.id)):
        has_tx = "transcript" if (v.video_id in tx) else "no transcript"
        print(f"  dbId={v.id:<5} {v.video_id or '-':13s} lang={v.lang or '-':3s} "
              f"cat={v.category:<10} views={v.views or 0:>9,} {has_tx}")
        print(f"        title  : {(v.title or '')[:76]}")
        print(f"        channel: {(v.channel or '')[:40]}   query={(v.query or '')[:34]}")
        if APPLY:
            v.status = "hidden"
    if APPLY:
        db.commit()
        print(f"\nAPPLIED — {len(flagged)} set to status='hidden' (reversible)")
    else:
        db.rollback()
        print("\nDRY RUN — nothing written (pass --apply)")
finally:
    db.close()
