"""Which videos still need a source transcript? Runs on the VPS; Veron consumes it.

  python -m app.jobs.export_transcript_queue /tmp/queue.json [--limit 40]

Source transcripts only — the translations are made here from those, not fetched.
Ordered by views so the videos people actually watch get subtitles first, and
capped per run because YouTube rate-limits caption fetches hard (an unthrottled
sweep is what produced HTTP 429 in testing).
"""
import argparse
import json

from ..db import Base, SessionLocal, engine
from ..models import VideoTranscript, VideoTranscriptAttempt, WagyuVideo


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--lang", default="", help="only videos in this spoken language")
    args = ap.parse_args()

    # This job runs first in the pipeline, so on a tank that has never ingested a
    # transcript the attempts table may not exist yet.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        have = {v for (v,) in db.query(VideoTranscript.video_id)
                .filter(VideoTranscript.is_source == True).all()}  # noqa: E712
        # Videos we already know have no speech to transcribe. Re-offering these
        # means re-downloading their audio every night to reach the same answer,
        # and the residential IP's YouTube budget is the scarce resource here.
        tried = {(v, l) for (v, l) in db.query(VideoTranscriptAttempt.video_id,
                                               VideoTranscriptAttempt.lang).all()}
        q = (db.query(WagyuVideo)
               .filter(WagyuVideo.video_id.isnot(None), WagyuVideo.status == "approved")
               .order_by(WagyuVideo.views.desc().nullslast()))
        if args.lang:
            q = q.filter(WagyuVideo.lang == args.lang)
        out = []
        skipped = 0
        for v in q.all():
            if v.video_id in have:
                continue
            lang = v.lang or "ja"
            if (v.video_id, lang) in tried:
                skipped += 1
                continue
            out.append({"video_id": v.video_id, "lang": lang})
            if len(out) >= args.limit:
                break
        json.dump(out, open(args.out, "w"))
        print(f"transcript queue: {len(out)} videos → {args.out} "
              f"({len(have)} already have a source transcript, "
              f"{skipped} skipped as previously no-speech)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
