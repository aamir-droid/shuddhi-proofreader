"""Free grammar / spelling / style checking via the public LanguageTool API.
No API key required. English (and other LT-supported languages) only — Hindi and
Gujarati are not supported by LanguageTool, so those rely on rules + dictionary.
"""
from __future__ import annotations
import json
import time
import urllib.parse
import urllib.request
from typing import List, Dict

API = "https://api.languagetool.org/v2/check"
UA = {"User-Agent": "Shuddhi/1.0 (proofreading tool)"}

# English spelling convention -> LanguageTool language code
VARIANT_LT = {"uk": "en-GB", "us": "en-US", "indian": "en-GB"}  # Indian English ~ British

_ISSUE_PRIORITY = {"misspelling": "High", "grammar": "High", "typographical": "Medium",
                   "whitespace": "Low", "duplication": "Medium", "style": "Low",
                   "locale-violation": "Medium", "uncategorized": "Low"}
_ISSUE_TYPE = {"misspelling": "spelling", "grammar": "grammar", "typographical": "punctuation",
               "whitespace": "punctuation", "duplication": "grammar", "style": "style"}


def _call(text: str, lang: str) -> dict:
    data = urllib.parse.urlencode({"text": text, "language": lang, "level": "default"}).encode()
    req = urllib.request.Request(API, data=data, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def _chunk(segments, max_chars=9000, max_items=40):
    chunk, size = [], 0
    for s in segments:
        if chunk and (size + len(s["text"]) > max_chars or len(chunk) >= max_items):
            yield chunk
            chunk, size = [], 0
        chunk.append(s)
        size += len(s["text"])
    if chunk:
        yield chunk


def check(en_segments: List[Dict], variant: str = "indian", max_chunks: int = 12,
          log=lambda *a: None) -> List[dict]:
    lang = VARIANT_LT.get(variant, "en-GB")
    findings: List[dict] = []
    for ci, chunk in enumerate(_chunk(en_segments)):
        if ci >= max_chunks:
            log("LanguageTool: stopped after %d chunks (free-API courtesy limit)." % max_chunks)
            break
        combined, spans = "", []
        for s in chunk:
            start = len(combined)
            combined += s["text"] + "\n\n"
            spans.append((start, start + len(s["text"]), s))
        try:
            res = _call(combined, lang)
        except Exception as e:
            log("LanguageTool unavailable (%s) — using rules/spelling only." % str(e)[:60])
            break
        for m in res.get("matches", []):
            off, ln = m.get("offset", 0), m.get("length", 0)
            seg = next((s for (a, b, s) in spans if a <= off < b), None)
            if seg is None:
                continue
            incorrect = combined[off:off + ln]
            if not incorrect.strip():
                continue
            reps = m.get("replacements", [])
            sugg = reps[0]["value"] if reps else ""
            if not sugg or sugg == incorrect:
                continue  # skip matches with no concrete fix (reduces noise)
            issue = m.get("rule", {}).get("issueType", "uncategorized")
            findings.append({
                "loc": seg["loc"], "language": "English",
                "type": _ISSUE_TYPE.get(issue, "grammar"),
                "priority": _ISSUE_PRIORITY.get(issue, "Low"),
                "incorrect": incorrect, "suggestion": sugg,
                "explanation": (m.get("shortMessage") or m.get("message", ""))[:180],
                "source": "langtool",
            })
        time.sleep(1.1)  # be gentle on the free shared API
    return findings
