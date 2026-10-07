#!/usr/bin/env python3
"""Create a PPT-ready xlsx for the per-question judge score spread."""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

OUT = "outputs/裁判分数区分度表.xlsx"

wb = Workbook()
ws = wb.active
ws.title = "分数区分度"

# Title
ws.merge_cells("A1:C1")
ws["A1"] = "按题分组：同一题 3 个节点裁判分数差（198 题）"
ws["A1"].font = Font(size=14, bold=True)
ws["A1"].alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[1].height = 30

# Header
headers = ["分数差", "题数", "占比"]
header_fill = PatternFill("solid", fgColor="4472C4")
header_font = Font(bold=True, color="FFFFFF", size=12)
for col, h in enumerate(headers, 1):
    c = ws.cell(row=2, column=col, value=h)
    c.fill = header_fill
    c.font = header_font
    c.alignment = Alignment(horizontal="center", vertical="center")
ws.row_dimensions[2].height = 24

rows = [
    ("0（完全相同）", 57, "28.8%"),
    ("≤1", 127, "64.1%"),
    ("≥2（有实质区分）", 31, "15.7%"),
]
thin = Side(style="thin", color="999999")
border = Border(left=thin, right=thin, top=thin, bottom=thin)
highlight = PatternFill("solid", fgColor="FCE4D6")
for r, row in enumerate(rows, 3):
    for col, v in enumerate(row, 1):
        c = ws.cell(row=r, column=col, value=v)
        c.border = border
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.font = Font(size=12)
        if r == 4:  # highlight the ≤1 row (key finding)
            c.fill = highlight
            c.font = Font(size=12, bold=True)
    ws.row_dimensions[r].height = 22

# Footnote
ws.merge_cells("A7:C7")
ws["A7"] = "28.8% 的题三节点同分，64.1% 的题分数差≤1——裁判在约 2/3 的题上无法区分链质量"
ws["A7"].font = Font(size=10, italic=True, color="808080")

ws.column_dimensions["A"].width = 24
ws.column_dimensions["B"].width = 12
ws.column_dimensions["C"].width = 12

wb.save(OUT)
print("saved", OUT)
