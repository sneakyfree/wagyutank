#!/usr/bin/env python3
"""Stamp tanks/_template → tanks/<key>, substituting {{PLACEHOLDERS}}.

This is step 0 of a new breed clone: it produces a fillable tank directory (config
+ seed scaffolds) so you never start from a Wagyu-specific copy. You still supply
the breed CONTENT (foundation animals, history, FAQ, seller sites) — see
tanks/_template/README.md and TEMPLATE_SPEC.md §5 — but the structure, brand
plumbing, and placeholders are laid down for you.

    ./deploy/scaffold-content.py <key> \\
        --brand HighlandTank --domain highlandtank.com --breed "Scottish Highland" \\
        --port 8122 --gold '#8a6d2b' [--logo HT] [--cron-offset 60]

Only tokens you pass are substituted; the rest stay as {{TOKENS}} for you to fill
by hand. Refuses to overwrite an existing tanks/<key> unless --force.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TEMPLATE = REPO / "tanks" / "_template"


def _lighten(hex_color: str, amount: float) -> str:
    try:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        r, g, b = (min(255, int(c + (255 - c) * amount)) for c in (r, g, b))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:  # noqa: BLE001
        return hex_color


def _soft(hex_color: str) -> str:
    try:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
        return f"rgba({r},{g},{b},0.13)"
    except Exception:  # noqa: BLE001
        return "rgba(160,160,160,0.13)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key")
    ap.add_argument("--brand", help="brand name, e.g. HighlandTank")
    ap.add_argument("--domain", help="e.g. highlandtank.com")
    ap.add_argument("--breed", help='e.g. "Scottish Highland"')
    ap.add_argument("--species", default="cattle")
    ap.add_argument("--port", type=int, help="API port (next free after 8121…)")
    ap.add_argument("--gold", default="#8a6d2b", help="primary theme colour")
    ap.add_argument("--logo", help="2-letter logo text (default: initials)")
    ap.add_argument("--cron-offset", type=int, default=60, help="crawl stagger minutes")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    dest = REPO / "tanks" / args.key
    if dest.exists() and not args.force:
        print(f"! tanks/{args.key} already exists (use --force to overwrite)", file=sys.stderr)
        sys.exit(2)

    breed = args.breed or ""
    logo = args.logo or "".join(w[0] for w in (args.brand or args.key).replace("Tank", " ").split())[:2].upper()
    subs = {
        "{{KEY}}": args.key,
        "{{BRAND_NAME}}": args.brand or f"{args.key.title()}Tank",
        "{{DOMAIN}}": args.domain or f"{args.key}tank.com",
        "{{BREED}}": breed,
        "{{BREED_UPPER}}": breed.upper(),
        "{{SPECIES}}": args.species,
        "{{LOGO_TEXT}}": logo,
        "{{COLOR_GOLD}}": args.gold,
        "{{COLOR_GOLD_BRIGHT}}": _lighten(args.gold, 0.25),
        "{{COLOR_GOLD_SOFT}}": _soft(args.gold),
        "{{CRON_OFFSET_MIN}}": str(args.cron_offset),
        "{{PORT}}": str(args.port) if args.port else "{{PORT}}",
    }

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(TEMPLATE, dest)
    (dest / "README.md").unlink(missing_ok=True)  # keep the guide in _template only

    stamped = 0
    for p in dest.rglob("*"):
        if not p.is_file():
            continue
        try:
            text = p.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        new = text
        for k, v in subs.items():
            new = new.replace(k, v)
        if new != text:
            p.write_text(new)
            stamped += 1

    remaining = sorted({tok for p in dest.rglob("*") if p.is_file()
                        for tok in _tokens(p)})
    print(f"✓ scaffolded tanks/{args.key} ({stamped} files stamped)")
    if remaining:
        print(f"  still to fill ({len(remaining)} placeholder types): "
              + ", ".join(remaining[:12]) + ("…" if len(remaining) > 12 else ""))
    print("  next: fill seed/ content (foundation_animals, breed_history, faq, "
          "roundup_seeds) then run ./deploy/hatch-tank.sh " + args.key)


def _tokens(path: Path):
    import re
    try:
        return set(re.findall(r"\{\{[A-Z0-9_]+\}\}", path.read_text()))
    except (UnicodeDecodeError, OSError):
        return set()


if __name__ == "__main__":
    main()
