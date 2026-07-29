"""Translate stored source transcripts into the tank's other languages.

  python -m app.jobs.translate_transcripts [--langs ja,fr] [--limit 5] [--dry]

Runs on the DURABLE tier, because this is the whole reason to own transcripts at
all. YouTube's auto-translate is a machine translating machine-transcribed audio
with no domain knowledge — it does not know 種雄牛 is a breeding bull, that A5 is
a grade, or that 但馬 is Tajima. Ours does, and the output is cached forever.

TRANSLATED IN WINDOWS, NOT CUE BY CUE. YouTube's ASR chops mid-sentence — a real
example from the corpus splits ございます across two cues:

    こちらはタンでござい
    ますそしてこれがタンクのオリジナル

Hand those to a translator one at a time and you get two fragments of nonsense.
So each request carries a run of consecutive cues plus the neighbours on either
side as context, and the model returns one line per cue. Cue COUNT must round
trip exactly or the subtitles desync from the audio, which is worse than no
subtitles — so a window whose count comes back wrong is retried once and then
skipped, never guessed at.
"""
import argparse
import json
import re

from .. import tank
from ..db import SessionLocal
from ..models import VideoTranscript
from ..services import translate as T
from ..services.ai import chat

WINDOW = 12      # cues translated per request
CONTEXT = 3      # neighbouring cues shown either side, never translated


def _system(target: str) -> str:
    b = tank.brand()
    breed = b.get("breed") or "Wagyu"
    return (
        f"You are subtitling {breed} cattle footage. Translate ONLY the numbered "
        f"lines into natural {target}.\n"
        f"These are speech-recognition cues and they SPLIT MID-SENTENCE. Use the "
        f"CONTEXT lines to understand the sentence, then translate each numbered "
        f"line as the part of the sentence it actually is. Do not merge lines, do "
        f"not add lines, do not translate the context.\n"
        f"Subtitles: keep each line short and readable. Use the industry term — a "
        f"sire is a breeding BULL, a dam is a cow, a unit of frozen semen is an "
        f"insemination straw. Leave animal names, ranch and company names, "
        f"registration numbers, breed names and carcass grades (A5, BMS) exactly "
        f"as they are.\n"
        f"Return ONLY a JSON array of strings, exactly one per numbered line."
    )


def _translate_window(cues, lo, hi, target, model):
    before = [c["x"] for c in cues[max(0, lo - CONTEXT):lo]]
    after = [c["x"] for c in cues[hi:hi + CONTEXT]]
    body = ""
    if before:
        body += "CONTEXT BEFORE (do not translate):\n" + "\n".join(before) + "\n\n"
    body += "TRANSLATE THESE:\n" + "\n".join(
        f"{i + 1}. {cues[lo + i]['x']}" for i in range(hi - lo))
    if after:
        body += "\n\nCONTEXT AFTER (do not translate):\n" + "\n".join(after)

    want = hi - lo
    for _ in range(2):
        try:
            raw = chat(_system(target), body, max_tokens=2400, model=model,
                       provider=T._provider_for(T.DURABLE))
        except Exception as e:
            # Quota refusal means every remaining window fails too — surface it
            # so the caller stops instead of grinding through a whole transcript
            # producing nothing.
            if T._is_rate_limited(e):
                raise T.RateLimited(str(e)[:200]) from e
            # Anything else (a read timeout on a long window is routine with a
            # big model) is retryable — fall through to the retry, and let the
            # window be skipped if it fails twice. Killing the whole run over one
            # slow request threw away every transcript already done.
            raw = None
        if not raw:
            continue
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
        try:
            got = json.loads(raw)
        except Exception:
            continue
        if isinstance(got, list) and len(got) == want and all(isinstance(x, str) for x in got):
            return got
    return None      # count mismatch — skip rather than desync the subtitles


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="")
    ap.add_argument("--limit", type=int, default=5, help="videos per run")
    ap.add_argument("--video", default="", help="a single YouTube id")
    ap.add_argument("--source-lang", default="",
                    help="only transcripts spoken in this language (e.g. ja)")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    if not langs:
        langs = [l for l in (tank.config().get("langs") or []) if l != "en"]
    langs = [l for l in langs if l in T.LANGS]

    model = T._model(T.DURABLE)
    db = SessionLocal()
    try:
        sq = (db.query(VideoTranscript)
                .filter(VideoTranscript.is_source == True))  # noqa: E712
        if args.video:
            sq = sq.filter(VideoTranscript.video_id == args.video)
        if args.source_lang:
            sq = sq.filter(VideoTranscript.lang == args.source_lang)
        sources = sq.order_by(VideoTranscript.id).all()
        done_keys = {(r.video_id, r.lang) for r in db.query(VideoTranscript)
                     .filter(VideoTranscript.is_source == False).all()}  # noqa: E712
        todo = [(s, l) for s in sources for l in langs
                if l != s.lang and (s.video_id, l) not in done_keys]
        print(f"  model={model or '(provider default)'} langs={','.join(langs)}")
        print(f"  {len(sources)} source transcripts · {len(todo)} (video,lang) pairs outstanding")
        if args.dry:
            print("  DRY — nothing translated")
            return

        videos_done = 0
        seen_videos: set[str] = set()
        for src, lang in todo:
            if src.video_id not in seen_videos and videos_done >= args.limit:
                break
            cues = src.cues or []
            if not cues:
                continue
            out, ok = [], True
            try:
                for lo in range(0, len(cues), WINDOW):
                    hi = min(lo + WINDOW, len(cues))
                    got = _translate_window(cues, lo, hi, T.LANGS[lang], model)
                    if got is None:
                        ok = False
                        break
            except T.RateLimited as e:
                print(f"\n  QUOTA EXHAUSTED on {src.video_id} → {lang} — stopping.")
                print(f"    {e}")
                print("    Re-run when the quota resets; completed videos are skipped.")
                return
                out.extend({"t": cues[lo + i]["t"], "d": cues[lo + i]["d"], "x": got[i]}
                           for i in range(hi - lo))
            if not ok:
                print(f"    {src.video_id} → {lang}: window failed, skipped", flush=True)
                continue
            db.add(VideoTranscript(video_id=src.video_id, lang=lang, is_source=False,
                                   source="translated", cues=out,
                                   word_count=sum(len(c["x"]) for c in out)))
            db.commit()
            print(f"    {src.video_id} → {lang}: {len(out)} cues", flush=True)
            if src.video_id not in seen_videos:
                seen_videos.add(src.video_id)
                videos_done += 1
    finally:
        db.close()


if __name__ == "__main__":
    main()
