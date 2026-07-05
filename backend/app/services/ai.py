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
    """Ad copy / translation via the Anthropic Messages API (Job 2)."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ad_copy_api_key)
    facts = {
        "product": _PRODUCT_NOUN.get(product_type, "genetics"),
        "animal": animal.name,
        "registration": animal.registration_no,
        "bloodline": animal.bloodline,
        "bloodline_detail": animal.bloodline_detail,
        "breed": animal.breed,
        "sire": animal.sire_name,
    }
    lang_note = "" if language in ("en", "", None) else f" Write the listing in {language}."
    msg = client.messages.create(
        model=settings.ad_copy_model,
        max_tokens=400,
        system=(
            "You write concise, accurate, persuasive marketplace listings for frozen Wagyu "
            "genetics (semen, embryos, cloning rights). 2-4 sentences. Never invent facts, "
            "pedigree, or EPDs not given. No emojis, no hype clichés." + lang_note
        ),
        messages=[{"role": "user", "content": f"Write the listing copy from these facts: {facts}"}],
    )
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()


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


_PEDIGREE_TOOL = {
    "name": "record_pedigree",
    "description": "Record the Wagyu animal's registry details read from the screenshot.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "registration_no": {"type": "string"},
            "animal_type": {"type": "string", "enum": ["bull", "cow", "steer"]},
            "breed": {"type": "string"},
            "bloodline": {"type": "string"},
            "bloodline_detail": {"type": "string"},
            "birth_year": {"type": "integer"},
            "sire_reg": {"type": "string"},
            "dam_reg": {"type": "string"},
            "sire_name": {"type": "string"},
            "dam_name": {"type": "string"},
            "registry": {"type": "string"},
        },
        "required": ["name"],
    },
}


def _call_vision(image_bytes: bytes, filename: str) -> dict:
    """Pedigree extraction from a registry screenshot via Claude vision + forced tool use (Job 1)."""
    import base64

    import anthropic

    media_type = "image/png"
    low = filename.lower()
    if low.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif low.endswith(".webp"):
        media_type = "image/webp"

    client = anthropic.Anthropic(api_key=settings.vision_api_key)
    msg = client.messages.create(
        model=settings.vision_model,
        max_tokens=700,
        tools=[_PEDIGREE_TOOL],
        tool_choice={"type": "tool", "name": "record_pedigree"},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": media_type,
                    "data": base64.b64encode(image_bytes).decode(),
                }},
                {"type": "text", "text": (
                    "This is a screenshot of a Wagyu animal's registry page. Extract the animal's "
                    "details. Only include fields you can actually read; omit anything uncertain."
                )},
            ],
        }],
    )
    for block in msg.content:
        if getattr(block, "type", "") == "tool_use":
            return dict(block.input)
    return {"name": "", "_needs_manual_entry": True}
