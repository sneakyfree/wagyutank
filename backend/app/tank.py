"""Tank configuration — the per-breed identity the engine runs on.

The engine is species-neutral; each deployment is one "tank" (WagyuTank,
HighlandTank, …) selected by the TANK env var (default: wagyu). Its identity —
brand, product taxonomy, feature flags, vocabulary — lives in
`tanks/<key>/tank.json`, NOT hardcoded in the engine. This loader reads it once.

If the file is missing (e.g. an odd deploy layout), we fall back to the Wagyu
identity so the engine never hard-fails — config #1 is also the safety net."""
import json
import os
from functools import lru_cache
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # .../wagyutank
_TANK_KEY = os.environ.get("TANK", "wagyu").strip().lower() or "wagyu"

_WAGYU_FALLBACK = {
    "key": "wagyu",
    "brand": {"name": "WagyuTank", "domain": "wagyutank.com",
              "tagline": "The world's marketplace & knowledge hub for frozen Wagyu genetics",
              "species": "cattle", "breed": "Wagyu & Akaushi", "logoText": "WT",
              "colors": {"gold": "#8a6d2b"}, "contactEmail": "office@wagyutank.com",
              "legal": "Salt Lake City, Utah, USA · a Utah company"},
    "products": [
        {"key": "semen", "label": "Semen", "unit": "straw", "icon": "sperm", "fresh_chilled": False},
        {"key": "embryo", "label": "Embryos", "unit": "embryo", "icon": "morula", "fresh_chilled": False},
        {"key": "clone_rights", "label": "Cloning Rights", "unit": "right", "icon": "helix", "fresh_chilled": False},
    ],
    "features": {k: True for k in (
        "roundup", "directory", "help", "ads", "foundation", "history", "news", "videos",
        "price_index", "sale_reports", "catalog", "market_data", "japan_hub", "zenkyo",
        "feeding", "great_sires")},
    "vocab": {"animal_singular": "sire", "animal_plural": "cattle",
              "registry_names": ["American Wagyu Association", "American Akaushi Association"],
              "export_program": "CSS", "news_search_terms": ["Wagyu", "Akaushi", "Kobe beef"],
              "video_search_terms": ["Wagyu cattle", "Wagyu bull", "Akaushi"]},
    "langs": ["en", "es", "pt", "de", "ja", "zh"],
    "crawl": {"cron_offset_min": 0},
}


@lru_cache(maxsize=1)
def config() -> dict:
    path = _REPO_ROOT / "tanks" / _TANK_KEY / "tank.json"
    try:
        cfg = json.loads(path.read_text())
        # merge over the fallback so a partial config can't leave gaps
        merged = dict(_WAGYU_FALLBACK)
        merged.update(cfg)
        for k in ("brand", "features", "vocab"):
            if isinstance(_WAGYU_FALLBACK.get(k), dict) and isinstance(cfg.get(k), dict):
                merged[k] = {**_WAGYU_FALLBACK[k], **cfg[k]}
        return merged
    except Exception:
        return dict(_WAGYU_FALLBACK)


def key() -> str:
    return config().get("key", _TANK_KEY)


def brand() -> dict:
    return config().get("brand", {})


def products() -> list[dict]:
    return config().get("products", [])


def product_keys() -> set[str]:
    return {p["key"] for p in products() if p.get("key")}


def product_meta(pkey: str) -> dict | None:
    for p in products():
        if p.get("key") == pkey:
            return p
    return None


def features() -> dict:
    return config().get("features", {})


def feature_on(name: str) -> bool:
    return bool(config().get("features", {}).get(name, False))


def vocab() -> dict:
    return config().get("vocab", {})
