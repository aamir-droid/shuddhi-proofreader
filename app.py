"""Shuddhi — multilingual proofreading web app (Hindi / Gujarati / English).

Classic, premium UI built on Gradio 5. Upload a PDF / Word / Excel / CSV, choose
the content category, and get a Word + Excel report of incorrect terms with
standardized suggestions, ranked by priority.
"""
import os
import tempfile

import gradio as gr
import pandas as pd

from shuddhi import extract, check, report

LANG_CHOICES = [("Auto-detect", "auto"), ("Hindi (हिंदी)", "hi"),
                ("Gujarati (ગુજરાતી)", "gu"), ("English", "en")]
CATEGORY_CHOICES = ["General", "Education", "Speech", "Official / Government",
                    "Literary", "News / Media", "Marketing", "Legal"]
VARIANT_CHOICES = [("Indian English", "indian"), ("British (UK) English", "uk"),
                   ("American (US) English", "us")]

AI_ON = check.ai_available()

# --------------------------------------------------------------------------- #
#  Theme + styling                                                             #
# --------------------------------------------------------------------------- #
THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.indigo,
    secondary_hue=gr.themes.colors.amber,
    neutral_hue=gr.themes.colors.slate,
    font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
).set(
    body_background_fill="#f6f3ec",
    body_background_fill_dark="#14161c",
    block_background_fill="#ffffff",
    block_border_width="1px",
    block_shadow="0 1px 2px rgba(16,24,40,.04), 0 8px 24px rgba(16,24,40,.06)",
    block_radius="16px",
    block_label_text_weight="600",
    input_background_fill="#fbfaf7",
    button_large_radius="12px",
    button_primary_background_fill="linear-gradient(180deg,#273a6b 0%,#172049 100%)",
    button_primary_background_fill_hover="linear-gradient(180deg,#2f4580 0%,#1b2550 100%)",
    button_primary_text_color="#ffffff",
)

HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,400;0,9..144,500;0,9..144,600;1,9..144,500&family=Inter:wght@400;500;600&family=Tiro+Devanagari+Hindi&family=Noto+Sans+Gujarati:wght@400;600&display=swap" rel="stylesheet">
"""

CSS = """
:root{
  --navy:#172049; --navy2:#273a6b; --gold:#c6972f; --gold-soft:#e7c877;
  --cream:#f6f3ec; --ink:#1c2230; --muted:#6b7280; --line:#e7e2d6;
  --serif:'Fraunces',Georgia,serif;
  --hi:'Tiro Devanagari Hindi','Noto Sans Devanagari',serif;
  --gu:'Noto Sans Gujarati',sans-serif;
}
.gradio-container{max-width:1180px!important;margin:0 auto!important;}
footer{display:none!important;}

