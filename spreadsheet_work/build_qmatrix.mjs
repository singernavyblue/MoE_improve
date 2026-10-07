import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";
import JSZip from "jszip";

const outputDir = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs";
await fs.mkdir(outputDir, { recursive: true });

const workbook = Workbook.create();
const DARK = "#1F4E79";
const HEADER_FILL = "#D9E2F3";
const BORDER = "#D9D9D9";

// ============================================================
// Sheet 1: 标定指南（4 维）
// ============================================================
const g = workbook.worksheets.add("标定指南");
g.showGridLines = false;

g.mergeCells("A1:F1");
g.getRange("A1").values = [["Q 矩阵标定指南 —— 4 个能力维度定义与 3 问决策清单"]];
g.mergeCells("A2:F2");
g.getRange("A2").values = [[
  "用途：给每道摸底题标注它考哪些能力维度，形成 Q 矩阵（题 × 维度，1=需要该能力）。D4 为“推理与指令”联合维。",
]];

g.mergeCells("A4:F4");
g.getRange("A4").values = [["一、4 个能力维度定义"]];
g.getRange("A5:F5").values = [
  ["维度", "一句话定义", "何时标 1（判断标准）", "典型题", "对应失败模式", "轴"],
];
const dims = [
  [
    "D1 化学机理与分子推理",
    "调用化学领域知识解题（反应、结构、立体化学）",
    "题干/选项出现化合物、反应、试剂、产物、构型、化学键",
    "肉桂醛碳数题、产物结构题",
    "bad1、bad3",
    "学科知识轴",
  ],
  [
    "D2 物理计算与定量推理",
    "靠数值计算、公式、量纲、单位换算得出答案",
    "题干给数值/公式/常数，解题必须算数",
    "能量、速率、比例计算题",
    "5.1 计算类转错",
    "学科知识轴",
  ],
  [
    "D3 生物分子与机制",
    "调用分子生物学、遗传、生化通路知识",
    "涉及 DNA/RNA/蛋白/病毒/通路/代谢机制",
    "SARS-CoV-2 分子生物题",
    "bad2",
    "学科知识轴",
  ],
  [
    "D4 推理与指令（联合维）",
    "多步推理过程 ＋ 回答契约理解（原 D4 多步演绎 + 原 D5 指令理解合并）",
    "解题需 ≥2 步推理/逐条排除/条件传递，**或** 题含 except/not/incorrect/唯一/最接近等“回答契约”限定词",
    "逐条判断陈述、except 题、反应序列推产物",
    "bad2 分析对输出反、idx61 长链断链",
    "推理过程轴＋任务契约轴",
  ],
];
g.getRange("A6:F9").values = dims;

g.mergeCells("A11:F11");
g.getRange("A11").values = [["二、标定一道题的 3 问决策清单（按顺序问）"]];
g.getRange("A12:F12").values = [["顺序", "问题", "是 → 加标", "否 → 跳过", "", ""]];
g.getRange("A13:F15").values = [
  ["Q1", "这道题主要靠哪个学科知识？", "化学→D1 / 物理→D2 / 生物→D3（必选一个主维）", "不可能为否", "", ""],
  ["Q2", "解题必须做数值计算/量纲/公式吗？", "加标 D2", "跳过", "", ""],
  ["Q3", "需要 ≥2 步推理/逐条排除/条件传递，或题含 except/not/incorrect/唯一/最接近等回答契约限定词吗？", "加标 D4（备注记 M=多步 / I=指令 / MI=两者）", "跳过", "", ""],
];

