"""Machine translation with a permanent DB cache — translate content once per
language, then serve from cache forever."""
import hashlib
import os
import re
import time

from ..models import Translation
from .ai import active_provider_label, chat

LANGS = {"es": "Spanish", "pt": "Portuguese (Brazilian)", "de": "German",
         "ja": "Japanese", "zh": "Simplified Chinese", "fr": "French", "en": "English"}

# Bump when the prompt/guards change so every cached row re-translates itself.
# The cache key also carries the active model, so swapping models (or a bad batch
# run under a degraded provider) can never freeze garbage in place forever —
# which is exactly what happened on 2026-07-24 ("Semen Straws" -> 精液管).
_PROMPT_VERSION = "v3"


# Translation splits into two tiers with very different economics.
#
#   DURABLE — the skeleton. Breed history, foundation bios, great sires, FAQ,
#     feeding, the Japan vocabulary. ~254k chars of prose that is written once and
#     read forever, and it is what makes the site read as the authority on the
#     breed. Translating ALL of it into all five languages costs about $32 on the
#     best available model — one time, permanently cached. There is no reason to
#     economise here.
#
#   BULK — the churn. Listing summaries and news headlines: thousands of rows,
#     replaced nightly, and the parts that actually matter (sire name, reg number,
#     price, grade) never go through the translator anyway because they are on the
#     do-not-translate list. This is where volume lives, so it stays cheap.
#
# Both go through Windy Mind — the app never names a provider, it asks the buffet
# for a model id. To upgrade, add the model to the Windy Mind roster and change
# the env var; the model is part of the cache key, so everything re-translates
# itself rather than serving the older model's output forever.
DURABLE = "durable"
BULK = "bulk"


def _model(tier: str = BULK) -> str | None:
    if tier == DURABLE:
        return (os.getenv("TRANSLATE_MODEL_DURABLE")
                or os.getenv("TRANSLATE_MODEL") or None)
    return os.getenv("TRANSLATE_MODEL_BULK") or os.getenv("TRANSLATE_MODEL") or None


def _cache_salt(tier: str = BULK) -> str:
    # The model is part of the key, so switching models re-translates rather than
    # serving the weaker model's cached output forever.
    return f"{_PROMPT_VERSION}|{_model(tier) or active_provider_label()}"


def _key(text: str, lang: str, tier: str = BULK) -> str:
    raw = f"{_cache_salt(tier)}|{text}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32] + ":" + lang


# --- Never machine-translate these ------------------------------------------
# Proper nouns and terms of art where a wrong guess is worse than English.
# Country names in particular must NEVER go through an LLM: it rendered
# "Czechia"->クロアチア (Croatia) and "Hungary"->チェコ (Czech).
_DNT_EXACT = {
    # grades / standards / indices — proper nouns in every language
    "A5", "A4", "BMS", "Beef Marbling Standard", "EPD", "EBV", "IMF", "CSS",
    "Choice", "Prime", "Select", "Choice Boxed Beef Cutout", "CME Feeder Cattle Index",
    "USDA", "JMGA", "IVF", "ET", "SCD", "AI",
    # product/unit terms the curated dictionary owns
    "straw", "straws",
}
# Anything that is purely a country/place name is resolved from a static table by
# the caller, never here. Guard against them reaching the LLM by accident.
_COUNTRY_WORDS = {
    "united states", "australia", "austria", "germany", "japan", "brazil", "canada",
    "united kingdom", "denmark", "netherlands", "spain", "france", "italy", "colombia",
    "mexico", "south africa", "norway", "thailand", "czechia", "hungary", "new zealand",
    "türkiye", "turkiye", "vietnam", "ireland", "china", "south korea", "argentina",
    "united nations", "belgium", "poland", "portugal", "sweden", "switzerland",
    "paraguay", "uruguay", "ecuador", "peru", "bolivia", "venezuela", "kenya",
    "india", "pakistan", "indonesia", "estonia", "finland", "bulgaria", "romania",
    "guatemala", "panama", "costa rica", "nicaragua",
}

# Simplified-Chinese-only characters that must never appear in Japanese output.
# llama/qwen both bleed zh into ja; this catches it deterministically.
_ZH_ONLY_IN_JA = re.compile(r"[们东车马鸟单产爱国样这个书长间问题现实业务开关变门风飞马龙鱼]|"
                            r"克隆|在库|胚胎|联合国|土耳其|犀牛|谱系|如何制作")


def _is_dnt(text: str) -> bool:
    t = text.strip()
    if t in _DNT_EXACT:
        return True
    if t.lower() in _COUNTRY_WORDS:
        return True
    return False


def _looks_bad(src: str, out: str, lang: str) -> bool:
    """Reject obviously-broken machine output rather than caching it forever."""
    s, o = src.strip(), (out or "").strip()
    if not o:
        return True
    # Truncation: a headline that comes back as a fragment ("Beckenham", "$126").
    # CJK is denser than Latin, so only flag severe loss.
    floor = 0.25 if lang in ("ja", "zh") else 0.45
    if len(s) >= 40 and len(o) < len(s) * floor:
        return True
    # Chinese bleeding into Japanese.
    if lang == "ja" and _ZH_ONLY_IN_JA.search(o):
        return True
    # Model refused / echoed instructions instead of translating.
    if o.lower().startswith(("i cannot", "i can't", "as an ai", "sure,", "here is the translation")):
        return True
    return False


_CHUNK = 1400  # chars per translation chunk — keeps output well under token limits


