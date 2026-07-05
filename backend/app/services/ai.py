"""AI services (MASTER_PLAN §7, §9).

Two jobs, split by stakes:
  - Job 1  pedigree extraction from a screenshot  -> accuracy-critical (paid vision API)
  - Job 2  ad-copy generation + translation       -> forgiving (Windy Mind / cheap)

Both have deterministic template fallbacks so the app runs with no keys configured.
Wire real providers in `_call_vision` / `_call_llm` when keys are set.
"""
from __future__ import annotations

from ..config import settings
from ..schemas import AnimalUpsert


# --------------------------------------------------------------------------- #
# Job 2 — ad copy generation
# --------------------------------------------------------------------------- #
_PRODUCT_NOUN = {
    "semen": "semen straws",
    "embryo": "embryos",
    "clone_rights": "cloning rights",
}


def generate_ad_copy(product_type: str, animal: AnimalUpsert, language: str = "en") -> str:
    """Return polished listing copy. Falls back to a strong template if no LLM key."""
    if settings.ad_copy_api_key:
        try:
            return _call_llm(product_type, animal, language)
        except Exception:
            pass  # fall through to template
    return _template_copy(product_type, animal)


def _template_copy(product_type: str, a: AnimalUpsert) -> str:
    noun = _PRODUCT_NOUN.get(product_type, "genetics")
    bits: list[str] = []
    lead = a.name + (f" ({a.registration_no})" if a.registration_no else "")
    if product_type == "clone_rights":
        bits.append(f"Cloning rights to {lead} — bank a legend and make it live again.")
    elif product_type == "embryo":
        sire = a.sire_name or "an elite sire"
        bits.append(f"Full-blood Wagyu embryos out of {lead}, sired by {sire}.")
    else:
        bits.append(f"Premium full-blood Wagyu {noun} from {lead}.")

    if a.bloodline:
        detail = f" — {a.bloodline_detail}" if a.bloodline_detail else ""
        bits.append(f"{a.bloodline} bloodline{detail}.")
    if a.breed:
        bits.append(f"{a.breed} genetics.")
    bits.append(
        "Pedigree verified against the registry (see linked record). "
        "Stored at a professional facility; shipping handled on request."
    )
    return " ".join(bits)


def _call_llm(product_type: str, animal: AnimalUpsert, language: str) -> str:
    """Real LLM call for ad copy / translation. Stubbed until a provider is wired."""
    raise NotImplementedError("Ad-copy LLM provider not configured")


# --------------------------------------------------------------------------- #
# Job 1 — pedigree extraction from a screenshot
# --------------------------------------------------------------------------- #
def extract_pedigree_from_image(image_bytes: bytes, filename: str = "") -> dict:
    """Extract structured pedigree from a registry screenshot.

    Returns a dict shaped like AnimalUpsert. Without a vision key configured this
    returns an empty scaffold so the UI can fall back to manual confirm/entry.
    """
    if settings.vision_api_key:
        try:
            return _call_vision(image_bytes, filename)
        except Exception:
            pass
    return {
        "name": "",
        "registration_no": None,
        "_needs_manual_entry": True,
        "_note": "Vision extraction not configured — confirm the animal manually.",
    }


def _call_vision(image_bytes: bytes, filename: str) -> dict:
    """Real vision-model call with JSON-schema output. Stubbed until wired."""
    raise NotImplementedError("Vision provider not configured")
