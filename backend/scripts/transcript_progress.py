#!/usr/bin/env python3
"""How far along is video-transcript translation, honestly.

  python scripts/transcript_progress.py

The old ad-hoc `prog.py` computed the denominator as `ja_sources * 13`, which
assumed every source transcript was Japanese. Once the 2026-07-30 language audit
relabelled 11 videos to zh/en, the numerator still counted THEIR translations
while the denominator had shrunk — and it printed "613 / 481 (127%)". A progress
number that can exceed 100% is not measuring what it claims.

The real target is per source: every site language EXCEPT the one the video is
already spoken in. So it is summed per transcript, not multiplied by a constant.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import tank                      # noqa: E402
from app.db import SessionLocal           # noqa: E402
from app.models import VideoTranscript    # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        langs = [l for l in (tank.config().get("langs") or [])]
        srcs = db.query(VideoTranscript).filter(
            VideoTranscript.is_source == True).all()          # noqa: E712
        have = {(t.video_id, t.lang) for t in db.query(VideoTranscript).filter(
            VideoTranscript.is_source == False).all()}        # noqa: E712

        want = done = 0
        by_src_lang: dict[str, list[int]] = {}
        for s in srcs:
            targets = [l for l in langs if l != s.lang]
            got = sum(1 for l in targets if (s.video_id, l) in have)
            want += len(targets)
            done += got
            d, w = by_src_lang.setdefault(s.lang, [0, 0])
            by_src_lang[s.lang] = [d + got, w + len(targets)]

        cues = sum(len(t.cues or []) for t in db.query(VideoTranscript).filter(
            VideoTranscript.is_source == False).all())        # noqa: E712

        print(f"  site languages:     {len(langs)}  ({','.join(langs)})")
        print(f"  source transcripts: {len(srcs)}")
        for lang, (d, w) in sorted(by_src_lang.items()):
            n = sum(1 for s in srcs if s.lang == lang)
            print(f"     {lang}: {n:3d} videos → {d:4d}/{w:4d} translated")
        pct = 100 * done // max(want, 1)
        print(f"  translated pairs:   {done} / {want}  ({pct}%)")
        print(f"  translated cues:    {cues:,}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
