"""Load the transcripts Veron fetched into the database.

  python -m app.jobs.ingest_transcripts /root/wagyutank/backend/transcripts.json

Idempotent: re-running replaces a video's source transcript rather than
duplicating it, so a better source (a creator's real captions, or a Whisper pass)
can simply overwrite YouTube's ASR later. Derived translations are left alone —
they are regenerable and keyed on prompt+model anyway.
"""
import json
import sys
from datetime import datetime, timezone

from ..db import Base, SessionLocal, engine
from ..models import VideoTranscript, VideoTranscriptAttempt


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m app.jobs.ingest_transcripts <file.json>")
        return
    try:
        rows = json.loads(open(sys.argv[1]).read())
    except Exception as e:
        print(f"ingest_transcripts: cannot read ({e}) — skipping")
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    added = replaced = no_speech = malformed = 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        for r in rows:
            vid, lang = r.get("video_id"), r.get("lang")
            if not vid or not lang:
                malformed += 1
                continue
            # A cue-less result is a real answer, not a failure to report as
            # silence: Whisper's VAD found no speech (music, ambience, a clip with
            # no talking). Writing it as a transcript would be the worst outcome —
            # see VideoTranscriptAttempt — so record the attempt instead so the
            # queue stops handing this video back every night, and NEVER let it
            # become a 0-cue transcript row.
            if not r.get("cues"):
                no_speech += 1
                att = (db.query(VideoTranscriptAttempt)
                         .filter(VideoTranscriptAttempt.video_id == vid,
                                 VideoTranscriptAttempt.lang == lang).first())
                if att:
                    att.tries = (att.tries or 1) + 1
                    att.updated_at = now
                else:
                    db.add(VideoTranscriptAttempt(
                        video_id=vid, lang=lang, reason="no_speech", tries=1))
                continue
            existing = (db.query(VideoTranscript)
                          .filter(VideoTranscript.video_id == vid,
                                  VideoTranscript.lang == lang).first())
            if existing:
                existing.cues = r["cues"]
                existing.source = r.get("source") or existing.source
                existing.word_count = r.get("word_count")
                existing.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                replaced += 1
            else:
                db.add(VideoTranscript(
                    video_id=vid, lang=lang, is_source=bool(r.get("is_source", True)),
                    source=r.get("source") or "youtube_asr",
                    cues=r["cues"], word_count=r.get("word_count")))
                added += 1
        db.commit()
    finally:
        db.close()
    # Report every bucket. The old line said "+4 new, 0 refreshed (of 18 fetched)"
    # and left 14 rows unaccounted for, which reads as a silent failure.
    print(f"Transcripts: +{added} new, {replaced} refreshed, "
          f"{no_speech} no-speech (recorded, won't requeue), {malformed} malformed "
          f"— of {len(rows)} fetched")


if __name__ == "__main__":
    main()
