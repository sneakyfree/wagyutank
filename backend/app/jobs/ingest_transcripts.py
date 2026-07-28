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
from ..models import VideoTranscript


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
    added = replaced = 0
    try:
        for r in rows:
            vid, lang = r.get("video_id"), r.get("lang")
            if not vid or not lang or not r.get("cues"):
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
    print(f"Transcripts: +{added} new, {replaced} refreshed (of {len(rows)} fetched)")


if __name__ == "__main__":
    main()