g.mergeCells("A17:F17");
g.getRange("A17").values = [["三、填写规则与裁决"]];
g.mergeCells("A18:F18");
g.getRange("A18").values = [[
  "① 每题恰好 1 个主维（必填）；② 次维最多 2 个；③ D4 只在 Q3 触发时标 1，不默认加；④ 主维对应的格子必须填 1；⑤ “校验”列自动检查，全部为 OK 才算标定完成。",
]];
const rulings = [
  "裁决 1｜纯计算题不标 D4：算术/数值步骤归 D2；D4 只标“推理/判断型”多步或回答契约。",
  "裁决 2｜主维按学科知识定，数值计算只作次维加标（如 pH 题主维 = D1 化学，即使大量算数）。",
  "裁决 3｜D4 为“推理或指令”联合维：多步推理（≥2 步/逐条排除/条件传递）或回答契约限定词（except/not/incorrect/唯一/最接近）任一触发即标 1；化学术语（如 exo/endo）不触发；备注列记 M/I/MI 子类型。",
];
for (let i = 0; i < 3; i++) {
  const r = 19 + i;
  g.mergeCells(`A${r}:F${r}`);
  g.getRange(`A${r}`).values = [[rulings[i]]];
}

g.mergeCells("A23:F23");
g.getRange("A23").values = [["四、示例"]];
g.getRange("A24:F27").values = [
  ["示例", "主维", "D1", "D2", "D3", "D4"],
  ["肉桂醛碳数题", "D1", 1, 0, 0, 1],
  ["SARS except 题", "D3", 0, 0, 1, 1],
  ["纯计算题（π→μν 动能）", "D2", 0, 1, 0, 0],
];

