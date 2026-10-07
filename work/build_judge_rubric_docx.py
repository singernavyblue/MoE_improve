# -*- coding: utf-8 -*-
"""Build the judge-rubric standards document as DOCX (compact_reference_guide preset)."""
import re
from docx import Document
from docx.shared import Pt, Inches, RGBColor, Twips
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

SRC = "outputs/裁判标准_ClawTrack四维适配版.md"
OUT = "outputs/裁判标准_ClawTrack四维适配版.docx"

BLUE = RGBColor(0x2E, 0x74, 0xB5)
DARK_BLUE = RGBColor(0x1F, 0x4D, 0x78)
INK = RGBColor(0x0B, 0x25, 0x45)
BODY = RGBColor(0x1A, 0x1A, 0x1A)
MUTED = RGBColor(0x55, 0x55, 0x55)
HEADER_FILL = "E8EEF5"

FONT_LATIN = "Calibri"
FONT_CJK = "PingFang SC"
FONT_CODE = "Consolas"


def set_run_font(run, size=11, bold=False, italic=False, color=BODY, mono=False, name=None):
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    run.font.name = name or (FONT_CODE if mono else FONT_LATIN)
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:ascii"), name or (FONT_CODE if mono else FONT_LATIN))
    rFonts.set(qn("w:hAnsi"), name or (FONT_CODE if mono else FONT_LATIN))
    rFonts.set(qn("w:eastAsia"), FONT_CJK)


def para_format(p, before=0, after=6, line=1.25, align=WD_ALIGN_PARAGRAPH.LEFT):
    pf = p.paragraph_format
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    pf.alignment = align


def add_inline(p, text, size=11, base_bold=False, color=BODY, mono=False):
    """Render **bold** and `code` inline markers."""
    tokens = re.split(r"(\*\*.+?\*\*|`[^`]+`)", text)
    for tok in tokens:
        if not tok:
            continue
        if tok.startswith("**") and tok.endswith("**"):
            run = p.add_run(tok[2:-2])
            set_run_font(run, size=size, bold=True, color=color, mono=mono)
        elif tok.startswith("`") and tok.endswith("`"):
            run = p.add_run(tok[1:-1])
            set_run_font(run, size=max(size - 0.5, 8), mono=True, color=DARK_BLUE)
        else:
            run = p.add_run(tok)
            set_run_font(run, size=size, bold=base_bold, color=color, mono=mono)
    return p


def set_cell_margins(cell, top=80, bottom=80, start=120, end=120):
    tcPr = cell._tc.get_or_add_tcPr()
    mar = tcPr.find(qn("w:tcMar"))
    if mar is None:
        mar = OxmlElement("w:tcMar")
        tcPr.append(mar)
    for tag, val in (("top", top), ("bottom", bottom), ("start", start), ("end", end)):
        el = mar.find(qn(f"w:{tag}"))
        if el is None:
            el = OxmlElement(f"w:{tag}")
            mar.append(el)
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths_in):
    """Fixed DXA geometry: tblW, tblInd, tblGrid, and every tcW agree."""
    total_in = sum(widths_in)
    assert abs(total_in - 6.5) < 0.001, f"table width {total_in} != 6.5"
    widths_dxa = [int(w * 1440) for w in widths_in]
    tbl = table._tbl
    tblPr = tbl.tblPr
    tblW = tblPr.find(qn("w:tblW"))
    if tblW is None:
        tblW = OxmlElement("w:tblW")
        tblPr.append(tblW)
    tblW.set(qn("w:w"), str(sum(widths_dxa)))
    tblW.set(qn("w:type"), "dxa")
    tblInd = tblPr.find(qn("w:tblInd"))
    if tblInd is None:
        tblInd = OxmlElement("w:tblInd")
        tblPr.append(tblInd)
    tblInd.set(qn("w:w"), "120")
    tblInd.set(qn("w:type"), "dxa")
    tbl.set(qn("w:type"), "dxa")
    # grid
    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        tbl.remove(grid)
    grid = OxmlElement("w:tblGrid")
    for w in widths_dxa:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(w))
        grid.append(gc)
    tbl.insert(list(tbl).index(tblPr) + 1, grid)
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            tcPr = cell._tc.get_or_add_tcPr()
            tcW = tcPr.find(qn("w:tcW"))
            if tcW is None:
                tcW = OxmlElement("w:tcW")
                tcPr.append(tcW)
            tcW.set(qn("w:w"), str(widths_dxa[i]))
            tcW.set(qn("w:type"), "dxa")


