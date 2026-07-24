"""Work out the actual COUNTRY of a news article from the only signals Google
News RSS leaves us: the publisher name and the content language. (The link is a
news.google.com redirect, so the domain is not available.)

The old feed stored only a coarse macro-region (US = all of North America, AS =
all of Asia), which stamped Canadian, Filipino and even Japanese stories with a
US flag. This resolves a real ISO-3166 country, and re-derives the macro-region
from it so the region filter stays correct too.

Priority: script (kana/hangul) → ccTLD in the name → known publisher → language
→ feed-country hint → macro-region default. Returns None when nothing is
confident, and the UI falls back to the region label rather than a wrong flag.
"""
import re

# --- country -> macro-region (matches the news feed's US/SA/EU/JP/AS/ME/AF/AU buckets) ---
_REGION = {
    "JP": "JP",
    "US": "US", "CA": "US", "MX": "US",
    "BR": "SA", "AR": "SA", "CL": "SA", "CO": "SA", "UY": "SA", "PE": "SA", "PY": "SA", "BO": "SA", "EC": "SA",
    "AU": "AU", "NZ": "AU",
    "GB": "EU", "IE": "EU", "DE": "EU", "FR": "EU", "IT": "EU", "ES": "EU", "NL": "EU", "GR": "EU",
    "AT": "EU", "CH": "EU", "BE": "EU", "PT": "EU", "SE": "EU", "NO": "EU", "DK": "EU", "PL": "EU",
    "CZ": "EU", "HU": "EU", "FI": "EU", "RO": "EU",
    "CN": "AS", "TW": "AS", "KR": "AS", "HK": "AS", "SG": "AS", "MY": "AS", "TH": "AS", "VN": "AS",
    "ID": "AS", "IN": "AS", "PH": "AS",
    "AE": "ME", "SA": "ME", "QA": "ME", "IL": "ME", "TR": "ME",
    "ZA": "AF", "NG": "AF", "KE": "AF",
    "BZ": "US",
}

def region_for_country(cc):
    return _REGION.get(cc) if cc else None

# --- script blocks ---
_HANGUL = re.compile(r"[가-힣ㄱ-ㅎ]")
_KANA = re.compile(r"[぀-ゟ゠-ヿ]")          # hiragana + katakana (Japanese-only)
_HAN = re.compile(r"[㐀-鿿]")               # CJK ideographs (shared)

# --- ccTLD suffixes that appear inside domain-style source names ---
_TLD = [
    (".co.jp", "JP"), (".co.nz", "NZ"), (".com.au", "AU"), (".co.id", "ID"), (".co.uk", "GB"),
    (".co.za", "ZA"), (".com.ph", "PH"), (".com.br", "BR"), (".com.mx", "MX"), (".com.tw", "TW"),
    (".gov.ph", "PH"), (".com.sg", "SG"), (".com.my", "MY"), (".jp", "JP"), (".au", "AU"),
    (".nz", "NZ"), (".ph", "PH"), (".ie", "IE"), (".uk", "GB"), (".de", "DE"), (".fr", "FR"),
    (".it", "IT"), (".es", "ES"), (".nl", "NL"), (".gr", "GR"), (".br", "BR"), (".mx", "MX"),
    (".ca", "CA"), (".tw", "TW"), (".kr", "KR"), (".sg", "SG"), (".my", "MY"), (".in", "IN"),
    (".id", "ID"), (".vn", "VN"), (".th", "TH"), (".za", "ZA"),
]