// ---- 样式 ----
g.getRange("A1").format = { fill: DARK, font: { bold: true, color: "#FFFFFF", size: 14 }, horizontalAlignment: "center", verticalAlignment: "center" };
g.getRange("A2").format = { font: { italic: true, color: "#595959", size: 10 }, wrapText: true, verticalAlignment: "center" };
for (const r of ["A4", "A11", "A17", "A23"]) g.getRange(`${r}`).format = { fill: HEADER_FILL, font: { bold: true, color: DARK, size: 12 }, verticalAlignment: "center" };
g.getRange("A5:F5").format = { fill: HEADER_FILL, font: { bold: true, color: DARK }, borders: { preset: "all", style: "thin", color: "#B4C6E7" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
g.getRange("A6:F9").format = { borders: { preset: "all", style: "thin", color: BORDER }, wrapText: true, verticalAlignment: "center" };
g.getRange("A6:A9").format = { font: { bold: true, color: DARK } };
g.getRange("A12:F12").format = { fill: HEADER_FILL, font: { bold: true, color: DARK }, borders: { preset: "all", style: "thin", color: "#B4C6E7" }, horizontalAlignment: "center", verticalAlignment: "center" };
g.getRange("A13:F15").format = { borders: { preset: "all", style: "thin", color: BORDER }, wrapText: true, verticalAlignment: "center" };
g.getRange("A13:A15").format = { font: { bold: true, color: DARK }, horizontalAlignment: "center" };
g.getRange("A18").format = { wrapText: true, verticalAlignment: "top" };
for (let i = 0; i < 3; i++) {
  const r = 19 + i;
  g.getRange(`A${r}:F${r}`).format = { fill: "#FBF3E2", font: { color: "#7A5A00", size: 10 }, borders: { preset: "all", style: "thin", color: "#E5D5A8" }, wrapText: true, verticalAlignment: "center", horizontalAlignment: "left" };
  g.getRange(`A${r}`).format.rowHeight = 32;
}
g.getRange("A24:F26").format = { borders: { preset: "all", style: "thin", color: BORDER }, horizontalAlignment: "center", verticalAlignment: "center" };
g.getRange("A24:F24").format = { fill: HEADER_FILL, font: { bold: true, color: DARK }, borders: { preset: "all", style: "thin", color: "#B4C6E7" } };

g.getRange("A:A").format.columnWidth = 22;
g.getRange("B:C").format.columnWidth = 38;
g.getRange("D:F").format.columnWidth = 26;
g.getRange("A1").format.rowHeight = 32;
g.getRange("A2").format.rowHeight = 22;
for (const r of ["A4", "A11", "A17", "A23"]) g.getRange(`${r}`).format.rowHeight = 24;
g.getRange("A5").format.rowHeight = 26;
for (let r = 6; r <= 9; r++) g.getRange(`A${r}`).format.rowHeight = 60;
g.getRange("A11").format.rowHeight = 24;
g.getRange("A12").format.rowHeight = 22;
for (let r = 13; r <= 15; r++) g.getRange(`A${r}`).format.rowHeight = 42;
g.getRange("A18").format.rowHeight = 52;
g.getRange("A23").format.rowHeight = 24;
g.getRange("A24").format.rowHeight = 22;
g.getRange("A25:A26").format.rowHeight = 24;

// ============================================================
// Sheet 2: Q 矩阵（150 题 × D1–D4）
// ============================================================
const q = workbook.worksheets.add("Q 矩阵");
q.showGridLines = false;

q.mergeCells("A1:J1");
q.getRange("A1").values = [["Q 矩阵 —— 摸底题 × 能力维度（150 题，D4 = 推理与指令联合维）"]];
q.mergeCells("A2:J2");
q.getRange("A2").values = [[
  "填法：每行先选“主维”（下拉 D1–D4），再在 D1–D4 列填 1（需要该能力）或 0（不需要）；“校验”列自动检查。",
]];

q.getRange("A4:J4").values = [
  ["序号", "题目 ID/来源", "题目文本（可粘贴）", "主维", "D1", "D2", "D3", "D4", "校验", "备注(M/I)"],
];

const n = 150;
q.getRange(`A5:A${4 + n}`).values = Array.from({ length: n }, (_, i) => [i + 1]);
q.getRange(`B5:J${4 + n}`).values = Array.from({ length: n }, () => ["", "", "", "", "", "", "", "", ""]);

const checkFormula = Array.from({ length: n }, (_, i) => {
  const r = 5 + i;
  return [`=IF($D${r}="","请先填主维",IF(COUNTIF($E${r}:$H${r},1)=0,"请标维度",IF(COUNTIF($E${r}:$H${r},1)>3,"总维度>3",IF(IF($D${r}="D1",$E${r},IF($D${r}="D2",$F${r},IF($D${r}="D3",$G${r},$H${r})))<>1,"主维未标1","OK"))))`];
});
q.getRange(`I5:I${4 + n}`).formulas = checkFormula;

q.getRange(`D5:D${4 + n}`).dataValidation = { rule: { type: "list", values: ["D1", "D2", "D3", "D4"] } };
q.getRange(`E5:H${4 + n}`).dataValidation = { rule: { type: "list", values: ["0", "1"] } };
q.getRange(`I5:I${4 + n}`).conditionalFormats.add("containsText", { text: "OK", format: { fill: "#E2EFDA", font: { color: "#375623", bold: true } } });
q.getRange(`I5:I${4 + n}`).conditionalFormats.addCustom(`=AND($I5<>"",$I5<>"OK")`, { fill: "#FCE4E4", font: { color: "#9C1C1C" } });

q.getRange("A1").format = { fill: DARK, font: { bold: true, color: "#FFFFFF", size: 14 }, horizontalAlignment: "center", verticalAlignment: "center" };
q.getRange("A2").format = { font: { italic: true, color: "#595959", size: 10 }, wrapText: true, verticalAlignment: "center" };
q.getRange("A4:J4").format = { fill: HEADER_FILL, font: { bold: true, color: DARK }, borders: { preset: "all", style: "thin", color: "#B4C6E7" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
q.getRange(`A5:J${4 + n}`).format = { borders: { preset: "all", style: "thin", color: BORDER }, verticalAlignment: "center" };
q.getRange(`A5:A${4 + n}`).format = { horizontalAlignment: "center", font: { color: "#595959" } };
q.getRange(`D5:H${4 + n}`).format = { horizontalAlignment: "center" };
q.getRange(`C5:C${4 + n}`).format = { wrapText: true, horizontalAlignment: "left" };
q.getRange(`I5:I${4 + n}`).format = { horizontalAlignment: "center" };

q.getRange("A:A").format.columnWidth = 7;
q.getRange("B:B").format.columnWidth = 14;
q.getRange("C:C").format.columnWidth = 56;
q.getRange("D:D").format.columnWidth = 9;
q.getRange("E:H").format.columnWidth = 6;
q.getRange("I:I").format.columnWidth = 14;
q.getRange("J:J").format.columnWidth = 14;
q.getRange("A1").format.rowHeight = 32;
q.getRange("A2").format.rowHeight = 22;
q.getRange("A4").format.rowHeight = 26;
q.getRange(`A5:A${4 + n}`).format.rowHeight = 20;

const sRow = 4 + n + 3;
q.mergeCells(`A${sRow}:J${sRow}`);
q.getRange(`A${sRow}`).values = [["每维题量统计（目标：每维 ≥30）与标定进度"]];
q.getRange(`A${sRow + 1}:J${sRow + 1}`).values = [["指标", "D1", "D2", "D3", "D4", "", "", "校验通过数", "总题数", ""]];
q.getRange(`A${sRow + 2}:J${sRow + 2}`).formulas = [
  ["标1题数", `=COUNTIF($E$5:$E$${4 + n},1)`, `=COUNTIF($F$5:$F$${4 + n},1)`, `=COUNTIF($G$5:$G$${4 + n},1)`, `=COUNTIF($H$5:$H$${4 + n},1)`, "", "", `=COUNTIF($I$5:$I$${4 + n},"OK")`, `=${n}`, ""],
];
q.getRange(`A${sRow + 3}:J${sRow + 3}`).formulas = [
  ["主维数", `=COUNTIF($D$5:$D$${4 + n},"D1")`, `=COUNTIF($D$5:$D$${4 + n},"D2")`, `=COUNTIF($D$5:$D$${4 + n},"D3")`, `=COUNTIF($D$5:$D$${4 + n},"D4")`, "", "", "", "", ""],
];
q.getRange(`A${sRow + 2}`).values = [["标1题数"]];
q.getRange(`A${sRow + 3}`).values = [["主维数"]];
q.getRange(`A${sRow}`).format = { fill: HEADER_FILL, font: { bold: true, color: DARK, size: 11 }, verticalAlignment: "center" };
q.getRange(`A${sRow + 1}`).format = { fill: HEADER_FILL, font: { bold: true, color: DARK }, borders: { preset: "all", style: "thin", color: "#B4C6E7" }, horizontalAlignment: "center" };
q.getRange(`A${sRow + 2}:J${sRow + 3}`).format = { borders: { preset: "all", style: "thin", color: BORDER }, horizontalAlignment: "center" };
q.getRange(`A${sRow}`).format.rowHeight = 24;
q.getRange(`A${sRow + 1}`).format.rowHeight = 22;

const outPath = `${outputDir}/Q矩阵标定模板_150题.xlsx`;
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outPath);

const buf = await fs.readFile(outPath);
const zip = await JSZip.loadAsync(buf);
const sheet2Path = "xl/worksheets/sheet2.xml";
let xml = await zip.file(sheet2Path).async("string");
xml = xml.replace(
  '<x:sheetViews><x:sheetView showGridLines="0" workbookViewId="0" /></x:sheetViews>',
  '<x:sheetViews><x:sheetView showGridLines="0" workbookViewId="0">' +
    '<x:pane x:xSplit="3" x:ySplit="4" x:topLeftCell="D5" x:activePane="bottomRight" x:state="frozen"/>' +
    '<x:selection x:pane="bottomRight" x:activeCell="D5" x:sqref="D5"/>' +
    "</x:sheetView></x:sheetViews>",
);
zip.file(sheet2Path, xml);
const out = await zip.generateAsync({ type: "nodebuffer" });
await fs.writeFile(outPath, out);
console.log("saved:", outPath);
