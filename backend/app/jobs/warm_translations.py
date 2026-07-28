"""Pre-translate the durable content into every language the tank offers.

  python -m app.jobs.warm_translations [--langs ja,de] [--dry]

Two reasons this exists.

1. QUALITY. The durable tier — help centre, feeding guide, great-sires
   encyclopedia, breed history, FAQ — is roughly 254k characters of prose that is
   written once and read forever, and it is what makes the site read as the
   authority on the breed. Translating all of it into all five languages costs
   about $32 on the best model available, one time, permanently cached. Nothing
   about that is worth economising on, so the durable tier runs on the best model
   the Windy Mind roster offers (TRANSLATE_MODEL_DURABLE).

2. UX. Translation was entirely lazy, so a Japanese visitor watched the page
   machine-translate in front of them behind a progress banner. Warming means the
   cache is already populated when they arrive and the page just renders.

Idempotent: anything already cached under the current prompt+model key is skipped,
so re-running after a model upgrade re-translates only what actually changed.
"""
import argparse
import json
import sys
from pathlib import Path

from .. import tank
from ..db import SessionLocal
from ..models import Translation
from ..services import translate as T


def _durable_strings() -> list[str]:
    """Collect the prose the durable tier covers, deduplicated."""
    out: list[str] = []

    def walk(o) -> None:
        if isinstance(o, str):
            s = o.strip()
            # Prose only: skip ids, codes, dates, single words.
            if len(s) > 40 and s.count(" ") > 6:
                out.append(s)
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    base = Path(__file__).resolve().parent.parent / "seed" / "data"
    for name in ("help.json", "faq.json", "feeding.json", "great_sires.json",
                 "zenkyo.json", "foundation_animals.json", "foundation_bulls_enriched.json",
                 "foundation_cows_enriched.json", "facilities.json"):
        p = base / name
        if p.exists():
            try:
                walk(json.loads(p.read_text()))
            except Exception:
                pass
    # The tank's own seed content wins where it exists (clones ship their own).
    for name in ("faq.json", "facilities.json"):
        sp = tank.seed_path_strict(name)
        if sp is not None:
            try:
                walk(json.loads(sp.read_text()))
            except Exception:
                pass
    for md in ("breed_history.md",):
        sp = tank.seed_path_strict(md)
        p = sp if sp is not None else (base / md)
        if p and Path(p).exists():
            # Long-form: warm it paragraph by paragraph, which is how translate()
            # chunks it anyway, so the cache keys line up.
            for para in Path(p).read_text().split("\n\n"):
                para = para.strip()
                if len(para) > 40 and para.count(" ") > 6:
                    out.append(para)

    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--langs", default="")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    langs = [l.strip() for l in args.langs.split(",") if l.strip()]
    if not langs:
        # tank.json `langs` is the set this tank actually offers — a clone that
        # ships English-only warms nothing.
        langs = [l for l in (tank.config().get("langs") or []) if l != "en"]
    langs = [l for l in langs if l in T.LANGS]
    if not langs:
        print("warm: no non-English languages configured for this tank — nothing to do")
        return

    strings = _durable_strings()
    chars = sum(len(s) for s in strings)
    model = T._model(T.DURABLE) or "(provider default)"
    print(f"  tank={tank.key()} langs={','.join(langs)} model={model}")
    print(f"  durable strings: {len(strings)} ({chars:,} chars) x {len(langs)} languages")

    db = SessionLocal()
    try:
        todo = 0
        for lang in langs:
            for s in strings:
                if not db.query(Translation).filter(
                        Translation.cache_key == T._key(s, lang, T.DURABLE)).first():
                    todo += 1
        print(f"  not yet cached under this prompt+model: {todo}")
        if args.dry:
            print("  DRY — nothing translated")
            return
        done = failed = 0
        for lang in langs:
            for i, s in enumerate(strings, 1):
                try:
                    out = T.translate(db, s, lang, tier=T.DURABLE, raise_on_quota=True)
                    if out == s and len(s) > 60:
                        failed += 1          # fell back to English
                    else:
                        done += 1
                except T.RateLimited as e:
                    # STOP, do not spin. Every remaining call would fail the same
                    # way, and the job would keep printing progress against a
                    # cache that is no longer growing — which is how this went
                    # unnoticed for twenty minutes on 2026-07-28. The job is
                    # idempotent, so the next run resumes exactly here.
                    print(f"\n  QUOTA EXHAUSTED at [{lang}] {i}/{len(strings)} — stopping.")
                    print(f"    {e}")
                    print(f"    warmed this run: {done} ok, {failed} fell back")
                    print("    Re-run when the quota resets; it resumes where it left off.")
                    return
                except Exception as e:
                    failed += 1
                    print(f"    [{lang}] error on string {i}: {str(e)[:90]}")
                if i % 25 == 0:
                    print(f"    [{lang}] {i}/{len(strings)}…", flush=True)
        print(f"  warmed: {done} ok, {failed} fell back to English")
    finally:
        db.close()


if __name__ == "__main__":
    main()
