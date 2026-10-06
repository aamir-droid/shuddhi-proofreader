"""The proofreading engine (free, no API key):
  Layer 1 — curated standard-spelling rules (offline, precise)
  Layer 2 — conservative English dictionary spellcheck (skips names/places/acronyms)
  Layer 3 — LanguageTool free API for English grammar/spelling/style
  Layer 4 — official online-dictionary (Wiktionary) verification for Hindi (optional)
Every layer degrades gracefully if the network or a dependency is unavailable.
"""
from __future__ import annotations
import json
import os
import re
import urllib.parse
from typing import List, Dict

from . import langtool, webcheck

_HERE = os.path.dirname(__file__)
_RULES_PATH = os.path.join(_HERE, "rules.json")
_ALLOW_PATH = os.path.join(_HERE, "allowlist.json")

PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}
LANG_NAME = {"hi": "Hindi", "gu": "Gujarati", "en": "English"}
LANG_CODE = {"Hindi": "hi", "Gujarati": "gu", "English": "en"}

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_GUJARATI = re.compile(r"[઀-૿]")
_WORD_RE = re.compile(r"[A-Za-zऀ-ॿ઀-૿]+")
_COMBINING = re.compile(r"[̀-ͯǀ-ɏʰ-˿]")


def detect_lang(text: str) -> str:
    guj = len(_GUJARATI.findall(text))
    dev = len(_DEVANAGARI.findall(text))
    if guj and guj >= dev:
        return "gu"
    if dev:
        return "hi"
    return "en"


def _seg_lang(seg: Dict[str, str], language: str) -> str:
    return language if language in ("hi", "gu", "en") else detect_lang(seg["text"])


def looks_garbled(text: str) -> bool:
    dev = len(_DEVANAGARI.findall(text))
    bad = len(_COMBINING.findall(text))
    return dev > 0 and bad >= max(3, dev * 0.04)


# ---------- reference links (official dictionaries) ----------
def ref_link(word: str, lang_code: str) -> str:
    w = urllib.parse.quote((word or "").strip())
    if lang_code == "hi":
        return "https://www.shabdkosh.com/search-dictionary?lc=hi&sl=hi&tl=en&e=" + w
    if lang_code == "gu":
        return "https://www.shabdkosh.com/search-dictionary?lc=gu&sl=gu&tl=en&e=" + w
    return "https://dictionary.cambridge.org/dictionary/english/" + urllib.parse.quote(
        (word or "").strip().lower())


# ---------- Layer 1: curated rules ----------
def _load_rules():
    with open(_RULES_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _load_allow():
    with open(_ALLOW_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    words = set()
    for k, v in data.items():
        if not k.startswith("_"):
            for w in v:
                words.add(w.lower())
    return words


_RULES = _load_rules()
_ALLOW = _load_allow()


def rule_findings(seg, lang, category) -> List[dict]:
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
                "type": rule.get("type", "spelling"), "priority": rule.get("priority", "Medium"),
                "incorrect": word, "suggestion": rule["suggestion"],
                "explanation": rule.get("note", ""), "source": "rule",
            })
    return out


# ---------- Layer 2: conservative English dictionary spellcheck ----------
_EN_SPELL = None


def _en_speller():
    global _EN_SPELL
    if _EN_SPELL is None:
        try:
            from spellchecker import SpellChecker
            sp = SpellChecker(language="en")
            sp.word_frequency.load_words(_ALLOW)
            _EN_SPELL = sp
        except Exception:
            _EN_SPELL = False
    return _EN_SPELL


def spell_findings(seg, lang, max_per_seg=10) -> List[dict]:
    if lang != "en":
        return []
    sp = _en_speller()
    if not sp:
        return []
    out, seen = [], set()
    for tok in _WORD_RE.findall(seg["text"]):
        if not tok.isalpha() or len(tok) < 4:
            continue
        if tok[0].isupper() or tok.isupper():
            continue
        low = tok.lower()
        if low in seen or low in _ALLOW:
            continue
        if not sp.unknown([low]):
            continue
        seen.add(low)
        corr = sp.correction(low)
        if corr and corr != low:
            out.append({
                "loc": seg["loc"], "language": "English", "type": "spelling", "priority": "Low",
                "incorrect": tok, "suggestion": corr,
                "explanation": "Not in the English dictionary; nearest match shown "
                               "(verify — may be a name or technical term).",
                "source": "spell",
            })
        if len(out) >= max_per_seg:
            break
    return out


# ---------- Orchestration ----------
def _keep_langtool(f: dict) -> bool:
    """Drop LanguageTool hits that touch proper nouns, acronyms or allowlisted
    (e.g. UK/Indian) words — so names/places and British spellings aren't flagged."""
    w = f["incorrect"].strip()
    if " " not in w:                         # single token
        if w.lower() in _ALLOW:
            return False
        if f["type"] == "spelling" and (w[:1].isupper() or w.isupper()):
            return False
    return True


def deep_available() -> bool:
    """The free deep check (LanguageTool) needs only internet access."""
    return True


def analyze(segments, language="auto", category="General", variant="indian",
            use_deep=True, use_spell=False, use_dict=False, log=lambda *a: None) -> List[dict]:
    findings = []
    for seg in segments:
        lang = _seg_lang(seg, language)
        findings += rule_findings(seg, lang, category)
        if use_spell:
            findings += spell_findings(seg, lang)

    if use_deep:
        en_segs = [s for s in segments if _seg_lang(s, language) == "en"]
        if en_segs:
            log("Running free grammar check (LanguageTool) on %d English segment(s)…" % len(en_segs))
            findings += [f for f in langtool.check(en_segs, variant=variant, log=log)
                         if _keep_langtool(f)]
        else:
            log("No English text detected for the LanguageTool grammar check.")

    if use_dict:
        hi_segs = [s for s in segments if _seg_lang(s, language) == "hi"]
        if hi_segs:
            log("Verifying Hindi words against हिन्दी विक्षनरी (online dictionary)…")
            findings += webcheck.verify_hindi(hi_segs, log=log)

    return _dedupe_and_sort(findings)


def _dedupe_and_sort(findings) -> List[dict]:
    src_rank = {"langtool": 0, "rule": 1, "spell": 2, "webcheck": 3}
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
