---
title: Shuddhi Proofreader
emoji: ✍️
colorFrom: indigo
colorTo: pink
sdk: gradio
sdk_version: 5.50.0
app_file: app.py
pinned: false
license: mit
short_description: Hindi/Gujarati/English proofreading — spelling, grammar, context
---

# शुद्धि · Shuddhi — Multilingual Proofreader

Upload a **PDF, Word, Excel, or CSV**, choose the **content category** (education,
speech, official, …), and get a **Word + Excel report** listing every *incorrect
term → standardized suggestion*, ranked by priority.

Languages: **Hindi, Gujarati, English** (auto-detected per segment).

## What it checks
- **Spelling / वर्तनी** — maatra errors (इ/ई, उ/ऊ), anusvara vs chandrabindu, visarga vs colon, nukta, tatsam/tadbhav.
- **Grammar & sentence formation** — agreement, verb forms, word order.
- **Context / level** — word choice appropriate to the stated category.
- **Standardization** — preferred official/NCERT-aligned forms.

## How the engine works (100% free, no API key)
1. **Curated rules** (offline, precise) — standard-spelling corrections in `shuddhi/rules.json` (Hindi/Gujarati/English), with an allowlist so Indian names, places, schemes and acronyms are never flagged.
2. **LanguageTool** (`shuddhi/langtool.py`) — the free public LanguageTool API checks English grammar, spelling and style. Choose Indian/British/American spelling. No key.
3. **Official dictionary verification** (`shuddhi/webcheck.py`) — optional cross-check of Hindi words against हिन्दी विक्षनरी (Wiktionary).
4. **Reference links** — every finding links to an authoritative dictionary (शब्दकोश for Hindi/Gujarati, Cambridge for English).

LanguageTool doesn't support Hindi/Gujarati grammar, so those languages rely on the rules + dictionary layers.

---

## Deploy free on Hugging Face Spaces

1. Create a free account at <https://huggingface.co> and click **New Space**.
2. **SDK: Gradio**, name it (e.g. `shuddhi-proofreader`), visibility **Public**.
3. Upload every file in this folder (keep the `shuddhi/` subfolder), or push with git:
   ```bash
   git clone https://huggingface.co/spaces/<your-username>/shuddhi-proofreader
   # copy these files in, then:
   git add . && git commit -m "Shuddhi proofreader" && git push
   ```
4. **Enable AI analysis:** Space → **Settings → Variables and secrets → New secret**
   - Name: `ANTHROPIC_API_KEY`  ·  Value: your key from <https://console.anthropic.com>
   - (Optional) `SHUDDHI_MODEL` — defaults to `claude-opus-5-5`. For lower cost set
     `claude-haiku-4-5` or `claude-sonnet-5-5`.
5. The Space builds (`packages.txt` installs Tesseract OCR; `requirements.txt` installs Python deps) and gives you a public URL anyone can use.

> Free CPU Spaces work for digital documents and light OCR. Heavy OCR on large scanned PDFs may be slow — upgrade hardware if needed.

## Run locally
```bash
pip install -r requirements.txt
# optional, for OCR: install Tesseract + hin/guj/eng language data
# optional, for AI:  export ANTHROPIC_API_KEY=sk-ant-...
python app.py        # opens http://localhost:7860
```

## Cost note
Rules + dictionary are free. The AI pass costs per document based on the model:
Haiku (cheapest) < Sonnet < Opus. Set `SHUDDHI_MODEL` to control it.

## Extending
- Add corrections to `shuddhi/rules.json` (per language, with category tags).
- Hindi/Gujarati Hunspell dictionaries can be wired into `shuddhi/check.py` for offline spellcheck in those languages.
