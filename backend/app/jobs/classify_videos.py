"""LLM category refinement for the Wagyu Theater — fixes heuristic misfiles
(e.g. a steak-tasting video filed under Sales & Auctions). Batch-classifies
titles via the active AI provider; safe to re-run.

  python -m app.jobs.classify_videos
"""
import time

from ..db import SessionLocal
from ..models import WagyuVideo
from ..services.ai import chat

CATS = ("sire", "sale", "japan", "education", "ranch", "cooking", "general")
SYS = ("You classify Wagyu-cattle YouTube videos by TITLE into exactly one category:\n"
       "sire = a specific bull/cow/lot (breeding animal showcase, semen/embryo lot)\n"
       "sale = an auction/sale event, bidding, sale results\n"
       "japan = Japanese-language or inside-Japan farming/market content\n"
       "education = how-to for BREEDERS (AI, embryo, feeding, grading, starting a herd)\n"
       "ranch = ranch tours, farmer stories, raising cattle (non-Japan)\n"
       "cooking = eating/steak/restaurant/chef/taste-test/butchery content\n"
       "Return ONLY the numbered list with one category word per line.")


def main():
    db = SessionLocal()
    try:
        rows = db.query(WagyuVideo).filter(WagyuVideo.source == "youtube").all()
        changed = 0
        for i in range(0, len(rows), 20):
            batch = rows[i:i + 20]
            prompt = "\n".join(f"{n+1}. {v.title[:110]}" for n, v in enumerate(batch))
            out = None
            for _ in range(2):
                try:
                    out = chat(SYS, prompt, max_tokens=400)
                except Exception:
                    out = None
                if out:
                    break
                time.sleep(5)
            if not out:
                continue
            lines = {}
            for ln in out.splitlines():
                m = ln.strip().lower()
                dot = m.find(".")
                if dot > 0 and m[:dot].isdigit():
                    word = m[dot + 1:].strip().strip("*").split()[0] if m[dot + 1:].strip() else ""
                    if word in CATS:
                        lines[int(m[:dot])] = word
            for n, v in enumerate(batch):
                new = lines.get(n + 1)
                # Trust the LLM except: keep 'sire' when we have a reg match (hard evidence)
                if new and new != v.category and not (v.matched_animal_reg and new != "sire" and v.category == "sire"):
                    v.category = new
                    changed += 1
            db.commit()
            time.sleep(1)
        print(f"Reclassified {changed}/{len(rows)} videos.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
