"""Runtime settings — a DB-backed key/value store the admin panel can edit live.

Reads are cached briefly so hot paths (AI provider lookup) don't hit the DB every
call; writes invalidate the cache. Values are JSON (str/int/bool/dict/list)."""
import time

from ..db import SessionLocal
from ..models import Setting

_CACHE: dict[str, tuple[float, object]] = {}
_TTL = 30.0  # seconds


def get(key: str, default=None):
    hit = _CACHE.get(key)
    if hit and (time.monotonic() - hit[0]) < _TTL:
        return hit[1]
    db = SessionLocal()
    try:
        row = db.get(Setting, key)
        val = row.value if row else default
    finally:
        db.close()
    _CACHE[key] = (time.monotonic(), val)
    return val


def get_many(keys: list[str], defaults: dict | None = None) -> dict:
    defaults = defaults or {}
    return {k: get(k, defaults.get(k)) for k in keys}


def set(key: str, value) -> None:
    db = SessionLocal()
    try:
        row = db.get(Setting, key)
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))
        db.commit()
    finally:
        db.close()
    _CACHE[key] = (time.monotonic(), value)


def all() -> dict:
    db = SessionLocal()
    try:
        return {s.key: s.value for s in db.query(Setting).all()}
    finally:
        db.close()
