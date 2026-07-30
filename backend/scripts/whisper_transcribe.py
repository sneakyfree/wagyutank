#!/usr/bin/env python3
"""Transcribe a video's audio with Whisper on the 5090. RUNS ON VERON.

  whisper_transcribe.py <video_id> [--lang ja] [--model large-v3] [--out f.json]

Why bother when YouTube already hands us an ASR track:

  1. QUALITY AT THE SOURCE. Everything downstream inherits it — translating a bad
     transcript beautifully still yields nonsense. YouTube's ASR is general-purpose
     and mangles exactly the words that matter here: 但馬 (Tajima), 種雄牛
     (breeding bull), 霜降り (marbling), sire names, registration numbers.
  2. THE GLOSSARY. Whisper takes an initial_prompt, so we can prime it with the
     breed's vocabulary. That is a lever YouTube simply does not give us.
  3. IT SIDESTEPS THE ToS QUESTION. Transcribing audio we stream is a different
     act from lifting a caption file.
  4. It works on videos with NO captions at all — a third of the sample had none.

Deliberately not wired into the nightly path yet: this is the evaluation harness
for the head-to-head against YouTube's ASR. Promote it to the default source only
if it clearly wins.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile

# Primes Whisper with the domain's proper nouns so it stops guessing at them.
# Kept in the video's own language — an initial_prompt works by continuation, so
# it must read like the audio, not like an instruction.
GLOSSARY_JA = (
    "和牛の話です。但馬牛、気高、藤良、糸桜、そして褐毛和種（あか牛）の血統について。"
    # "BMS" was written БМS with a CYRILLIC Б and М. A prompt works by
    # continuation, so priming the model with a nonsense token teaches it a
    # nonsense token — the one term in this list most likely to appear next to a
    # grade number, mis-seeded.
    "種雄牛、繁殖牛、受精卵、精液ストロー、人工授精、枝肉、霜降り、BMS、A5等級、"
    "全共（全国和牛能力共進会）、松阪牛、神戸ビーフ、宮崎牛、鹿児島黒牛。"
)
# English had NO glossary, so every English video was transcribed unprimed —
# and priming is the whole reason Whisper beat YouTube's ASR on Japanese
# (炭火焼肉 vs "スビ"). Unprimed, English ASR mangles exactly the words that
# matter here: sire names are Japanese loanwords in an English sentence
# (Michifuku, Itoshigenami, Shigeshigenami), and the grading vocabulary is
# initialisms a general model renders phonetically. Same continuation trick —
# it reads like a rancher talking, not like an instruction.
GLOSSARY_EN = (
    "We're talking Wagyu genetics today — fullblood and purebred cattle, Akaushi "
    "and Japanese Black. Bloodlines like Tajima, Kedaka, Itozakura, Fujiyoshi and "
    "Shimane, and sires including Michifuku, Itoshigenami, Shigeshigenami, "
    "Fukutsuru, Kitaguni 7/8, Mt. Fuji, Rueshaw, Yasufuku and Dai 7 Itozakura. "
    "We'll cover semen straws, embryo transfer, IVF and AI, EPDs and EBVs, "
    "marbling score, BMS, IMF percentage, ribeye area, carcass and yield grade, "
    "F1 crosses, dams and progeny, feedlot performance and the CSS export protocol."
)
GLOSSARY = {"ja": GLOSSARY_JA, "en": GLOSSARY_EN}


def audio_for(video_id: str, dest: str) -> str | None:
    """Pull audio only — we never keep the video."""
    cmd = ["yt-dlp", "-f", "bestaudio", "-x", "--audio-format", "wav",
           "--audio-quality", "0", "-o", dest,
           f"https://www.youtube.com/watch?v={video_id}"]
    subprocess.run(cmd, capture_output=True, timeout=900, check=False)
    for cand in (dest, dest + ".wav", os.path.splitext(dest)[0] + ".wav"):
        if os.path.exists(cand):
            return cand
    return None


def _load(model_name: str):
    """GPU if there is room, CPU otherwise. The 5090 is SHARED — Ollama keeps a
    32B model resident for other platforms and routinely leaves under a gigabyte
    free, which OOMs every load. Transcription must degrade to CPU rather than
    fail: slower is fine, a dead nightly job is not. Never evict someone else's
    model to make room."""
    from faster_whisper import WhisperModel
    try:
        return WhisperModel(model_name, device="cuda", compute_type="int8_float16")
    except Exception as e:
        print(f"  GPU unavailable ({str(e)[:60]}) — falling back to CPU", flush=True)
        return WhisperModel(model_name, device="cpu", compute_type="int8",
                            cpu_threads=os.cpu_count() or 8)


def transcribe(path: str, lang: str, model_name: str) -> list[dict]:
    model = _load(model_name)
    segments, _info = model.transcribe(
        path, language=lang, vad_filter=True,
        initial_prompt=GLOSSARY.get(lang), beam_size=5, condition_on_previous_text=True,
    )
    out = []
    for s in segments:
        txt = (s.text or "").strip()
        if txt:
            out.append({"t": round(s.start, 2), "d": round(max(0.8, s.end - s.start), 2), "x": txt})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    # YouTube ids are base64url, so about one in 64 STARTS WITH A HYPHEN and
    # argparse reads it as an option: "-_7vZYqZvYM" died with "the following
    # arguments are required: video_id". It had been silently skipping those
    # videos forever — not one transcript in the database had a hyphen-leading
    # id. Callers should use the --video-id=<id> form, which argparse parses
    # unambiguously even when the value looks like a flag; the positional stays
    # for hand use with ordinary ids.
    ap.add_argument("video_id", nargs="?")
    ap.add_argument("--video-id", dest="video_id_opt", default="")
    ap.add_argument("--lang", default="ja")
    ap.add_argument("--model", default="large-v3-turbo")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    video_id = args.video_id_opt or args.video_id
    if not video_id:
        ap.error("a video id is required (prefer --video-id=<id>)")

    with tempfile.TemporaryDirectory() as td:
        wav = audio_for(video_id, os.path.join(td, "a"))
        if not wav:
            print("could not fetch audio")
            return
        print(f"  audio {os.path.getsize(wav)//1024}KB → whisper {args.model} ({args.lang})", flush=True)
        cues = transcribe(wav, args.lang, args.model)

    rec = {"video_id": video_id, "lang": args.lang, "source": "whisper",
           "is_source": True, "cues": cues,
           "word_count": sum(len(c["x"]) for c in cues)}
    if args.out:
        json.dump([rec], open(args.out, "w"), ensure_ascii=False)
        # Say which of the two things happened. "wrote 0 cues" read as success and
        # hid 14 no-speech videos behind a cheerful log line; the VAD returning
        # nothing is a verdict about the audio, not a fault to gloss over.
        if cues:
            print(f"  wrote {len(cues)} cues → {args.out}")
        else:
            print(f"  NO SPEECH detected (VAD found none) → {args.out}")
    else:
        for c in cues[:12]:
            print(f"    {c['t']:7.1f}s  {c['x']}")
        print(f"  ({len(cues)} cues)")


if __name__ == "__main__":
    main()
