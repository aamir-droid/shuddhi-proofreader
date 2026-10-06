"""The proofreading engine: language detection, curated rules, a *conservative*
dictionary spellcheck (that never flags names/places/acronyms), reference-link
enrichment, and an optional AI (Claude) deep pass. Every layer degrades
gracefully so the app still runs when a dependency or API key is missing.
"""
from __future__ import annotations
import json
import os
import re
import urllib.parse
from typing import List, Dict, Any

_HERE = os.path.dirname(__file__)
_RULES_PATH = os.path.join(_HERE, "rules.json")
_ALLOW_PATH = os.path.join(_HERE, "allowlist.json")

PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}
LANG_NAME = {"hi": "Hindi", "gu": "Gujarati", "en": "English"}
LANG_CODE = {"Hindi": "hi", "Gujarati": "gu", "English": "en"}

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_GUJARATI = re.compile(r"[઀-૿]")
_WORD_RE = re.compile(r"[A-Za-zऀ-ॿ઀-૿]+")
# Stray Latin combining marks / accents that appear when a PPT→PDF export has a
# broken font encoding (e.g. बुद्ͬ धमता, Ǔनवेश). Used to warn the user.
_COMBINING = re.compile(r"[̀-ͯǀ-ɏʰ-˿]")


def detect_lang(text: str) -> str:
    guj = len(_GUJARATI.findall(text))
    dev = len(_DEVANAGARI.findall(text))
    if guj and guj >= dev:
        return "gu"
    if dev:
        return "hi"
    return "en"


def looks_garbled(text: str) -> bool:
    """True if the text layer looks corrupted (broken font encoding)."""
    dev = len(_DEVANAGARI.findall(text))
    bad = len(_COMBINING.findall(text))
    return dev > 0 and bad >= max(3, dev * 0.04)


# --------------------------------------------------------------------------- #
#  Reference links (feedback item: link शब्दकोश / UK dictionary)              #
# --------------------------------------------------------------------------- #
def ref_link(word: str, lang_code: str) -> str:
    w = urllib.parse.quote((word or "").strip())
    if lang_code == "hi":
        return "https://www.shabdkosh.com/search-dictionary?lc=hi&sl=hi&tl=en&e=" + w
    if lang_code == "gu":
        return "https://www.shabdkosh.com/search-dictionary?lc=gu&sl=gu&tl=en&e=" + w
    return "https://dictionary.cambridge.org/dictionary/english/" + urllib.parse.quote(
        (word or "").strip().lower())


