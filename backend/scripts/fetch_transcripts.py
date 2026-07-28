#!/usr/bin/env python3
"""Fetch source-language transcripts for videos. RUNS ON VERON, not the VPS.

Same split as the Roundup crawl and for the same reason: Veron has the
residential IP and the yt-dlp toolchain, the VPS has the database. This writes a
JSON file that jobs.ingest_transcripts loads on the other side.

  fetch_transcripts.py --queue queue.json --out transcripts.json [--limit 40]

REQUIRES A JS RUNTIME. Without one yt-dlp cannot solve YouTube's player
challenge and every caption download fails with HTTP 429 — that was the whole
blocker. Installing deno (~/.deno/bin) fixed it outright; the remaining
"no impersonate target" warning is cosmetic and downloads succeed regardless.

YouTube's ASR VTT needs real cleaning, not a naive parse:
  - every cue carries inline word timings, `宝塚<00:00:05.359><c>市</c>…`
  - cues come in a ROLLING WINDOW: each one repeats the tail of the previous
    line and appends a few new words, so a naive parse yields text roughly
    doubled and unreadable as subtitles.
Both are handled below. Getting this wrong poisons every downstream translation,
which is the expensive part — the source transcript is the durable asset.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

_TAG = re.compile(r"<\d{2}:\d{2}:\d{2}\.\d{3}>|</?c[^>]*>")
_TS = re.compile(r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s+-->\s+(\d{2}):(\d{2}):(\d{2})\.(\d{3})")


def _secs(h, m, s, ms) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(text: str) -> list[dict]:
    """WEBVTT → [{t, d, x}], cleaned for YouTube's auto-caption format.

    YouTube's ASR VTT emits cues in PAIRS to produce the live-typing effect:

        00:00:04.520 --> 00:00:10.270   宝塚<00:00:05.359><c>市</c>…   ← rolling, tagged
        00:00:10.270 --> 00:00:10.280   宝塚市小林市にある和牛…            ← settled, ~10ms
        00:00:10.280 --> 00:00:12.110   宝塚市小林市…/やっ<…><c>て</c>…   ← next rolling

    Only the SETTLED cues carry finished, untagged text. Taking everything (or
    naively de-prefixing) leaves each line stuttered two or three times — which
    then gets translated, and paid for, three times over. So: keep the settled
    cues, and give each one a display window running to the start of the next.
    """
    cues: list[tuple[float, float, str]] = []
    block: list[str] = []
    start = end = None

    def flush():
        nonlocal block, start, end
        if start is not None and block:
            # A settled cue is the one whose text carries no inline word timings.
            joined = " ".join(b for b in block if b.strip())
            if joined and "<" not in joined:
                cues.append((start, end, re.sub(r"\s+", " ", joined).strip()))
        block = []

    for line in text.splitlines() + [""]:
        m = _TS.search(line)
        if m:
            flush()
            start = _secs(*m.groups()[:4])
            end = _secs(*m.groups()[4:])
        elif not line.strip():
            flush()
            start = end = None
        elif line.strip().upper().startswith(("WEBVTT", "KIND:", "LANGUAGE:")):
            continue
        else:
            block.append(line.rstrip())
    flush()

    # Drop consecutive duplicates, then run each cue until the next one starts.
    out: list[dict] = []
    for s_, e_, txt in cues:
        if out and out[-1]["x"] == txt:
            continue
        out.append({"t": round(s_, 2), "d": 0.0, "x": txt})
    for i, c in enumerate(out):
        nxt = out[i + 1]["t"] if i + 1 < len(out) else c["t"] + 4.0
        c["d"] = round(max(0.8, min(nxt - c["t"], 12.0)), 2)
    return out


def fetch_one(video_id: str, lang: str, timeout: int = 180) -> tuple[list[dict], str] | None:
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "cap")
        cmd = ["yt-dlp", "--skip-download", "--sub-format", "vtt",
               "--sub-lang", lang, "-o", base,
               f"https://www.youtube.com/watch?v={video_id}"]
        # Prefer a real uploaded caption track; fall back to YouTube's ASR.
        for flag, kind in (("--write-subs", "youtube_human"), ("--write-auto-subs", "youtube_asr")):
            try:
                subprocess.run(cmd + [flag], capture_output=True, timeout=timeout, check=False)
            except subprocess.TimeoutExpired:
                continue
            for fn in os.listdir(td):
                if fn.endswith(".vtt"):
                    cues = parse_vtt(open(os.path.join(td, fn), encoding="utf-8").read())
                    os.remove(os.path.join(td, fn))
                    if cues:
                        return cues, kind
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", required=True, help="JSON [{video_id, lang}] to fetch")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()

    queue = json.load(open(args.queue))[: args.limit]
    print(f"fetching transcripts for {len(queue)} videos…", flush=True)
    out = []
    for i, item in enumerate(queue, 1):
        vid, lang = item["video_id"], item.get("lang") or "ja"
        got = fetch_one(vid, lang)
        if got:
            cues, kind = got
            words = sum(len(c["x"]) for c in cues)
            out.append({"video_id": vid, "lang": lang, "source": kind,
                        "is_source": True, "cues": cues, "word_count": words})
            print(f"  [{i}/{len(queue)}] {vid} {lang} · {len(cues)} cues · {kind}", flush=True)
        else:
            print(f"  [{i}/{len(queue)}] {vid} {lang} · none", flush=True)
    json.dump(out, open(args.out, "w"), ensure_ascii=False)
    print(f"wrote {len(out)} transcripts → {args.out}")
    if not out:
        sys.exit(0)


if __name__ == "__main__":
    main()