# --- known publishers (substring match, longest key first) ---
_PUB = {
    # Australia
    "beef central": "AU", "the weekly times": "AU", "stock journal": "AU", "queensland country life": "AU",
    "north queensland register": "AU", "australian broadcasting": "AU", "australian traveller": "AU",
    "farm online": "AU", "countryman": "AU", "the land": "AU",
    # New Zealand
    "farmers weekly": "NZ",
    # Canada
    "streets of toronto": "CA", "toronto": "CA", "globe and mail": "CA", "toronto star": "CA",
    "canadian cattlemen": "CA", "global news": "CA", "news canada": "CA", "blogto": "CA", "daily hive": "CA",
    # Philippines
    "philstar": "PH", "abs-cbn": "PH", "gma network": "PH", "manila times": "PH", "manila bulletin": "PH",
    "manila standard": "PH", "the manila": "PH", "inquirer": "PH", "sunstar": "PH", "businessworld": "PH",
    "interaksyon": "PH", "philippine primer": "PH", "malaya business": "PH", "spot ph": "PH",
    "mindanews": "PH", "daily tribune": "PH", "insiderph": "PH", "esquiremag.ph": "PH",
    # Taiwan / HK / Singapore / Malaysia
    "focus taiwan": "TW", "taipei times": "TW", "taiwan news": "TW",
    "south china morning post": "HK", "tatler asia": "HK",
    "straits times": "SG", "business times": "SG", "cna luxury": "SG", "channel news asia": "SG",
    "hungrygowhere": "SG", "sethlui": "SG", "honeycombers": "SG", "thinkchina": "SG", "8days": "SG",
    "malay mail": "MY", "borneo post": "MY", "the star": "MY",
    # India / Israel / Indonesia / Vietnam
    "times of india": "IN", "onmanorama": "IN", "the hindu": "IN", "economic times": "IN",
    "times of israel": "IL", "jakarta": "ID", "ipb university": "ID", "vnexpress": "VN",
    # UK / Ireland / Greece
    "bbc": "GB", "the guardian": "GB", "telegraph": "GB", "daily mail": "GB", "evening standard": "GB",
    "time out worldwide": "GB", "wallpaper": "GB", "agriland uk": "GB", "the irish sun": "IE",
    "irish independent": "IE", "irish times": "IE", "irish farmers journal": "IE", "businessplus": "IE",
    "agriland": "IE", "kathimerini": "GR",
    # Middle East / Latin America / Belize
    "gault&millau uae": "AE", "the times of israel": "IL", "contexto ganadero": "CO", "love fm belize": "BZ",
    # United States (frequent)
    "new york times": "US", "wall street journal": "US", "bloomberg": "US", "forbes": "US",
    "eater": "US", "food & wine": "US", "the kitchn": "US", "modern luxury": "US", "robb report": "US",
    "d magazine": "US", "culturemap": "US", "nbc new york": "US", "wtop": "US", "wjla": "US", "wfmz": "US",
    "palm beaches": "US", "bethesda": "US", "radio milwaukee": "US", "meatingplace": "US",
    "national provisioner": "US", "progressive farmer": "US", "ag proud": "US", "boca raton": "US",
    "the pride la": "US", "moco show": "US", "magnolia tribune": "US", "resident magazine": "US",
    "stars and stripes": "US", "national law review": "US",
}
_PUB_KEYS = sorted(_PUB, key=len, reverse=True)

# --- language -> country (for non-English content when nothing else resolves) ---
_LANG = {"ja": "JP", "ko": "KR", "de": "DE", "fr": "FR", "it": "IT", "nl": "NL",
         "pt": "BR", "th": "TH", "vi": "VN", "id": "ID", "zh": "CN"}


def classify_country(source_name, language=None, region=None, gl=None):
    name = (source_name or "").strip()
    low = name.lower()
    lang = (language or "").lower()

    # 1) script — beats a mislabeled language field (some Korean/Japanese rows are tagged zh)
    if _HANGUL.search(name):
        return "KR"
    if _KANA.search(name):
        return "JP"
    if _HAN.search(name):
        if lang == "zh":
            return "CN"
        if lang == "ko":
            return "KR"
        if "新闻" in name:          # simplified-Chinese "news" -> mainland source
            return "CN"
        return "JP"                 # a kanji-named publisher in a Wagyu feed is Japanese
                                    # (朝日新聞, 読売新聞 …) even when the feed lang is en

    # 2) ccTLD embedded in a domain-style source name
    for suf, cc in _TLD:
        if low.endswith(suf) or (suf + "/") in low or (suf + " ") in low:
            return cc

    # 3) known publisher
    for k in _PUB_KEYS:
        if k in low:
            return _PUB[k]

    # 4) a real feed-country hint (only stored for live crawls going forward)
    if gl:
        return gl.upper()

    # 5) language default (English is too ambiguous to map)
    if lang == "es":
        if region == "US":   # the only region=US Spanish feed targets Mexico
            return "MX"
        if region == "EU":
            return "ES"
        return None          # South-American Spanish: can't pin one country
    if lang in _LANG:
        return _LANG[lang]

    # 6) macro-region default for English / unresolved
    return {"US": "US", "AU": "AU", "JP": "JP", "ME": "AE", "AF": "ZA"}.get(region)