def _system(target: str, is_markdown: bool) -> str:
    fmt = "Preserve all Markdown formatting (headings, bold, lists, links) exactly. " if is_markdown else ""
    from .. import tank
    b = tank.brand()
    breed = b.get("breed") or "Wagyu"
    species = b.get("species") or "cattle"
    brand_name = b.get("name") or "WagyuTank"
    ja_rule = (" The target is Japanese: use Japanese script only — never Simplified Chinese "
               "characters or Chinese vocabulary (write クローン not 克隆, 在庫あり not 在库中, "
               "胚 not 胚胎)." if target == "Japanese" else "")
    return (f"You are a professional translator specializing in {species} genetics and the {breed} "
            f"breed. Translate the user's text into natural, fluent {target}. {fmt}"
            f"NEVER TRANSLATE: the brand name '{brand_name}'; company, ranch, farm and person names; "
            f"place and country names; animal names; registration numbers; breed terms ({breed}); "
            f"carcass grades and standards (A5, BMS, USDA Choice/Prime); and market index names "
            f"(e.g. CME Feeder Cattle Index). Leave all of those exactly as written in English.\n"
            f"Use the correct industry term for a unit of frozen semen — it is an insemination "
            f"straw (de: Portion; ja: ストロー; es: pajilla; pt: palheta; zh: 细管) — never the word "
            f"for a drinking straw or for hay, and never an anatomical term.\n"
            f"These animals are {species}. Use {species} terminology only: a 'sire' is a breeding "
            f"BULL (de: Bulle/Vatertier — never Deckhengst, which is a stallion), a 'dam' is a cow. "
            f"Never use horse, pig, sheep or other-species words.{ja_rule}\n"
            f"Return ONLY the translation, nothing else.")


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


def translate(db, text: str, lang: str, *, is_markdown: bool = False,
              tier: str = DURABLE) -> str:
    """Return `text` translated to `lang` (cached). English or unknown → unchanged.
    Long text is translated in chunks so the output never gets truncated.

    Defaults to the DURABLE tier: every caller of this function is long-lived prose
    the site is judged on — the help centre, the feeding guide, the great-sires
    encyclopedia, the breed history, the digest. High-volume churn goes through
    translate_batch() instead, which defaults to BULK."""
    lang = (lang or "en").lower()
    if lang == "en" or lang not in LANGS or not text.strip():
        return text
    if _is_dnt(text):
        return text
    key = _key(text, lang, tier)
    row = db.query(Translation).filter(Translation.cache_key == key).first()
    if row:
        return row.text
    system = _system(LANGS[lang], is_markdown)
    parts = []
    for chunk in _chunks(text):
        out = None
        for attempt in range(2):  # free-tier LLMs rate-limit under burst; back off once
            try:
                out = chat(system, chunk, max_tokens=2200, model=_model(tier))
            except Exception:
                out = None
            if out:
                break
            time.sleep(7)
        if not out or _looks_bad(chunk, out, lang):
            return text  # failed or obviously-broken → stay English, never cache it
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


def translate_batch(db, items: list[dict], lang: str, tier: str = BULK) -> dict:
    """Translate many short strings (e.g. headlines) in as few LLM calls as
    possible. BULK tier by default — this is the whole-page DOM sweep and the
    comment feed, thousands of short strings whose highest-visibility members are
    already covered hand-written in lib/i18n.tsx. items = [{id, text}]. Returns {id: translated_text} for the ones
    that actually translated. Cache-first per item; uncached ones go in one
    numbered-list prompt per ~20."""
    # Unlike translate(), the TARGET here may be English — comments arrive in any
    # language and are read in the viewer's, which is often English.
    lang = (lang or "en").lower()
    if lang not in LANGS:
        return {}
    result: dict = {}
    pending: list[dict] = []
    for it in items:
        text = (it.get("text") or "").strip()
        _id = it.get("id")
        if not text or _id is None or _is_dnt(text):
            continue
        row = db.query(Translation).filter(Translation.cache_key == _key(text, lang, tier)).first()
        if row:
            if row.text != text:
                result[_id] = row.text
        else:
            pending.append({"id": _id, "text": text})

    from .. import tank
    _b = tank.brand()
    system = (f"You are a professional translator for the {_b.get('breed') or 'Wagyu'} "
              f"{_b.get('species') or 'cattle'} industry. Translate each "
              f"numbered headline into natural {LANGS[lang]}. Keep breed terms and proper nouns "
              f"(breed names, sire names, registration numbers, company/ranch names, place and "
              f"country names, carcass grades like A5/BMS/Choice) unchanged. Translate the FULL "
              f"headline — never return a fragment or a single word."
              + (" Use Japanese script only, never Simplified Chinese characters."
                 if lang == "ja" else "")
              + " Return ONLY the same numbered list, one translation per line, no extra text.")
    for i in range(0, len(pending), 20):
        batch = pending[i:i + 20]
        prompt = "\n".join(f"{n + 1}. {b['text']}" for n, b in enumerate(batch))
        out = None
        for attempt in range(2):
            try:
                out = chat(system, prompt, max_tokens=1600, model=_model(tier))
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
            # Guard the batch path too: a mis-parsed numbered list used to cache
            # fragments as "translations" (a headline coming back as "$126").
            if tr and tr != b["text"] and not _looks_bad(b["text"], tr, lang):
                result[b["id"]] = tr
                _cache_put(db, _key(b["text"], lang, tier), lang, tr)
    return result
