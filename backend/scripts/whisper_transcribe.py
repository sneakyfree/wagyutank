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
    "種雄牛、繁殖牛、受精卵、精液ストロー、人工授精、枝肉、霜降り、БМS、A5等級、"
    "全共（全国和牛能力共進会）、松阪牛、神戸ビーフ、宮崎牛、鹿児島黒牛。"
)
GLOSSARY = {"ja": GLOSSARY_JA}


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


def transcribe(path: str, lang: str, model_name: str) -> list[dict]:
    from faster_whisper import WhisperModel
    # int8_float16 keeps the footprint small — Ollama already holds most of the
    # card, and the crawl extraction lane must not be starved.
    model = WhisperModel(model_name, device="cuda", compute_type="int8_float16")
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
    ap.add_argument("video_id")
    ap.add_argument("--lang", default="ja")
    ap.add_argument("--model", default="large-v3")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        wav = audio_for(args.video_id, os.path.join(td, "a"))
        if not wav:
            print("could not fetch audio")
            return
        print(f"  audio {os.path.getsize(wav)//1024}KB → whisper {args.model} ({args.lang})", flush=True)
        cues = transcribe(wav, args.lang, args.model)

    rec = {"video_id": args.video_id, "lang": args.lang, "source": "whisper",
           "is_source": True, "cues": cues,
           "word_count": sum(len(c["x"]) for c in cues)}
    if args.out:
        json.dump([rec], open(args.out, "w"), ensure_ascii=False)
        print(f"  wrote {len(cues)} cues → {args.out}")
    else:
        for c in cues[:12]:
            print(f"    {c['t']:7.1f}s  {c['x']}")
        print(f"  ({len(cues)} cues)")


if __name__ == "__main__":
    main()