# --------------------------------------------------------------------------- #
#  Layer 1 — curated rules                                                     #
# --------------------------------------------------------------------------- #
def _load_rules() -> Dict[str, List[dict]]:
    with open(_RULES_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _load_allow() -> set:
    with open(_ALLOW_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    words = set()
    for k, v in data.items():
        if k.startswith("_"):
            continue
        for w in v:
            words.add(w.lower())
    return words


_RULES = _load_rules()
_ALLOW = _load_allow()


def rule_findings(seg: Dict[str, str], lang: str, category: str) -> List[dict]:
    text = seg["text"]
    out = []
    for rule in _RULES.get(lang, []):
        cats = rule.get("categories", [])
        if not cats:
            continue
        if "all" not in cats and category.lower() not in [c.lower() for c in cats]:
            continue
        word = rule["word"]
        if rule.get("match", "word") == "phrase":
            present = word in text
        else:
            present = re.search(r"(?<![A-Za-zऀ-ॿ઀-૿])"
                                + re.escape(word)
                                + r"(?![A-Za-zऀ-ॿ઀-૿])", text) is not None
        if present:
            out.append({
                "loc": seg["loc"], "language": LANG_NAME.get(lang, lang),
                "type": rule.get("type", "spelling"),
                "priority": rule.get("priority", "Medium"),
                "incorrect": word, "suggestion": rule["suggestion"],
                "explanation": rule.get("note", ""), "source": "rule",
            })
    return out


# --------------------------------------------------------------------------- #
#  Layer 2 — conservative English dictionary spellcheck                        #
# --------------------------------------------------------------------------- #
_EN_SPELL = None


def _en_speller():
    global _EN_SPELL
    if _EN_SPELL is None:
        try:
            from spellchecker import SpellChecker
            sp = SpellChecker(language="en")
            sp.word_frequency.load_words(_ALLOW)   # never flag allowlisted words
            _EN_SPELL = sp
        except Exception:
            _EN_SPELL = False
    return _EN_SPELL


def spell_findings(seg: Dict[str, str], lang: str, max_per_seg: int = 10) -> List[dict]:
    """Flag only clearly-misspelled *lowercase* English words. Skips proper nouns
    (Capitalised), acronyms (ALL CAPS), short tokens, numbers, and allowlisted
    Indian/UK terms — so names, places and brands are never flagged."""
    if lang != "en":
        return []
    sp = _en_speller()
    if not sp:
        return []
    out, seen = [], set()
    for tok in _WORD_RE.findall(seg["text"]):
        if not tok.isalpha() or len(tok) < 4:
            continue
        if tok[0].isupper() or tok.isupper():      # proper noun or acronym
            continue
        low = tok.lower()
        if low in seen or low in _ALLOW:
            continue
        if not sp.unknown([low]):                   # known word → fine
            continue
        seen.add(low)
        corr = sp.correction(low)
        if corr and corr != low:
            out.append({
                "loc": seg["loc"], "language": "English", "type": "spelling",
                "priority": "Low", "incorrect": tok, "suggestion": corr,
                "explanation": "Not in the English dictionary; nearest match shown. "
                               "(Verify — may be a name or technical term.)",
                "source": "spell",
            })
        if len(out) >= max_per_seg:
            break
    return out


# --------------------------------------------------------------------------- #
#  Layer 3 — AI deep pass (Claude)                                             #
# --------------------------------------------------------------------------- #
DEFAULT_MODEL = os.environ.get("SHUDDHI_MODEL", "claude-opus-5-5")
VARIANT_LABEL = {"indian": "Indian English", "uk": "British (UK) English",
                 "us": "American (US) English"}


def anthropic_sdk() -> bool:
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


def ai_available() -> bool:
    """True when a server-side key is configured (the SDK is always a dependency)."""
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return False
    return anthropic_sdk()


_SYSTEM = (
    "You are an expert proofreader and copy-editor for Hindi, Gujarati and English, "
    "specialising in Indian government, education and public-communication material. "
    "You correct spelling (वर्तनी), grammar (व्याकरण), sentence formation, punctuation, "
    "and context-appropriate word choice.\n"
    "For Hindi/Gujarati: follow standard orthography (मानक वर्तनी) per NCERT / Central "
    "Hindi Directorate — short/long maatras (इ-ई, उ-ऊ), anusvara vs chandrabindu, "
    "visarga vs colon, nukta, and correct tatsam/tadbhav spellings.\n"
    "CRITICAL — never flag as errors: proper nouns (names of people, places, states, "
    "districts, departments, schemes, apps or brands such as Bihar, Patna, Beltron, "
    "Sahyog, Janvishwas, IPGRS, Panchayat, Aadhaar, WhatsApp), acronyms, deliberate "
    "English/technical terms, or correctly-spelt words. Report ONLY genuine issues; "
    "do not invent problems. Keep each explanation short and in the language of the text."
)

_INSTR = """Below are numbered text segments from a document.

Content category: {category}
Primary language: {language}
English spelling convention to enforce: {variant}

For each GENUINE issue output one JSON object:
- "seg": segment number (integer)
- "incorrect": the exact wrong word/phrase as written
- "suggestion": the corrected word/phrase
- "type": "spelling" | "grammar" | "sentence" | "context" | "punctuation" | "standardization"
- "priority": "High" (clear error / wrong meaning), "Medium" (clarity / standardization), "Low" (style)
- "explanation": brief reason, in the language of the text

Rules: judge word choice against the content category; prefer the stated English convention
(e.g. British spellings 'colour/organise' when British). Ignore proper nouns, names, places,
scheme names and acronyms. Return ONLY a JSON array (no prose, no code fences); [] if nothing.

SEGMENTS:
{segments}
"""


def _chunk(segments, max_chars=5000, max_items=40):
    chunk, size = [], 0
    for s in segments:
        if chunk and (size + len(s["text"]) > max_chars or len(chunk) >= max_items):
            yield chunk
            chunk, size = [], 0
        chunk.append(s)
        size += len(s["text"])
    if chunk:
        yield chunk


def _parse_json_array(txt: str) -> List[dict]:
    txt = txt.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\n?", "", txt).rstrip("`").strip()
    start, end = txt.find("["), txt.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(txt[start:end + 1])
        return data if isinstance(data, list) else []
    except Exception:
        return []


def ai_findings(segments, language, category, variant="indian",
                model=None, api_key=None, log=lambda *a: None) -> List[dict]:
    import anthropic
    try:
        client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
    except Exception as e:
        log("Could not start the AI client: %s" % e)
        return []
    model = model or DEFAULT_MODEL
    results = []
    for ci, chunk in enumerate(_chunk(segments)):
        numbered = "\n".join("[%d] (%s) %s" % (i, s["loc"], s["text"])
                             for i, s in enumerate(chunk))
        prompt = _INSTR.format(category=category or "General", language=language,
                               variant=VARIANT_LABEL.get(variant, "Indian English"),
                               segments=numbered)
        try:
            resp = client.messages.create(
                model=model, max_tokens=8000, system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = next((b.text for b in resp.content if b.type == "text"), "")
        except Exception as e:
            log("AI pass failed on chunk %d: %s" % (ci + 1, e))
            continue
        for item in _parse_json_array(text):
            try:
                seg = chunk[int(item.get("seg"))]
            except Exception:
                continue
            if not item.get("incorrect") or not item.get("suggestion"):
                continue
            results.append({
                "loc": seg["loc"],
                "language": LANG_NAME.get(detect_lang(seg["text"]), language),
                "type": item.get("type", "spelling"),
                "priority": item.get("priority") if item.get("priority") in PRIORITY_RANK else "Medium",
                "incorrect": str(item["incorrect"]), "suggestion": str(item["suggestion"]),
                "explanation": item.get("explanation", ""), "source": "ai",
            })
    return results


# --------------------------------------------------------------------------- #
#  Orchestration                                                               #
# --------------------------------------------------------------------------- #
def analyze(segments, language="auto", category="General", variant="indian",
            use_ai=True, use_spell=False, api_key=None, log=lambda *a: None) -> List[dict]:
    findings = []
    for seg in segments:
        lang = language if language in ("hi", "gu", "en") else detect_lang(seg["text"])
        findings += rule_findings(seg, lang, category)
        if use_spell:
            findings += spell_findings(seg, lang)

    api_key = (api_key or "").strip() or None
    can_ai = ai_available() or (api_key is not None and anthropic_sdk())
    if use_ai and can_ai:
        log("Running AI deep pass (%s)…" % DEFAULT_MODEL)
        ai_lang = LANG_NAME.get(language, "mixed (auto-detect per segment)")
        findings += ai_findings(segments, ai_lang, category, variant=variant,
                                api_key=api_key, log=log)
    elif use_ai:
        log("AI deep pass is OFF — paste your Anthropic API key to enable grammar & context analysis.")

    return _dedupe_and_sort(findings)


def _dedupe_and_sort(findings) -> List[dict]:
    src_rank = {"ai": 0, "rule": 1, "spell": 2}
    best: Dict[tuple, dict] = {}
    for f in findings:
        key = (f["loc"], f["incorrect"].strip(), f["suggestion"].strip())
        cur = best.get(key)
        if cur is None or src_rank.get(f["source"], 9) < src_rank.get(cur["source"], 9):
            best[key] = f
    merged = list(best.values())
    merged.sort(key=lambda f: (PRIORITY_RANK.get(f["priority"], 1), f["loc"]))
    for i, f in enumerate(merged, 1):
        f["num"] = i
        code = LANG_CODE.get(f.get("language"), "en")
        f["reference"] = ref_link(f.get("suggestion") or f.get("incorrect"), code)
    return merged