def mark_header_row(row):
    trPr = row._tr.get_or_add_trPr()
    tblHeader = OxmlElement("w:tblHeader")
    tblHeader.set(qn("w:val"), "true")
    trPr.append(tblHeader)


def shade_cell(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def add_body(doc, text, size=11, bold=False, color=BODY, after=6, style=None):
    p = doc.add_paragraph(style=style)
    para_format(p, before=0, after=after)
    add_inline(p, text, size=size, base_bold=bold, color=color)
    return p


def add_bullet(doc, text, size=11):
    p = doc.add_paragraph(style="List Bullet")
    para_format(p, before=0, after=4)
    p.paragraph_format.left_indent = Inches(0.375)
    p.paragraph_format.first_line_indent = Inches(-0.188)
    add_inline(p, text, size=size)
    return p


def add_code_block(doc, lines):
    p = doc.add_paragraph()
    para_format(p, before=2, after=8)
    pPr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), "F2F4F7")
    pPr.append(shd)
    for i, ln in enumerate(lines):
        run = p.add_run(ln)
        set_run_font(run, size=9.5, mono=True, color=INK)
        if i < len(lines) - 1:
            run.add_break()


def add_table(doc, rows, widths):
    n_cols = len(rows[0])
    n_rows = len(rows)
    table = doc.add_table(rows=n_rows, cols=n_cols)
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    table.autofit = False
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            cell = table.cell(ri, ci)
            set_cell_margins(cell)
            p = cell.paragraphs[0]
            para_format(p, before=0, after=0, line=1.15)
            is_head = ri == 0
            add_inline(p, val, size=10, base_bold=is_head, color=(DARK_BLUE if is_head else BODY))
            if is_head:
                shade_cell(cell, HEADER_FILL)
    mark_header_row(table.rows[0])
    set_table_geometry(table, widths)
    return table


