#!/usr/bin/env bash
# Harvest source-language transcripts for a tank's videos. RUNS ON VERON.
#   tank-transcripts.sh <tank_key> [limit]
#
# Same split as tank-crawl.sh: Veron has the residential IP and the yt-dlp
# toolchain, the VPS has the database. Ask the VPS what is missing, fetch it
# here, ship it back.
#
# NEEDS A JS RUNTIME on PATH. Without one every caption download fails with
# HTTP 429 — that was the original blocker, and deno fixes it outright.
set -e
KEY="${1:?usage: tank-transcripts.sh <tank_key> [limit] [--captions]}"
LIMIT="${2:-40}"
# Whisper on the 5090 is the DEFAULT source. Head-to-head on real Japanese farm
# audio it beat YouTube's ASR outright — 12 complete punctuated sentences against
# 28 fragments with no punctuation at all, and it got the domain words right where
# YouTube did not (炭火焼肉 vs "スビ", the restaurant name たんくろ vs "タクロ").
# It also works on videos with NO captions (a third of the sample) and
# transcribing audio sidesteps the caption-file ToS question. Pass --captions to
# fall back to yt-dlp caption fetching.
MODE="whisper"
[ "${3:-}" = "--captions" ] && MODE="captions"
WHISPER_PY="$HOME/.venvs/whisper/bin/python"
WHISPER_SP="$HOME/.venvs/whisper/lib/python3.12/site-packages"

# Share the crawl lock: both jobs hammer the same residential IP, and running a
# transcript sweep during a Roundup crawl is how you earn a rate-limit ban.
LOCK="/tmp/tank-crawl.lock"
if [ -z "${TANK_CRAWL_LOCKED:-}" ]; then
  export TANK_CRAWL_LOCKED=1
  exec flock -w 21600 "$LOCK" "$0" "$@"
fi

REPO="$HOME/wagyutank"
VPS="root@72.60.118.54"
export PATH="$HOME/.deno/bin:$HOME/.local/bin:$PATH"
echo "===== $KEY transcripts $(date) ====="
cd "$REPO" && git pull -q 2>/dev/null || true

command -v deno >/dev/null || echo "WARNING: no JS runtime on PATH — caption fetches will 429"

Q=/tmp/${KEY}-transcript-queue.json
OUT=/tmp/${KEY}-transcripts.json
ssh "$VPS" "cd /root/wagyutank/backend && set -a && . ../tanks/$KEY/tank.env && set +a && \
  .venv/bin/python -m app.jobs.export_transcript_queue /tmp/${KEY}_tq.json --limit $LIMIT"
scp -q "$VPS:/tmp/${KEY}_tq.json" "$Q"
[ -s "$Q" ] || { echo "no queue file — skipping"; exit 0; }

if [ "$MODE" = "whisper" ] && [ -x "$WHISPER_PY" ]; then
  # faster-whisper needs its CUDA libs on the loader path; they ship inside the
  # venv as nvidia-* wheels and are NOT on the system path.
  export LD_LIBRARY_PATH="$WHISPER_SP/nvidia/cublas/lib:$WHISPER_SP/nvidia/cuda_nvrtc/lib:$WHISPER_SP/nvidia/cudnn/lib:${LD_LIBRARY_PATH:-}"
  echo "[]" > "$OUT"
  python3 - "$Q" "$OUT" "$LIMIT" <<'PYEOF'
import json, subprocess, sys, os
queue, out, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
items = json.load(open(queue))[:limit]
py = os.path.expanduser("~/.venvs/whisper/bin/python")
script = os.path.expanduser("~/wagyutank/backend/scripts/whisper_transcribe.py")
got = []
for i, it in enumerate(items, 1):
    tmp = f"/tmp/_wh_{it['video_id']}.json"
    r = subprocess.run([py, script, it["video_id"], "--lang", it.get("lang") or "ja",
                        "--out", tmp], capture_output=True, text=True, timeout=1800)
    if os.path.exists(tmp):
        got.extend(json.load(open(tmp)))
        os.remove(tmp)
        print(f"  [{i}/{len(items)}] {it['video_id']} whisper ok", flush=True)
    else:
        print(f"  [{i}/{len(items)}] {it['video_id']} whisper failed: {r.stderr.strip()[-120:]}", flush=True)
json.dump(got, open(out, "w"), ensure_ascii=False)
print(f"wrote {len(got)} transcripts -> {out}")
PYEOF
else
  python3 "$REPO/backend/scripts/fetch_transcripts.py" --queue "$Q" --out "$OUT" --limit "$LIMIT"
fi
[ -s "$OUT" ] || { echo "nothing fetched"; exit 0; }

scp -q "$OUT" "$VPS:/root/wagyutank/backend/${KEY}_transcripts.json"
ssh "$VPS" "cd /root/wagyutank/backend && set -a && . ../tanks/$KEY/tank.env && set +a && \
  .venv/bin/python -m app.jobs.ingest_transcripts ${KEY}_transcripts.json"
rm -f "$Q" "$OUT"
echo "===== $KEY transcripts done $(date) ====="
