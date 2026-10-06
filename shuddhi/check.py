"""The proofreading engine: language detection, curated rules, dictionary
spellcheck, and an optional AI (Claude) deep pass. Each layer degrades
gracefully so the app still runs when a dependency or API key is missing.
"""
from __future__ import annotations
import json
import os
import re
from typing import List, Dict, Any

_HERE = os.path.dirname(__file__)
_RULES_PATH = os.path.join(_HERE, "rules.json")

PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}
LANG_NAME = {"hi": "Hindi", "gu": "Gujarati", "en": "English"}

# Unicode blocks
_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_GUJARATI = re.compile(r"[઀-૿]")
# Word tokenizer that keeps Indic matras/conjuncts together
_WORD_RE = re.compile(r"[A-Za-zऀ-ॿ઀-૿]+")


def detect_lang(text: str) -> str:
    """Return 'hi', 'gu', or 'en' based on dominant script."""
    guj = len(_GUJARATI.findall(text))
    dev = len(_DEVANAGARI.findall(text))
    if guj and guj >= dev:
        return "gu"
    if dev:
        return "hi"
    return "en"


# --------------------------------------------------------------------------- #
#  Layer 1 — curated rules (offline, precise)                                  #
# --------------------------------------------------------------------------- #
def _load_rules() -> Dict[str, List[dict]]:
    with open(_RULES_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_")}


_RULES = _load_rules()


def rule_findings(seg: Dict[str, str], lang: str, category: str) -> List[dict]:
    text = seg["text"]
    out = []
    for rule in _RULES.get(lang, []):
        cats = rule.get("categories", [])
        if not cats:
            continue  # disabled / reference-only entry
        if "all" not in cats and category.lower() not in [c.lower() for c in cats]:
            continue
        word = rule["word"]
        match_mode = rule.get("match", "word")
        if match_mode == "phrase":
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
#  Layer 2 — English dictionary spellcheck (optional, reliable)               #
# --------------------------------------------------------------------------- #
_EN_SPELL = None


def _en_speller():
    global _EN_SPELL
    if _EN_SPELL is None:
        try:
            from spellchecker import SpellChecker
            _EN_SPELL = SpellChecker(language="en")
        except Exception:
            _EN_SPELL = False
    return _EN_SPELL


def spell_findings(seg: Dict[str, str], lang: str, max_per_seg: int = 12) -> List[dict]:
    """Flag unknown English words. hi/gu dictionary spellcheck is handled by the
    curated rules + AI pass (Hunspell dictionaries can be added later)."""
    if lang != "en":
        return []
    sp = _en_speller()
    if not sp:
        return []
    tokens = [t for t in _WORD_RE.findall(seg["text"]) if t.isalpha() and len(t) > 2 and not t.isupper()]
    unknown = sp.unknown([t.lower() for t in tokens])
    out = []
    seen = set()
    for tok in tokens:
        low = tok.lower()
        if low in unknown and low not in seen:
            seen.add(low)
            corr = sp.correction(low)
            if corr and corr != low:
                out.append({
                    "loc": seg["loc"], "language": "English", "type": "spelling",
                    "priority": "Low", "incorrect": tok, "suggestion": corr,
                    "explanation": "Not found in English dictionary; nearest suggestion shown.",
                    "source": "spell",
                })
            if len(out) >= max_per_seg:
                break
    return out


# --------------------------------------------------------------------------- #
#  Layer 3 — AI deep pass (Claude): spelling + grammar + context + level       #
# --------------------------------------------------------------------------- #
DEFAULT_MODEL = os.environ.get("SHUDDHI_MODEL", "claude-opus-5-5")


def ai_available() -> bool:
    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except Exception:
        return False


_SYSTEM = (
    "You are an expert proofreader and copy-editor for Hindi, Gujarati and English. "
    "You correct spelling (वर्तनी), grammar (व्याकरण), sentence formation, punctuation, "
    "and context-appropriate word choice. For Hindi and Gujarati, follow standard "
    "orthography (मानक वर्तनी): correct maatras (short/long इ-ई, उ-ऊ), anusvara vs "
    "chandrabindu, visarga vs colon, nukta, and proper tatsam/tadbhav spellings as per "
    "NCERT / Central Hindi Directorate norms. Judge word choice against the stated "
    "content category. Report ONLY genuine issues — do not invent problems, and do not "
    "flag correct text, proper nouns, brand names, or deliberate English/technical terms. "
    "Keep explanations short and in the same language as the text."
)

_INSTR = """Below are numbered text segments from a document.

Content category: {category}
Primary language: {language}

For each genuine issue, output one JSON object with these fields:
- "seg": the segment number (integer)
- "incorrect": the exact wrong word or phrase as it appears
- "suggestion": the corrected word or phrase
- "type": one of "spelling", "grammar", "sentence", "context", "standardization"
- "priority": "High" (clear error, changes meaning/correctness), "Medium" (standardization / clarity), or "Low" (style/preference)
- "explanation": a brief reason, in the same language as the text

Return ONLY a JSON array of such objects (no prose, no markdown fences). If there are no issues, return [].

SEGMENTS:
{segments}
"""


def _chunk(segments: List[Dict[str, str]], max_chars: int = 5000, max_items: int = 40):
    chunk, size = [], 0
    for s in segments:
        t = s["text"]
        if chunk and (size + len(t) > max_chars or len(chunk) >= max_items):
            yield chunk
            chunk, size = [], 0
        chunk.append(s)
        size += len(t)
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


def ai_findings(segments: List[Dict[str, str]], language: str, category: str,
                model: str = None, log=lambda *a: None) -> List[dict]:
    import anthropic
    client = anthropic.Anthropic()
    model = model or DEFAULT_MODEL
    results: List[dict] = []
    for ci, chunk in enumerate(_chunk(segments)):
        numbered = "\n".join("[%d] (%s) %s" % (i, s["loc"], s["text"])
                             for i, s in enumerate(chunk))
        prompt = _INSTR.format(category=category or "General",
                               language=language, segments=numbered)
        try:
            resp = client.messages.create(
                model=model, max_tokens=8000, system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            text = next((b.text for b in resp.content if b.type == "text"), "")
        except Exception as e:  # network / auth / rate limit — degrade
            log("AI pass failed on chunk %d: %s" % (ci + 1, e))
            continue
        for item in _parse_json_array(text):
            try:
                idx = int(item.get("seg"))
                seg = chunk[idx]
            except Exception:
                continue
            if not item.get("incorrect") or not item.get("suggestion"):
                continue
            results.append({
                "loc": seg["loc"],
                "language": LANG_NAME.get(detect_lang(seg["text"]), language),
                "type": item.get("type", "spelling"),
                "priority": item.get("priority", "Medium") if item.get("priority") in PRIORITY_RANK else "Medium",
                "incorrect": str(item["incorrect"]), "suggestion": str(item["suggestion"]),
                "explanation": item.get("explanation", ""), "source": "ai",
            })
    return results


# --------------------------------------------------------------------------- #
#  Orchestration                                                               #
# --------------------------------------------------------------------------- #
def analyze(segments: List[Dict[str, str]], language: str = "auto",
            category: str = "General", use_ai: bool = True,
            use_spell: bool = True, log=lambda *a: None) -> List[dict]:
    """Run all enabled layers and return a merged, de-duplicated, prioritized list."""
    findings: List[dict] = []

    # Per-segment language (respect explicit choice, else auto-detect)
    for seg in segments:
        lang = language if language in ("hi", "gu", "en") else detect_lang(seg["text"])
        findings += rule_findings(seg, lang, category)
        if use_spell:
            findings += spell_findings(seg, lang)

    if use_ai and ai_available():
        log("Running AI deep pass (%s)..." % DEFAULT_MODEL)
        ai_lang = LANG_NAME.get(language, "mixed (auto-detect per segment)")
        findings += ai_findings(segments, ai_lang, category, log=log)
    elif use_ai:
        log("AI pass requested but no API key / SDK — skipping (rule + dictionary only).")

    return _dedupe_and_sort(findings)


def _dedupe_and_sort(findings: List[dict]) -> List[dict]:
    # Prefer AI > rule > spell when the same (loc, incorrect) is reported twice.
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
    return merged
