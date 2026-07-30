"""Spoken-language audit, v3 — Han RUN-LENGTH is the discriminator.

v2 used Mandarin "function words" and produced FALSE POSITIVES: 現在 / 可以 /
所以 / 非常 / 真的 / 一個 are ordinary JAPANESE too, so it flagged
【牛の博物館】種雄牛改良最前線 ("大変お待たせいたしました…", 60% kana) as Chinese.
Relabelling a Japanese video as Chinese is worse than the bug being fixed.

Kana COUNT is also unusable: Whisper given a `ja` hint sprinkles kana into
Mandarin, so a Chinese video can read 48% kana.

What survives both problems is GRAMMAR. Japanese cannot write a long clause
without a kana particle (の は が を に), so consecutive-Han runs stay short;
Mandarin writes whole sentences in unbroken Han. Measured on this corpus the
split is unambiguous and there is nothing near the boundary:
    Japanese : 1.44 - 2.06   (n=30+)
    Mandarin : 3.86 - 10.01  (n=7)
Only genuinely ambiguous Mandarin pronouns are kept as a secondary signal."""
import re
from statistics import mean
from app.db import SessionLocal
from app.models import VideoTranscript as T, WagyuVideo as V

HANRUN = re.compile(r"[一-鿿]+")
KANA = re.compile(r"[぀-ゟ゠-ヿ]")
HANGUL = re.compile(r"[가-힯]")
LATIN = re.compile(r"[A-Za-z]")
# ONLY words with no ordinary Japanese reading. 現在/可以/所以 deliberately absent.
ZH_ONLY = re.compile(r"我們|我们|你們|你们|這個|这个|什麼|什么|沒有|没有|怎麼|怎么|大家好|哪裡|哪里")
RUNLEN_ZH = 3.5          # measured gap: ja tops out at 2.06, zh starts at 3.86

db = SessionLocal()
vids = {v.video_id: v for v in db.query(V).all()}
flag = []
for t in db.query(T).filter(T.is_source == True).order_by(T.video_id):   # noqa: E712
    txt = " ".join(c["x"] for c in (t.cues or []))
    if len(txt) < 60:
        continue
    runs = [len(r) for r in HANRUN.findall(txt)]
    han = sum(runs)
    lat = len(LATIN.findall(txt))
    if len(HANGUL.findall(txt)) > 0.1 * len(txt):
        v = "ko"
    elif han < 20 and lat > 40:
        v = "en"
    elif runs and (mean(runs) >= RUNLEN_ZH or len(ZH_ONLY.findall(txt)) >= 12):
        v = "zh"
    else:
        v = "ja"
    if v != t.lang:
        flag.append((t.video_id, t.lang, v, mean(runs) if runs else 0,
                     len(ZH_ONLY.findall(txt))))
print(f"MISLABELLED: {len(flag)}")
for vid, old, new, rl, zh in flag:
    ttl = (vids.get(vid).title if vids.get(vid) else "")[:50]
    print(f"   {vid:13s} {old} -> {new}  runlen={rl:5.2f} zh_only={zh:4d}  {ttl}")
db.close()