/* ---------- hero ---------- */
.sh-hero{
  position:relative;overflow:hidden;border-radius:20px;margin:6px 0 20px;
  padding:34px 40px 30px;color:#f4f1e9;
  background:
    radial-gradient(1200px 300px at 85% -40%, rgba(198,151,47,.35), transparent 60%),
    linear-gradient(135deg,#141c40 0%,#1f2a5a 55%,#2b3a74 100%);
  box-shadow:0 12px 40px rgba(20,28,64,.28);
  border:1px solid rgba(231,200,119,.25);
}
.sh-hero:before{content:"";position:absolute;inset:0;
  background-image:radial-gradient(rgba(255,255,255,.06) 1px,transparent 1px);
  background-size:18px 18px;opacity:.5;pointer-events:none;}
.sh-rule{height:2px;width:72px;background:linear-gradient(90deg,var(--gold),transparent);margin:14px 0 0;border:0;}
.sh-wordmark{display:flex;align-items:baseline;gap:16px;position:relative;z-index:1;}
.sh-deva{font-family:var(--hi);font-size:52px;line-height:1;letter-spacing:.5px;
  color:#fff;text-shadow:0 2px 18px rgba(0,0,0,.25);}
.sh-latin{font-family:var(--serif);font-weight:600;font-size:30px;letter-spacing:.3px;color:var(--gold-soft);}
.sh-tag{font-family:var(--serif);font-style:italic;font-weight:500;font-size:17px;
  color:#d8dcea;margin-top:12px;position:relative;z-index:1;}
.sh-sub{font-size:13.5px;color:#aab2cc;margin-top:6px;position:relative;z-index:1;letter-spacing:.2px;}
.sh-emblem{position:absolute;right:30px;top:26px;opacity:.9;z-index:1;}

/* ---------- status pill ---------- */
.sh-status{display:inline-flex;align-items:center;gap:9px;font-size:13.5px;font-weight:500;
  padding:9px 16px;border-radius:999px;margin:2px 0 4px;}
.sh-status.on{background:#eaf6ee;color:#146c43;border:1px solid #bfe3cc;}
.sh-status.off{background:#fdf3e3;color:#9a6700;border:1px solid #f1d9a9;}
.sh-status .dot{width:8px;height:8px;border-radius:50%;background:currentColor;box-shadow:0 0 0 4px rgba(20,108,67,.12);}

/* ---------- section headings ---------- */
.sh-eyebrow{font-family:var(--serif);font-weight:600;font-size:12px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--gold);margin:2px 0 2px;}
h1,h2,.prose h2{font-family:var(--serif)!important;color:var(--ink);}

/* ---------- premium cards ---------- */
.sh-card{background:#fff;border:1px solid var(--line);border-radius:18px;
  padding:20px 20px 14px;box-shadow:0 1px 2px rgba(16,24,40,.04),0 10px 28px rgba(16,24,40,.06);}
.sh-card.pad-lg{padding:22px 24px;}

/* ---------- primary button ---------- */
#sh-go{font-family:var(--serif)!important;font-weight:600!important;font-size:17px!important;
  letter-spacing:.3px;padding:14px 20px!important;border:1px solid rgba(231,200,119,.5)!important;
  box-shadow:0 8px 20px rgba(23,32,73,.25)!important;}
#sh-go:hover{filter:brightness(1.07);}

/* ---------- stat chips ---------- */
.sh-stats{display:flex;gap:12px;flex-wrap:wrap;margin:2px 0 10px;}
.sh-chip{flex:1;min-width:120px;border-radius:14px;padding:14px 16px;border:1px solid var(--line);
  background:#fff;box-shadow:0 6px 16px rgba(16,24,40,.05);}
.sh-chip .n{font-family:var(--serif);font-size:26px;font-weight:600;line-height:1;}
.sh-chip .l{font-size:12px;color:var(--muted);margin-top:5px;letter-spacing:.03em;text-transform:uppercase;}
.sh-chip.total .n{color:var(--navy);} .sh-chip.high .n{color:#c0392b;}
.sh-chip.med .n{color:#b7791f;} .sh-chip.low .n{color:#2d6cdf;}

/* ---------- how-it-works trio ---------- */
.sh-steps{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:6px;}
.sh-step{background:#fff;border:1px solid var(--line);border-radius:14px;padding:16px 16px 14px;}
.sh-step .k{font-family:var(--serif);color:var(--gold);font-weight:600;font-size:13px;letter-spacing:.1em;}
.sh-step .t{font-weight:600;color:var(--ink);margin:6px 0 4px;font-size:15px;}
.sh-step .d{font-size:13px;color:var(--muted);line-height:1.5;}
@media(max-width:820px){.sh-steps{grid-template-columns:1fr;}}

/* dataframe polish */
.sh-table table{font-size:13px;}
.sh-table thead th{background:var(--navy)!important;color:#fff!important;font-weight:600!important;}
"""

EMBLEM_SVG = """
<svg class="sh-emblem" width="54" height="54" viewBox="0 0 54 54" fill="none">
  <circle cx="27" cy="27" r="25" stroke="#e7c877" stroke-opacity=".55" stroke-width="1.4"/>
  <circle cx="27" cy="27" r="19" stroke="#e7c877" stroke-opacity=".3" stroke-width="1"/>
  <path d="M38 17c-9 1-17 7-20 17-1 3-1 5-1 5s3-1 5-2c9-4 14-12 16-20z"
        fill="#e7c877" fill-opacity=".9"/>
  <path d="M17 39c3-6 7-10 13-13" stroke="#172049" stroke-width="1.3" stroke-linecap="round"/>
</svg>
"""


def status_html():
    if AI_ON:
        return ('<div class="sh-status on"><span class="dot"></span>AI deep analysis is ON'
                ' &nbsp;·&nbsp; model <code>%s</code></div>' % check.DEFAULT_MODEL)
    return ('<div class="sh-status off"><span class="dot"></span>'
            'For grammar &amp; context analysis, paste your own Anthropic API key below '
            '— <a href="https://console.anthropic.com/settings/keys" target="_blank" '
            'rel="noopener" style="color:#9a6700;font-weight:600">get a free key ↗</a></div>')


HERO = """
<div class="sh-hero">
  %s
  <div class="sh-wordmark"><span class="sh-deva">शुद्धि</span><span class="sh-latin">Shuddhi</span></div>
  <hr class="sh-rule"/>
  <div class="sh-tag">Proofreading, refined — spelling, grammar &amp; context in Hindi, Gujarati and English.</div>
  <div class="sh-sub">वर्तनी · व्याकरण · वाक्य-रचना · संदर्भ-अनुकूल सुझाव — प्राथमिकता के अनुसार क्रमबद्ध</div>
</div>
""" % EMBLEM_SVG

STEPS = """
<div class="sh-steps">
  <div class="sh-step"><div class="k">STEP 01</div><div class="t">Upload &amp; classify</div>
    <div class="d">Drop a PDF, Word, Excel or CSV and tell Shuddhi what kind of content it is.</div></div>
  <div class="sh-step"><div class="k">STEP 02</div><div class="t">Three-layer review</div>
    <div class="d">Curated standard-spelling rules, dictionary spellcheck, and an AI pass for grammar &amp; context.</div></div>
  <div class="sh-step"><div class="k">STEP 03</div><div class="t">Download report</div>
    <div class="d">A Word + Excel sheet of every <i>incorrect → suggested</i> term, ranked by priority.</div></div>
</div>
"""


def stats_html(findings):
    if not findings:
        return ""
    hi = sum(1 for f in findings if f["priority"] == "High")
    me = sum(1 for f in findings if f["priority"] == "Medium")
    lo = sum(1 for f in findings if f["priority"] == "Low")
    return ("""<div class="sh-stats">
      <div class="sh-chip total"><div class="n">%d</div><div class="l">Total issues</div></div>
      <div class="sh-chip high"><div class="n">%d</div><div class="l">High priority</div></div>
      <div class="sh-chip med"><div class="n">%d</div><div class="l">Medium</div></div>
      <div class="sh-chip low"><div class="n">%d</div><div class="l">Low</div></div>
    </div>""" % (len(findings), hi, me, lo))


# --------------------------------------------------------------------------- #
#  Core run                                                                    #
# --------------------------------------------------------------------------- #
def run(files, language, variant, category, custom_category, use_ai, use_ocr, use_spell,
        out_format, user_key=""):
    if not files:
        return None, None, pd.DataFrame(), "", "⚠️ Please upload at least one file to begin."

    cat = (custom_category or "").strip() or category
    logs = []
    def log(*a): logs.append(" ".join(str(x) for x in a))

    all_findings, base_names = [], []
    for fobj in files:
        path = fobj.name if hasattr(fobj, "name") else fobj
        fname = os.path.basename(path)
        base_names.append(os.path.splitext(fname)[0])
        try:
            segs = extract.extract(path, ocr=use_ocr, ocr_lang=language)
        except Exception as e:
            log("Could not read %s: %s" % (fname, e)); continue
        if not segs:
            log("⚠️ No readable text in **%s**. It is likely a scanned/image PDF — "
                "turn on **OCR** in Advanced options and try again." % fname)
            continue
        garbled = sum(1 for s in segs if check.looks_garbled(s["text"]))
        if garbled and garbled >= len(segs) * 0.4:
            log("⚠️ **%s** has a damaged text layer (broken font encoding from the "
                "PowerPoint→PDF export). Results will be poor — turn on **OCR** to read it "
                "from the page images instead." % fname)
        log("**%s** → %d text segment(s) scanned" % (fname, len(segs)))
        findings = check.analyze(segs, language=language, category=cat, variant=variant,
                                 use_ai=use_ai, use_spell=use_spell, api_key=user_key, log=log)
        for f in findings:
            f["file"] = fname
        all_findings += findings

    for i, f in enumerate(all_findings, 1):
        f["num"] = i

    df = pd.DataFrame([{
        "#": f["num"], "File": f.get("file", ""), "Location": f["loc"],
        "Language": f.get("language", ""), "Type": f.get("type", ""),
        "Priority": f.get("priority", ""), "Incorrect": f["incorrect"],
        "Suggestion": f["suggestion"], "Explanation": f.get("explanation", ""),
        "Reference": f.get("reference", ""),
    } for f in all_findings])

    tmpdir = tempfile.mkdtemp(prefix="shuddhi_")
    stem = base_names[0] if len(base_names) == 1 else "shuddhi_report"
    lang_label = dict(LANG_CHOICES).get(language, language)
    docx_path = xlsx_path = None
    if out_format in ("Word", "Both"):
        docx_path = os.path.join(tmpdir, stem + "_proofread.docx")
        report.build_docx(all_findings, docx_path, stem, cat, lang_label)
    if out_format in ("Excel", "Both"):
        xlsx_path = os.path.join(tmpdir, stem + "_proofread.xlsx")
        report.build_xlsx(all_findings, xlsx_path, stem, cat, lang_label)

    if all_findings:
        head = "**%d issue(s) found** across %d file(s)." % (len(all_findings), len(base_names))
    else:
        head = "No issues found by the active checks."
    note = ""
    if not AI_ON and not (user_key or "").strip():
        note = ("\n\n> ℹ️ **AI deep analysis was off**, so only spelling + curated rules ran. "
                "For grammar, sentence formation and context-aware suggestions, paste your "
                "**Anthropic API key** in the field on the left and run again.")
    summary = head + note + "\n\n" + "\n".join("· " + l for l in logs)
    return docx_path, xlsx_path, df, stats_html(all_findings), summary


# --------------------------------------------------------------------------- #
#  UI                                                                          #
# --------------------------------------------------------------------------- #
with gr.Blocks(title="Shuddhi — Proofreader", theme=THEME, css=CSS, head=HEAD,
               analytics_enabled=False) as demo:
    gr.HTML(HERO)
    gr.HTML(status_html())

    with gr.Row(equal_height=False):
        with gr.Column(scale=5, elem_classes="sh-card pad-lg"):
            gr.HTML('<div class="sh-eyebrow">Your document</div>')
            files = gr.File(label="Upload PDF · Word · Excel · CSV",
                            file_types=[".pdf", ".docx", ".xlsx", ".xlsm", ".csv", ".tsv", ".txt"],
                            file_count="multiple")
            language = gr.Dropdown([c[0] for c in LANG_CHOICES], value="Auto-detect",
                                   label="Language", type="index")
            category = gr.Dropdown(CATEGORY_CHOICES, value="General",
                                   label="Content category", info="Tailors context & word-choice suggestions")
            variant = gr.Dropdown([c[0] for c in VARIANT_CHOICES], value="Indian English",
                                  label="English spelling convention", type="index",
                                  info="Which English to enforce (e.g. UK: colour, organise)")
            custom_category = gr.Textbox(label="Describe it yourself (optional)",
                                         placeholder="e.g. Class-6 science textbook · political speech · government circular")
            if not AI_ON:
                user_key = gr.Textbox(type="password", label="🔑 Anthropic API key — enables AI (optional)",
                                      placeholder="sk-ant-…",
                                      info="Bring your own key to unlock grammar + context analysis. "
                                           "Used only for this request, never stored. Get one at console.anthropic.com.")
            else:
                user_key = gr.Textbox(visible=False, value="")
            with gr.Accordion("Advanced options", open=False):
                use_ai = gr.Checkbox(value=True, label="AI deep analysis — grammar, sentence formation, context & level",
                                     interactive=True)
                use_ocr = gr.Checkbox(value=False, label="OCR for scanned / image PDFs (recommended for presentations)")
                use_spell = gr.Checkbox(value=False,
                                        label="Strict English dictionary spellcheck (may flag names/places — off by default)")
                out_format = gr.Radio(["Both", "Word", "Excel"], value="Both", label="Output format")
            btn = gr.Button("✦  Proofread", variant="primary", elem_id="sh-go")

        with gr.Column(scale=7, elem_classes="sh-card pad-lg"):
            gr.HTML('<div class="sh-eyebrow">Results</div>')
            stats = gr.HTML()
            summary = gr.Markdown("Upload a document and press **Proofread** to see corrections here.")
            table = gr.Dataframe(label="Findings — sorted by priority", wrap=True,
                                 interactive=False, elem_classes="sh-table")
            gr.HTML('<div class="sh-eyebrow" style="margin-top:8px">Download</div>')
            with gr.Row():
                word_out = gr.File(label="Word report (.docx)")
                excel_out = gr.File(label="Excel report (.xlsx)")

    gr.HTML('<div class="sh-eyebrow" style="margin:22px 0 2px">How it works</div>')
    gr.HTML(STEPS)
    gr.HTML('<div style="text-align:center;color:#8a8f9c;font-size:12.5px;margin:22px 0 6px">'
            'Files are processed in memory for your request and not stored. '
            '&nbsp;·&nbsp; शुद्धि · Shuddhi</div>')

    def _run(files, language_idx, variant_idx, category, custom_category, use_ai, use_ocr,
             use_spell, out_format, user_key):
        code = LANG_CHOICES[language_idx][1] if isinstance(language_idx, int) else "auto"
        var = VARIANT_CHOICES[variant_idx][1] if isinstance(variant_idx, int) else "indian"
        return run(files, code, var, category, custom_category, use_ai, use_ocr, use_spell,
                   out_format, user_key)

    btn.click(_run,
              inputs=[files, language, variant, category, custom_category, use_ai, use_ocr,
                      use_spell, out_format, user_key],
              outputs=[word_out, excel_out, table, stats, summary])


if __name__ == "__main__":
    demo.launch(
        server_name=os.environ.get("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.environ.get("PORT", 7860)),
        show_api=False,
        share=os.environ.get("SHUDDHI_SHARE", "0") == "1",
    )
