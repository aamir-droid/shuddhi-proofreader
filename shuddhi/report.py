"""Build Word (.docx) and Excel (.xlsx) proofreading reports from findings."""
from __future__ import annotations
import datetime as _dt
from typing import List, Dict

PRIORITY_FILL = {"High": "F8CBAD", "Medium": "FFE699", "Low": "D9E1F2"}
PRIORITY_FONT = {"High": "C00000", "Medium": "BF8F00", "Low": "2E5496"}
_HEAD_FILL = "1F3864"
COLS = ["#", "Location", "Language", "Type", "Priority", "Incorrect", "Suggestion", "Explanation"]


def _meta(filename: str, category: str, language: str, n: int) -> Dict[str, str]:
    return {
        "File": filename, "Category": category or "General",
        "Language": language, "Total issues": str(n),
        "Generated": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# --------------------------------------------------------------------------- #
def build_docx(findings: List[dict], out_path: str, filename: str,
               category: str, language: str) -> str:
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    def shade(cell, hexcolor):
        tcpr = cell._tc.get_or_add_tcPr()
        sh = OxmlElement("w:shd")
        sh.set(qn("w:val"), "clear"); sh.set(qn("w:fill"), hexcolor)
        tcpr.append(sh)

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Nirmala UI"
    style.element.rPr.rFonts.set(qn("w:cs"), "Nirmala UI")
    style.font.size = Pt(10)

    title = doc.add_paragraph(); title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("Shuddhi — Proofreading Report"); r.bold = True; r.font.size = Pt(18)
    r.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)
    sub = doc.add_paragraph(); sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rs = sub.add_run("Hindi · Gujarati · English  |  वर्तनी · व्याकरण · संदर्भ")
    rs.font.size = Pt(10); rs.font.color.rgb = RGBColor(0x80, 0x80, 0x80)

    for k, v in _meta(filename, category, language, len(findings)).items():
        p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(0)
        rk = p.add_run("%s: " % k); rk.bold = True; rk.font.size = Pt(9)
        p.add_run(v).font.size = Pt(9)

    counts = {"High": 0, "Medium": 0, "Low": 0}
    for f in findings:
        counts[f.get("priority", "Medium")] = counts.get(f.get("priority", "Medium"), 0) + 1
    ps = doc.add_paragraph()
    ps.add_run("\nPriority summary — ").bold = True
    ps.add_run("High: %d   Medium: %d   Low: %d" % (counts["High"], counts["Medium"], counts["Low"]))

    if not findings:
        doc.add_paragraph("\n✅ No issues found.").runs[0].bold = True
        doc.save(out_path); return out_path

    table = doc.add_table(rows=1, cols=len(COLS)); table.style = "Table Grid"
    widths = [0.4, 1.3, 0.8, 0.9, 0.7, 1.3, 1.3, 2.0]
    for ci, name in enumerate(COLS):
        c = table.rows[0].cells[ci]; shade(c, _HEAD_FILL)
        run = c.paragraphs[0].add_run(name); run.bold = True
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF); run.font.size = Pt(9)

    for f in findings:
        cells = table.add_row().cells
        vals = [str(f.get("num", "")), f["loc"], f.get("language", ""), f.get("type", ""),
                f.get("priority", ""), f["incorrect"], f["suggestion"], f.get("explanation", "")]
        for ci, val in enumerate(vals):
            cell = cells[ci]; para = cell.paragraphs[0]; run = para.add_run(val)
            run.font.size = Pt(9)
            if COLS[ci] == "Incorrect":
                run.font.color.rgb = RGBColor(0xC0, 0x00, 0x00); run.font.strike = True
            elif COLS[ci] == "Suggestion":
                run.font.color.rgb = RGBColor(0x00, 0x86, 0x3B); run.bold = True
            elif COLS[ci] == "Priority":
                pr = f.get("priority", "Medium")
                shade(cell, PRIORITY_FILL.get(pr, "FFFFFF"))
                hexf = PRIORITY_FONT.get(pr, "000000")
                run.font.color.rgb = RGBColor(int(hexf[0:2], 16), int(hexf[2:4], 16), int(hexf[4:6], 16))
                run.bold = True

    tip = doc.add_paragraph()
    tip.add_run("\nRed (struck) = incorrect · Green (bold) = suggested correction. "
                "Rows are sorted by priority.").italic = True
    doc.save(out_path)
    return out_path


# --------------------------------------------------------------------------- #
def build_xlsx(findings: List[dict], out_path: str, filename: str,
               category: str, language: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook(); ws = wb.active; ws.title = "Corrections"
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    # Meta block
    ws["A1"] = "Shuddhi — Proofreading Report"; ws["A1"].font = Font(bold=True, size=14, color="1F3864")
    row = 2
    for k, v in _meta(filename, category, language, len(findings)).items():
        ws.cell(row=row, column=1, value=k).font = Font(bold=True, size=9)
        ws.cell(row=row, column=2, value=v).font = Font(size=9)
        row += 1
    header_row = row + 1

    for ci, name in enumerate(COLS, 1):
        c = ws.cell(row=header_row, column=ci, value=name)
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F3864")
        c.alignment = Alignment(horizontal="center", vertical="center"); c.border = border

    for ri, f in enumerate(findings, header_row + 1):
        vals = [f.get("num", ""), f["loc"], f.get("language", ""), f.get("type", ""),
                f.get("priority", ""), f["incorrect"], f["suggestion"], f.get("explanation", "")]
        for ci, val in enumerate(vals, 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.alignment = Alignment(vertical="top", wrap_text=(COLS[ci - 1] == "Explanation"))
            c.border = border; c.font = Font(size=9)
            if COLS[ci - 1] == "Incorrect":
                c.font = Font(size=9, color="C00000", strike=True)
            elif COLS[ci - 1] == "Suggestion":
                c.font = Font(size=9, color="00863B", bold=True)
            elif COLS[ci - 1] == "Priority":
                pr = f.get("priority", "Medium")
                c.fill = PatternFill("solid", fgColor=PRIORITY_FILL.get(pr, "FFFFFF"))
                c.font = Font(size=9, bold=True, color=PRIORITY_FONT.get(pr, "000000"))

    widths = [5, 16, 10, 13, 9, 20, 20, 42]
    for ci, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(ci)].width = w
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.auto_filter.ref = "A%d:%s%d" % (header_row, get_column_letter(len(COLS)),
                                       header_row + len(findings))
    wb.save(out_path)
    return out_path