def parse_markdown(src):
    with open(src, encoding="utf-8") as f:
        raw = f.read().splitlines()
    blocks = []
    i = 0
    while i < len(raw):
        line = raw[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("```"):
            code = []
            i += 1
            while i < len(raw) and not raw[i].strip().startswith("```"):
                code.append(raw[i])
                i += 1
            i += 1
            blocks.append(("code", code))
            continue
        if stripped.startswith("# "):
            blocks.append(("title", stripped[2:].strip()))
            i += 1
            continue
        if stripped.startswith("## "):
            blocks.append(("h2", stripped[3:].strip()))
            i += 1
            continue
        if stripped.startswith("### "):
            blocks.append(("h3", stripped[4:].strip()))
            i += 1
            continue
        if stripped.startswith("|"):
            rows = []
            while i < len(raw) and raw[i].strip().startswith("|"):
                cells = [c.strip() for c in raw[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                blocks.append(("table", rows))
            continue
        if stripped.startswith("> "):
            quote = stripped[2:].strip()
            blocks.append(("quote", quote))
            i += 1
            continue
        if stripped.startswith("- "):
            blocks.append(("bullet", stripped[2:].strip()))
            i += 1
            continue
        if re.match(r"^\d+\.\s", stripped):
            blocks.append(("bullet", re.sub(r"^\d+\.\s", "", stripped)))
            i += 1
            continue
        blocks.append(("para", stripped))
        i += 1
    return blocks


def main():
    doc = Document()
    # page geometry: Letter, 1in margins
    sec = doc.sections[0]
    sec.page_width = Inches(8.5)
    sec.page_height = Inches(11)
    sec.left_margin = Inches(1)
    sec.right_margin = Inches(1)
    sec.top_margin = Inches(1)
    sec.bottom_margin = Inches(1)
    sec.header_distance = Inches(0.492)
    sec.footer_distance = Inches(0.492)

    # base Normal style
    normal = doc.styles["Normal"]
    normal.font.name = FONT_LATIN
    normal.font.size = Pt(11)
    normal.font.color.rgb = BODY
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    rfonts.set(qn("w:eastAsia"), FONT_CJK)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    # heading styles
    for name, size, color, before, after in (
        ("Heading 1", 16, BLUE, 18, 10),
        ("Heading 2", 13, BLUE, 14, 7),
        ("Heading 3", 12, DARK_BLUE, 10, 5),
    ):
        st = doc.styles[name]
        st.font.name = FONT_LATIN
        st.font.size = Pt(size)
        st.font.bold = True
        st.font.color.rgb = color
        rpr = st.element.get_or_add_rPr()
        rfonts = rpr.find(qn("w:rFonts"))
        if rfonts is None:
            rfonts = OxmlElement("w:rFonts")
            rpr.append(rfonts)
        rfonts.set(qn("w:eastAsia"), FONT_CJK)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)
        st.paragraph_format.line_spacing = 1.25

    # list styles spacing
    for lname in ("List Bullet",):
        try:
            lst = doc.styles[lname]
            lst.font.name = FONT_LATIN
            lst.font.size = Pt(11)
            lst.paragraph_format.space_after = Pt(4)
            lst.paragraph_format.line_spacing = 1.25
        except KeyError:
            pass

    # header: muted running label
    hp = sec.header.paragraphs[0]
    hp.text = ""
    hr = hp.add_run("判断推理链好坏的标准 · ClawTrack 四维框架适配版")
    set_run_font(hr, size=8.5, color=MUTED)
    hp.paragraph_format.space_after = Pt(0)
    # footer: right page number
    fp = sec.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = fp.add_run()
    fld1 = OxmlElement("w:fldChar")
    fld1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    fld2 = OxmlElement("w:fldChar")
    fld2.set(qn("w:fldCharType"), "end")
    run._r.append(fld1)
    run._r.append(instr)
    run._r.append(fld2)
    set_run_font(run, size=9, color=MUTED)

    blocks = parse_markdown(SRC)
    # table column presets by row count / header hint
    def widths_for(rows):
        n = len(rows[0])
        heads = [c.lower() for c in rows[0]]
        if n == 2:
            return [1.7, 4.8]
        if n == 3:
            if any("档" in h for h in heads):
                return [0.55, 2.55, 3.4]
            if any("怎么治" in h or "证据" in h for h in heads):
                return [2.0, 1.3, 3.2]
            if "版本" in "".join(heads) or "变体" in "".join(heads):
                return [1.7, 0.9, 3.9]
            return [2.4, 0.7, 3.4]
        if n == 4:
            return [1.7, 1.0, 1.9, 1.9]
        return [6.5 / n] * n

    for kind, payload in blocks:
        if kind == "title":
            p = doc.add_paragraph()
            para_format(p, before=0, after=4)
            add_inline(p, payload, size=20, base_bold=True, color=INK)
        elif kind == "h2":
            doc.add_heading(payload, level=1)
        elif kind == "h3":
            doc.add_heading(payload, level=2)
        elif kind == "para":
            if payload.startswith("日期：") or payload.startswith("---"):
                p = doc.add_paragraph()
                para_format(p, before=0, after=10)
                add_inline(p, payload, size=10, color=MUTED)
            else:
                add_body(doc, payload)
        elif kind == "bullet":
            add_bullet(doc, payload)
        elif kind == "quote":
            p = doc.add_paragraph()
            para_format(p, before=2, after=8)
            p.paragraph_format.left_indent = Inches(0.25)
            pPr = p._p.get_or_add_pPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), "F4F6F9")
            pPr.append(shd)
            add_inline(p, payload, size=10.5, color=INK)
        elif kind == "code":
            add_code_block(doc, payload)
        elif kind == "table":
            add_table(doc, payload, widths_for(payload))
            # breathing room after table
            sp = doc.add_paragraph()
            para_format(sp, before=0, after=2)
            sp.add_run("")

    doc.save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    main()
