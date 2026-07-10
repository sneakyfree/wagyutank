"""Machine translation with a permanent DB cache — translate content once per
language, then serve from cache forever."""
import hashlib
import time

from ..models import Translation
from .ai import chat

LANGS = {"es": "Spanish", "pt": "Portuguese (Brazilian)", "de": "German",
         "ja": "Japanese", "zh": "Simplified Chinese", "fr": "French", "en": "English"}


def _key(text: str, lang: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32] + ":" + lang


_CHUNK = 1400  # chars per translation chunk — keeps output well under token limits


def _system(target: str, is_markdown: bool) -> str:
    fmt = "Preserve all Markdown formatting (headings, bold, lists, links) exactly. " if is_markdown else ""
    return (f"You are a professional translator specializing in cattle genetics and the Wagyu "
            f"breed. Translate the user's text into natural, fluent {target}. {fmt}"
            f"Keep proper nouns, cattle names, registration numbers, and breed terms "
            f"(Wagyu, Akaushi, Tajima, etc.) unchanged. Return ONLY the translation, nothing else.")


def _chunks(text: str) -> list[str]:
    """Split on blank lines into chunks under _CHUNK chars, so nothing gets truncated."""
    out, buf = [], ""
    for para in text.split("\n\n"):
        if len(buf) + len(para) + 2 > _CHUNK and buf:
            out.append(buf)
            buf = ""
        buf = f"{buf}\n\n{para}" if buf else para
    if buf:
        out.append(buf)
    return out


def translate(db, text: str, lang: str, *, is_markdown: bool = False) -> str:
    """Return `text` translated to `lang` (cached). English or unknown → unchanged.
    Long text is translated in chunks so the output never gets truncated."""
    lang = (lang or "en").lower()
    if lang == "en" or lang not in LANGS or not text.strip():
        return text
    key = _key(text, lang)
    row = db.query(Translation).filter(Translation.cache_key == key).first()
    if row:
        return row.text
    system = _system(LANGS[lang], is_markdown)
    parts = []
    for chunk in _chunks(text):
        out = None
        for attempt in range(2):  # free-tier LLMs rate-limit under burst; back off once
            try:
                out = chat(system, chunk, max_tokens=2200)
            except Exception:
                out = None
            if out:
                break
            time.sleep(7)
        if not out:
            return text  # any chunk fails → fall back to English, don't cache a partial
        parts.append(out.strip())
        time.sleep(0.7)
    result = "\n\n".join(parts)
    _cache_put(db, key, lang, result)
    return result


def _cache_put(db, key: str, lang: str, text: str) -> None:
    """Insert a translation, tolerating a concurrent request that cached the same
    key first (the unique constraint would otherwise 500 the whole response)."""
    from sqlalchemy.exc import IntegrityError
    db.add(Translation(cache_key=key, lang=lang, text=text))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()  # another request won the race — its row is fine


def translate_one(db, text: str, lang: str) -> tuple[str, bool]:
    """Like translate() but reports whether translation actually happened."""
    lang = (lang or "en").lower()
    if lang == "en" or lang not in LANGS or not text.strip():
        return text, False
    out = translate(db, text, lang)
    return out, (out != text)


def translate_batch(db, items: list[dict], lang: str) -> dict:
    """Translate many short strings (e.g. headlines) in as few LLM calls as
    possible. items = [{id, text}]. Returns {id: translated_text} for the ones
    that actually translated. Cache-first per item; uncached ones go in one
    numbered-list prompt per ~20."""
    lang = (lang or "en").lower()
    if lang == "en" or lang not in LANGS:
        return {}
    result: dict = {}
    pending: list[dict] = []
    for it in items:
        text = (it.get("text") or "").strip()
        _id = it.get("id")
        if not text or _id is None:
            continue
        row = db.query(Translation).filter(Translation.cache_key == _key(text, lang)).first()
        if row:
            if row.text != text:
                result[_id] = row.text
        else:
            pending.append({"id": _id, "text": text})

    system = (f"You are a professional translator for the Wagyu cattle industry. Translate each "
              f"numbered headline into natural {LANGS[lang]}. Keep breed terms and proper nouns "
              f"(Wagyu, Akaushi, Tajima, Kobe, sire names, registration numbers) unchanged. "
              f"Return ONLY the same numbered list, one translation per line, no extra text.")
    for i in range(0, len(pending), 20):
        batch = pending[i:i + 20]
        prompt = "\n".join(f"{n + 1}. {b['text']}" for n, b in enumerate(batch))
        out = None
        for attempt in range(2):
            try:
                out = chat(system, prompt, max_tokens=1600)
            except Exception:
                out = None
            if out:
                break
            time.sleep(5)
        if not out:
            continue
        # parse "N. translation" lines back to their ids
        lines = {}
        for ln in out.splitlines():
            m = ln.strip()
            if not m:
                continue
            dot = m.find(".")
            if dot > 0 and m[:dot].isdigit():
                lines[int(m[:dot])] = m[dot + 1:].strip()
        for n, b in enumerate(batch):
            tr = lines.get(n + 1)
            if tr and tr != b["text"]:
                result[b["id"]] = tr
                _cache_put(db, _key(b["text"], lang), lang, tr)
    return result
