"""Official-website dictionary verification (free, no key).

Checks whether a word exists in Wiktionary (an authoritative online dictionary).
Used to flag Hindi words that are absent from the dictionary — a cross-check
against an official source. Conservative and capped to stay fast and low-noise.
"""
from __future__ import annotations
import json
import re
import urllib.parse
import urllib.request
from typing import List, Dict

UA = {"User-Agent": "Mozilla/5.0 Shuddhi/1.0 (proofreading tool)"}
_DEV = re.compile(r"[ऀ-ॿ]+")
_cache: Dict[tuple, object] = {}

WIKTIONARY = {"hi": "hi.wiktionary.org", "en": "en.wiktionary.org", "gu": "gu.wiktionary.org"}


def dict_url(word: str, lang: str) -> str:
    host = WIKTIONARY.get(lang, "en.wiktionary.org")
    return "https://%s/wiki/%s" % (host, urllib.parse.quote(word))


def exists(word: str, lang: str):
    """True / False / None(unknown) — whether the word has a Wiktionary entry."""
    host = WIKTIONARY.get(lang)
    if not host:
        return None
    key = (host, word)
    if key in _cache:
        return _cache[key]
    url = "https://%s/w/api.php?action=query&titles=%s&format=json" % (host, urllib.parse.quote(word))
    try:
        r = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=8))
        pages = r["query"]["pages"]
        val = not any("missing" in p for p in pages.values())
    except Exception:
        val = None
    _cache[key] = val
    return val


def verify_hindi(hi_segments: List[Dict], cap: int = 40, log=lambda *a: None) -> List[dict]:
    """Flag Hindi words absent from हिन्दी विक्षनरी. Experimental: Wiktionary
    coverage is incomplete, so these are Low-priority 'please verify' hints."""
    out, seen, n = [], set(), 0
    for seg in hi_segments:
        for w in _DEV.findall(seg["text"]):
            if len(w) < 4 or w in seen:
                continue
            seen.add(w)
            if n >= cap:
                log("Dictionary verification: checked first %d unique words." % cap)
                return out
            n += 1
            if exists(w, "hi") is False:
                out.append({
                    "loc": seg["loc"], "language": "Hindi", "type": "spelling", "priority": "Low",
                    "incorrect": w, "suggestion": "(वर्तनी जाँचें)",
                    "explanation": "शब्दकोश (हिन्दी विक्षनरी) में प्रविष्टि नहीं मिली — वर्तनी जाँचें। "
                                   "(कोशकवरेज सीमित हो सकती है।)",
                    "source": "webcheck",
                })
    return out
