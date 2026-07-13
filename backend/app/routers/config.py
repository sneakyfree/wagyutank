"""Public tank config — lets the frontend render brand, product taxonomy, feature
flags and vocabulary from the tank's config instead of hardcoding them. This is
what makes one frontend build serve any tank: HighlandTank hides the Japan hub
and shows only its product types, all from `/api/config`, no code change."""
from fastapi import APIRouter

from .. import tank

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config():
    c = tank.config()
    return {
        "key": c.get("key"),
        "brand": c.get("brand", {}),
        "products": c.get("products", []),
        "features": c.get("features", {}),
        "vocab": c.get("vocab", {}),
        "copy": c.get("copy", {}),
        "langs": c.get("langs", ["en"]),
        # Sister tanks in the cross-site flywheel (empty for standalone tanks) —
        # drives the header cross-site button + per-animal PeerLink chips.
        "network": c.get("network", {}),
        # tankify's deep per-tank substitution pairs — without these in the API
        # payload, an API-baked frontend build silently skips them (they only
        # exist in tank.json otherwise).
        "substitutions": c.get("substitutions", []),
    }
