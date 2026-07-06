"""AI services (MASTER_PLAN §7, §9) — provider-swappable.

Two jobs:
  - Job 1  pedigree extraction from a screenshot   (vision + structured output)
  - Job 2  ad-copy generation + translation

Providers (select with AI_PROVIDER):
  - anthropic  : the Anthropic Messages API. Haiku for both jobs during testing so all
                 Haiku spend on the account is attributable to WagyuTank.
  - openai     : any OpenAI-compatible chat/completions endpoint.
  - windymind  : Grant's free-compute gateway (OpenAI-compatible; point base_url at it).

Everything degrades gracefully: if the selected provider has no key configured, both jobs
fall back to a deterministic template so the app keeps working with zero cost or setup.
Swapping providers or dropping in a real key is a .env change — no code edit.
"""
from __future__ import annotations

import base64
import json

import httpx

from ..config import settings
from ..schemas import AnimalUpsert

_PRODUCT_NOUN = {"semen": "semen straws", "embryo": "embryos", "clone_rights": "cloning rights"}

_AD_SYSTEM = (
    "You write concise, accurate, persuasive marketplace listings for frozen Wagyu genetics "
    "(semen, embryos, cloning rights). 2-4 sentences. Never invent facts, pedigree, or EPDs "
    "not provided. No emojis, no hype clichés."
)

_PEDIGREE_FIELDS = (
    "name, registration_no, animal_type (bull/cow/steer), breed, bloodline, bloodline_detail, "
    "birth_year (integer), sire_reg, dam_reg, sire_name, dam_name, registry"
)

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


# --------------------------------------------------------------------------- #
# Provider resolution
# --------------------------------------------------------------------------- #
def _active_provider_name() -> str:
    """Runtime provider — admin can swap it live (settings store) without a redeploy."""
    try:
        from . import settings_store
        return (settings_store.get("ai_provider", settings.ai_provider) or "anthropic").lower()
    except Exception:
        return (settings.ai_provider or "anthropic").lower()


def _model_override(key: str, fallback: str) -> str:
    try:
        from . import settings_store
        return settings_store.get(key, None) or fallback
    except Exception:
        return fallback


def _provider() -> dict | None:
    """Return the active provider's config, or None to use the template fallback."""
    p = _active_provider_name()
    if p == "template":
        return None
    if p == "anthropic" and settings.anthropic_api_key:
        return {"kind": "anthropic", "key": settings.anthropic_api_key,
                "vision_model": _model_override("anthropic_vision_model", settings.anthropic_vision_model),
                "adcopy_model": _model_override("anthropic_adcopy_model", settings.anthropic_adcopy_model)}
    if p == "openai" and settings.openai_api_key:
        return {"kind": "openai", "key": settings.openai_api_key, "base_url": settings.openai_base_url,
                "vision_model": _model_override("openai_vision_model", settings.openai_vision_model),
                "adcopy_model": _model_override("openai_adcopy_model", settings.openai_adcopy_model)}
    if p == "windymind" and settings.windymind_api_key and settings.windymind_base_url:
        return {"kind": "windymind", "key": settings.windymind_api_key, "base_url": settings.windymind_base_url,
                "vision_model": settings.windymind_vision_model or "",
                "adcopy_model": _model_override("windymind_adcopy_model", settings.windymind_adcopy_model or "auto")}
    return None


def active_provider_label() -> str:
    prov = _provider()
    if not prov:
        return "template (no AI key configured)"
    return f"{settings.ai_provider}:{prov['adcopy_model']}"


