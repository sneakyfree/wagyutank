"""The Great Sires & Dams of Japan — WagyuTank's own reference encyclopedia of
the breed's legendary animals. Original writing grounded in documented facts
(pedigrees, records, Ono's published rankings), credited to Kenichi Ono's
scholarship and pointing readers to his books. Translatable into every site
language via the cached translation service."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db

router = APIRouter(prefix="/api/canon", tags=["canon"])

DATA = Path(__file__).resolve().parent.parent / "seed" / "data" / "great_sires.json"
_cache: dict = {}


def _load() -> dict:
    if not _cache:
        try:
            _cache.update(json.loads(DATA.read_text()))
        except Exception:
            _cache.update({"attribution": "", "sires": [], "dams": []})
    return _cache


@router.get("")
def canon(lang: str = "en", db: Session = Depends(get_db)):
    d = _load()
    if not lang or lang == "en":
        return d
    from ..services import translate as tr
    # Translate the human-readable prose fields; leave names/regs/facts intact.
    out = {"attribution": tr.translate(db, d.get("attribution", ""), lang)}
    for group in ("sires", "dams"):
        rows = []
        for a in d.get(group, []):
            b = dict(a)
            if a.get("bio"):
                b["bio"] = tr.translate(db, a["bio"], lang)
            if a.get("epithet"):
                b["epithet"], _ = tr.translate_one(db, a["epithet"], lang)
            rows.append(b)
        out[group] = rows
    return out
