"""Machine translation with a permanent DB cache — translate content once per
language, then serve from cache forever."""
import hashlib
import os
import re
import time

from ..models import Translation
from .ai import active_provider_label, chat

LANGS = {"es": "Spanish", "pt": "Portuguese (Brazilian)", "de": "German",
         "ja": "Japanese", "zh": "Simplified Chinese", "fr": "French", "en": "English",
         # 2026-07-28 expansion to 14. Chosen on where the breed actually trades and
         # where the English barrier is real — not raw listing counts. Dutch and
         # Danish were deliberately SKIPPED despite being the two largest uncovered
         # markets by operation count: those breeders read English comfortably, so a
         # translation buys nothing. Italian/Turkish/Indonesian punch far above their
         # counts for the opposite reason. Korean has no listings yet BECAUSE the
         # site is unreadable there — Hanwoo is a national marbled-beef genetics
         # programme that mirrors Japan's.
         "it": "Italian", "ko": "Korean", "tr": "Turkish", "cs": "Czech",
         "pl": "Polish", "hu": "Hungarian", "id": "Indonesian"}

# Bump when the prompt/guards change so every cached row re-translates itself.
# The cache key also carries the active model, so swapping models (or a bad batch
# run under a degraded provider) can never freeze garbage in place forever —
# which is exactly what happened on 2026-07-24 ("Semen Straws" -> 精液管).
_PROMPT_VERSION = "v4"


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
    # Read through Settings, not os.getenv: this app loads .env via
    # pydantic-settings, which populates the Settings object and NOT os.environ,
    # so a bare `python -m app.jobs...` would otherwise never see these.
    from ..config import settings

    general = settings.translate_model or os.getenv("TRANSLATE_MODEL") or ""
    if tier == DURABLE:
        specific = settings.translate_model_durable or os.getenv("TRANSLATE_MODEL_DURABLE") or ""
    else:
        specific = settings.translate_model_bulk or os.getenv("TRANSLATE_MODEL_BULK") or ""
    return (specific or general) or None


def _provider_for(tier: str) -> str | None:
    """Which provider serves this tier.

    A configured translate model lives on the Windy Mind buffet, so pin the lane
    there. Otherwise inherit whatever the tank is set to. Without this, a tank
    whose AI_PROVIDER points at the local 5090 (as every tank.env does, for crawl
    extraction) sent translation there too and 404'd on claude-opus-5.
    """
    return "windymind" if _model(tier) else None


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
# NOTE 国 IS NOT IN THIS SET, deliberately. Japan adopted the same simplified form
# post-war (shinjitai), so 国 is ordinary Japanese — 全国, 国際, 韓国, 中国, 外国,
# 国内. Including it silently rejected 127 perfectly good Japanese translations,
# roughly 17% of the corpus, and on a site about INTERNATIONAL cattle genetics
# those are exactly the words that recur. Every character below is
# Simplified-Chinese-only; the Japanese equivalent is noted.
_ZH_ONLY_IN_JA = re.compile(
    r"[们"          # (no JA equivalent)
    r"东车马鸟单产爱样这个书长间问题现实业务开关变门风飞龙鱼"
    #  東車馬鳥単産愛様  個書長間問題現実業務開関変門風飛龍魚
    r"]|"
    r"克隆|在库|胚胎|联合国|土耳其|犀牛|谱系|如何制作")


def _is_dnt(text: str) -> bool:
    t = text.strip()
    if t in _DNT_EXACT:
        return True
    if t.lower() in _COUNTRY_WORDS:
        return True
    return False


class RateLimited(Exception):
    """The upstream gateway is refusing on quota, not failing on content.

    Distinguished from an ordinary failure because the right response is
    opposite: a content failure should fall back to English and move on, but a
    quota refusal means every subsequent call will fail too. A batch job that
    cannot tell the difference burns hours logging progress it is not making —
    which is exactly what happened on 2026-07-28, when a warm run sat on a
    frozen cache for twenty minutes looking healthy.
    """


def _is_rate_limited(exc: Exception) -> bool:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "too many requests" in text or "daily limit" in text


def _looks_bad(src: str, out: str, lang: str) -> bool:
    """Reject obviously-broken machine output rather than caching it forever."""
    s, o = src.strip(), (out or "").strip()
    if not o:
        return True
    # Truncation: a headline that comes back as a fragment ("Beckenham", "$126").
    # CJK is denser than Latin, so only flag severe loss there.
    # KOREAN BELONGS IN THIS SET. Leaving it out silently discarded good
    # translations: "Day in the Life of a Japanese Wagyu Beef Farmer" (46 chars)
    # came back as "와규 목장 농부의 일일 생활" (18) — correct Korean, but under the
    # 0.45 Latin floor, so it was rejected and the title stayed English. Hangul is
    # as information-dense as kana/hanzi.
    floor = 0.25 if lang in ("ja", "zh", "ko") else 0.45
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
    if target == "Korean":
        # Opus reached for Han characters on a Korean title (日本 instead of 일본).
        # Modern Korean is Hangul; Hanja is archaic outside legal/academic text.
        ja_rule = (" The target is Korean: write in Hangul. Do not use Han/Chinese "
                   "characters for ordinary words — 일본, not 日本.")
    return (f"You are a professional translator specializing in {species} genetics and the {breed} "
            f"breed. Translate the user's text into natural, fluent {target}. {fmt}"
            f"NEVER TRANSLATE: the brand name '{brand_name}'; company, ranch, farm and person names; "
            f"animal names; registration numbers; breed terms ({breed}); "
            f"carcass grades and standards (A5, BMS, USDA Choice/Prime); and market index names "
            f"(e.g. CME Feeder Cattle Index). Leave all of those exactly as written in English.\n"
            f"Country and place names ARE translated when they appear inside a sentence — write "
            f"them the way a native speaker would (Japanese: 日本, not 'Japan'). Standalone country "
            f"labels never reach you; they are resolved from a fixed table.\n"
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
              tier: str = DURABLE, raise_on_quota: bool = False) -> str:
    """Return `text` translated to `lang` (cached). English or unknown → unchanged.
    Long text is translated in chunks so the output never gets truncated.

    `raise_on_quota` is for BATCH callers only. A page render must always degrade
    quietly to English, but a warm job needs to know the difference between "this
    string failed" and "the gateway is refusing everything" — otherwise it spends
    hours logging progress against a frozen cache, which is exactly what happened
    on 2026-07-28. Default False keeps every interactive path unchanged.

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
                out = chat(system, chunk, max_tokens=2200, model=_model(tier), provider=_provider_for(tier))
            except Exception as e:
                # Quota refusal is not a content failure. Surface it so a batch
                # caller can stop; interactive callers still catch it and fall
                # back to English, exactly as before.
                if _is_rate_limited(e) and raise_on_quota:
                    raise RateLimited(str(e)[:200]) from e
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
                out = chat(system, prompt, max_tokens=1600, model=_model(tier), provider=_provider_for(tier))
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