def chat(system: str, user: str, max_tokens: int = 1500) -> str | None:
    """Generic single-shot chat via the active provider (used by the aggregator's
    extraction step). Returns None if no provider is configured."""
    prov = _provider()
    if not prov:
        return None
    model = prov["adcopy_model"]
    if prov["kind"] == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=prov["key"])
        msg = client.messages.create(
            model=model, max_tokens=max_tokens,
            system=system, messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    path = "/v1/chat" if prov["kind"] == "windymind" else "/chat/completions"
    r = httpx.post(
        f"{prov['base_url'].rstrip('/')}{path}",
        headers={"Authorization": f"Bearer {prov['key']}"},
        json={"model": model, "max_tokens": max_tokens,
              "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
        timeout=60,
    )
    r.raise_for_status()
    choice = r.json()["choices"][0]
    return (choice.get("message", {}).get("content") or choice.get("content") or "").strip()


# --------------------------------------------------------------------------- #
# Job 2 — ad copy
# --------------------------------------------------------------------------- #
def generate_ad_copy(product_type: str, animal: AnimalUpsert, language: str = "en") -> str:
    prov = _provider()
    if prov:
        try:
            return _complete(prov, product_type, animal, language)
        except Exception:
            pass  # fall through to template
    return _template_copy(product_type, animal)


def _facts(product_type: str, a: AnimalUpsert) -> str:
    return json.dumps({
        "product": _PRODUCT_NOUN.get(product_type, "genetics"),
        "animal": a.name, "registration": a.registration_no,
        "bloodline": a.bloodline, "bloodline_detail": a.bloodline_detail,
        "breed": a.breed, "sire": a.sire_name,
    })


def _complete(prov: dict, product_type: str, animal: AnimalUpsert, language: str) -> str:
    lang = "" if language in ("en", "", None) else f" Write the listing in {language}."
    user = f"Write the listing copy from these facts: {_facts(product_type, animal)}"
    if prov["kind"] == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=prov["key"])
        msg = client.messages.create(
            model=prov["adcopy_model"], max_tokens=400,
            system=_AD_SYSTEM + lang,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    if prov["kind"] == "windymind":
        # Windy Mind broker — OpenAI-shaped body at /v1/chat, text-only, free provider routing.
        r = httpx.post(
            f"{prov['base_url'].rstrip('/')}/v1/chat",
            headers={"Authorization": f"Bearer {prov['key']}"},
            json={"model": prov["adcopy_model"], "max_tokens": 400,
                  "messages": [{"role": "system", "content": _AD_SYSTEM + lang},
                               {"role": "user", "content": user}]},
            timeout=45,
        )
        r.raise_for_status()
        choice = r.json()["choices"][0]
        return (choice.get("message", {}).get("content") or choice.get("content") or "").strip()
    # openai-compatible
    r = httpx.post(
        f"{prov['base_url'].rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {prov['key']}"},
        json={"model": prov["adcopy_model"], "max_tokens": 400,
              "messages": [{"role": "system", "content": _AD_SYSTEM + lang},
                           {"role": "user", "content": user}]},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _template_copy(product_type: str, a: AnimalUpsert) -> str:
    noun = _PRODUCT_NOUN.get(product_type, "genetics")
    lead = a.name + (f" ({a.registration_no})" if a.registration_no else "")
    bits: list[str] = []
    if product_type == "clone_rights":
        bits.append(f"Cloning rights to {lead} — bank a legend and make it live again.")
    elif product_type == "embryo":
        bits.append(f"Full-blood Wagyu embryos out of {lead}, sired by {a.sire_name or 'an elite sire'}.")
    else:
        bits.append(f"Premium full-blood Wagyu {noun} from {lead}.")
    if a.bloodline:
        detail = f" — {a.bloodline_detail}" if a.bloodline_detail else ""
        bits.append(f"{a.bloodline} bloodline{detail}.")
    if a.breed:
        bits.append(f"{a.breed} genetics.")
    bits.append("Pedigree verified against the registry (see linked record). "
                "Stored at a professional facility; shipping handled on request.")
    return " ".join(bits)


# --------------------------------------------------------------------------- #
# Job 1 — pedigree extraction from a screenshot
# --------------------------------------------------------------------------- #
def extract_pedigree_from_image(image_bytes: bytes, filename: str = "") -> dict:
    prov = _provider()
    if prov:
        try:
            return _vision(prov, image_bytes, filename)
        except Exception:
            pass
    return {"name": "", "registration_no": None, "_needs_manual_entry": True,
            "_note": "AI extraction not configured — confirm the animal manually."}


def _media_type(filename: str) -> str:
    low = filename.lower()
    if low.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if low.endswith(".webp"):
        return "image/webp"
    return "image/png"


def _vision(prov: dict, image_bytes: bytes, filename: str) -> dict:
    if prov["kind"] == "windymind":
        # Windy Mind's /v1/chat is text-only (no image input) — fall back to manual confirm.
        raise NotImplementedError("windymind has no vision surface")
    media = _media_type(filename)
    b64 = base64.b64encode(image_bytes).decode()
    prompt = ("This is a screenshot of a Wagyu animal's registry page. Extract the animal's "
              "details. Only include fields you can actually read; omit anything uncertain.")
    if prov["kind"] == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=prov["key"])
        msg = client.messages.create(
            model=prov["vision_model"], max_tokens=700,
            tools=[_PEDIGREE_TOOL], tool_choice={"type": "tool", "name": "record_pedigree"},
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
                {"type": "text", "text": prompt},
            ]}],
        )
        for block in msg.content:
            if getattr(block, "type", "") == "tool_use":
                return dict(block.input)
        return {"name": "", "_needs_manual_entry": True}
    # openai-compatible: ask for a JSON object with the pedigree fields
    r = httpx.post(
        f"{prov['base_url'].rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {prov['key']}"},
        json={"model": prov["vision_model"], "max_tokens": 700,
              "response_format": {"type": "json_object"},
              "messages": [{"role": "user", "content": [
                  {"type": "text", "text": prompt + f" Respond with a JSON object with these keys: {_PEDIGREE_FIELDS}."},
                  {"type": "image_url", "image_url": {"url": f"data:{media};base64,{b64}"}},
              ]}]},
        timeout=45,
    )
    r.raise_for_status()
    return json.loads(r.json()["choices"][0]["message"]["content"])
