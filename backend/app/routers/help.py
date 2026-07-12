"""Help & FAQ — a curated, translatable Q&A plus a grounded help assistant.

The assistant answers free-text questions through the SAME admin-selectable AI
provider as the rest of the site (Settings → AI & Compute): WindyMind today, a
local LLM later, just by flipping the selector — no code change. It's grounded
in the FAQ + core facts and told to stay on-topic and defer to a human on
transactional specifics, so it's helpful without inventing prices or promises."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from ..db import get_db
from ..services import ai, ratelimit, settings_store
from ..services import translate as translate_service

router = APIRouter(prefix="/api/help", tags=["help"])

from .. import tank
def _data(): return tank.seed_path("faq.json")
_cache: dict = {}


def _load() -> dict:
    if not _cache:
        try:
            _cache.update(json.loads(_data().read_text()))
        except Exception:
            _cache.update({"intro": "", "categories": []})
    return _cache


def _kb() -> str:
    """Flatten the FAQ into a compact knowledge base for the assistant prompt."""
    d = _load()
    lines = [d.get("intro", "")]
    for cat in d.get("categories", []):
        lines.append(f"\n## {cat['name']}")
        for it in cat.get("items", []):
            lines.append(f"Q: {it['q']}\nA: {it['a']}")
    return "\n".join(lines)


@router.get("")
def faq(lang: str = "en", db=Depends(get_db)):
    """The curated FAQ, translated on demand into the viewer's language."""
    d = _load()
    if not lang or lang == "en":
        return d
    out = {"intro": translate_service.translate(db, d.get("intro", ""), lang), "categories": []}
    for cat in d.get("categories", []):
        out["categories"].append({
            "name": translate_service.translate(db, cat["name"], lang),
            "items": [{"q": translate_service.translate(db, it["q"], lang),
                       "a": translate_service.translate(db, it["a"], lang)}
                      for it in cat.get("items", [])],
        })
    return out


class AskBody(BaseModel):
    question: str
    lang: str | None = "en"


def _system() -> str:
    """Build the help-assistant system prompt from this tank's config, so a clone's
    bot speaks about its own breed/brand. Breed nuance (e.g. Wagyu's Akaushi rule)
    comes from vocab.help_nuance — content, per tank."""
    from .. import tank
    b = tank.brand()
    name = b.get("name", "this marketplace")
    breed = b.get("breed", "the breed")
    nuance = tank.vocab().get("help_nuance", "")
    nuance_line = f"- {nuance}\n" if nuance else ""
    return (
        f"You are the {name} help assistant. {name} is a global marketplace and "
        f"knowledge hub for {breed} genetics (semen, embryos, cloning rights) plus a "
        f"free web-wide index of genetics listings (the Roundup), translated news, a "
        f"genetics price index, foundation-bloodline records, and breed education.\n\n"
        f"Answer using ONLY the knowledge base below and general, well-established "
        f"facts about {breed} and genetics. Rules:\n"
        "- Be concise, friendly, and practical (2-4 sentences unless more is truly needed).\n"
        "- Never invent prices, availability, shipping guarantees, or legal/import "
        "advice. For those, tell the user to check the specific listing or contact the "
        "seller, and to confirm import rules with their own animal-health authority.\n"
        f"{nuance_line}"
        f"- If a question is outside {breed} or {name}, gently redirect.\n"
        "- If unsure, say so and point to the relevant section (Roundup, Foundation, "
        "News, or contacting a seller)."
    )


@router.post("/ask")
def ask(payload: AskBody, request: Request, db=Depends(get_db)):
    if not settings_store.get("help_bot_enabled", True):
        raise HTTPException(503, "The help assistant is currently offline. Please see the FAQ above.")
    q = (payload.question or "").strip()
    if len(q) < 3:
        raise HTTPException(400, "Please ask a question.")
    if len(q) > 600:
        q = q[:600]
    ip = (request.headers.get("cf-connecting-ip")
          or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "?"))
    # Protect the free WindyMind lane: 15 questions / IP / hour.
    if not ratelimit.allow(f"help_ask:ip:{ip}", 15, 3600):
        raise HTTPException(429, "You've asked a lot of questions in a short time — please try again shortly.")

    lang = (payload.lang or "en").strip() or "en"
    user = f"Knowledge base:\n{_kb()}\n\n---\nUser question: {q}"
    if lang != "en":
        user += f"\n\nRespond in this language code: {lang}."
    try:
        answer = ai.chat(_system(), user, max_tokens=400)
    except Exception:
        answer = None
    if not answer:
        return {"answer": "I'm having trouble reaching the assistant right now — please check the "
                          "FAQ above, or contact us at office@wagyutank.com.",
                "provider": ai.active_provider_label(), "fallback": True}
    return {"answer": answer.strip(), "provider": ai.active_provider_label()}
