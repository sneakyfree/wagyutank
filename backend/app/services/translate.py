"""Machine translation with a permanent DB cache — translate content once per
language, then serve from cache forever."""
import hashlib

from ..models import Translation
from .ai import chat

LANGS = {"es": "Spanish", "pt": "Portuguese", "fr": "French", "ja": "Japanese", "en": "English"}


def _key(text: str, lang: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32] + ":" + lang


def translate(db, text: str, lang: str, *, is_markdown: bool = False) -> str:
    """Return `text` translated to `lang` (cached). English or unknown → unchanged."""
    lang = (lang or "en").lower()
    if lang == "en" or lang not in LANGS or not text.strip():
        return text
    key = _key(text, lang)
    row = db.query(Translation).filter(Translation.cache_key == key).first()
    if row:
        return row.text
    target = LANGS[lang]
    fmt = ("Preserve all Markdown formatting (headings, bold, lists, links) exactly. "
           if is_markdown else "")
    system = (f"You are a professional translator specializing in cattle genetics and the Wagyu "
              f"breed. Translate the user's text into natural, fluent {target}. {fmt}"
              f"Keep proper nouns, cattle names, registration numbers, and breed terms "
              f"(Wagyu, Akaushi, Tajima, etc.) unchanged. Return ONLY the translation.")
    try:
        out = chat(system, text, max_tokens=min(4000, len(text) + 800))
    except Exception:
        out = None
    if not out:
        return text  # graceful fallback to English; don't cache failures
    db.add(Translation(cache_key=key, lang=lang, text=out))
    db.commit()
    return out
