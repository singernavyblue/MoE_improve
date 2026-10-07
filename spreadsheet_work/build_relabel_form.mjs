import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";
import JSZip from "jszip";

const outputDir = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs";
const sample = JSON.parse(
  await fs.readFile("/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/gpqa_repo/复标样本_15题.json", "utf8"),
);

const workbook = Workbook.create();
const DARK = "#1F4E79";
const HEADER_FILL = "#D9E2F3";
const BORDER = "#D9D9D9";

// ============================================================
// Sheet 1: 复标题目（15 题，空白待填）
// ============================================================
const s = workbook.worksheets.add("复标题目_15");
s.showGridLines = false;
s.mergeCells("A1:Q1");
s.getRange("A1").values = [["独立复标：Q 矩阵一致性检验（15 题）"]];
s.mergeCells("A2:Q2");
s.getRange("A2").values = [[
  "操作：请先阅读“标定指南”页，然后独立为每题选主维（L 列）并填 D1–D4（1=需要该能力），备注（Q 列）填 M/I/MI；不要参考他人答案。",
]];

s.getRange("A4:Q4").values = [[
  "序号", "Record ID", "学科", "子域", "难度", "题目（题干）", "选项A", "选项B", "选项C", "选项D",
  "正确答案（文本）", "主维", "D1", "D2", "D3", "D4", "备注(M/I)",
]];

const rows = sample.map((o, i) => {
  const it = o.item;
  const opts = [it.correct, ...it.incorrect];
  return [
    i + 1, it.record_id, it.domain, it.subdomain, it.difficulty, it.question,
    opts[0], opts[1], opts[2], opts[3], it.correct, "", "", "", "", "", "",
  ];
});
s.getRange(`A5:Q${4 + 15}`).values = rows;

s.getRange(`L5:L${4 + 15}`).dataValidation = { rule: { type: "list", values: ["D1", "D2", "D3", "D4"] } };
s.getRange(`M5:P${4 + 15}`).dataValidation = { rule: { type: "list", values: ["0", "1"] } };
s.getRange(`Q5:Q${4 + 15}`).dataValidation = { rule: { type: "list", values: ["M", "I", "MI"] } };

s.getRange("A1").format = { fill: DARK, font: { bold: true, color: "#FFFFFF", size: 14 }, horizontalAlignment: "center", verticalAlignment: "center" };
s.getRange("A2").format = { font: { italic: true, color: "#595959", size: 10 }, wrapText: true, verticalAlignment: "center" };
s.getRange("A4:Q4").format = { fill: HEADER_FILL, font: { bold: true, color: DARK, size: 10 }, borders: { preset: "all", style: "thin", color: "#B4C6E7" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
s.getRange(`A5:Q${4 + 15}`).format = { borders: { preset: "all", style: "thin", color: BORDER }, verticalAlignment: "center" };
s.getRange(`A5:A${4 + 15}`).format = { horizontalAlignment: "center", font: { color: "#595959" } };
s.getRange(`C5:E${4 + 15}`).format = { horizontalAlignment: "center", font: { size: 9 } };
s.getRange(`F5:F${4 + 15}`).format = { wrapText: true, horizontalAlignment: "left", font: { size: 9 } };
s.getRange(`G5:K${4 + 15}`).format = { wrapText: true, horizontalAlignment: "left", font: { size: 9 } };
s.getRange(`L5:L${4 + 15}`).format = { horizontalAlignment: "center", font: { bold: true } };
s.getRange(`M5:P${4 + 15}`).format = { horizontalAlignment: "center" };
s.getRange(`Q5:Q${4 + 15}`).format = { horizontalAlignment: "center" };

s.getRange("A:A").format.columnWidth = 6;
s.getRange("B:B").format.columnWidth = 12;
s.getRange("C:C").format.columnWidth = 9;
s.getRange("D:D").format.columnWidth = 15;
s.getRange("E:E").format.columnWidth = 9;
s.getRange("F:F").format.columnWidth = 52;
s.getRange("G:J").format.columnWidth = 20;
s.getRange("K:K").format.columnWidth = 18;
s.getRange("L:L").format.columnWidth = 8;
s.getRange("M:P").format.columnWidth = 5.5;
s.getRange("Q:Q").format.columnWidth = 10;
s.getRange("A1").format.rowHeight = 32;
s.getRange("A2").format.rowHeight = 22;
s.getRange("A4").format.rowHeight = 30;
for (let r = 5; r <= 19; r++) {
  const q = s.getRange(`F${r}`).values[0][0] || "";
  s.getRange(`A${r}`).format.rowHeight = Math.min(120, 22 + Math.ceil(q.length / 26) * 13);
}

// ============================================================
// Sheet 2: 标定指南
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
g.getRange("A5:F5").values = [["维度", "一句话定义", "何时标 1（判断标准）", "典型题", "对应失败模式", "轴"]];
const dims = [
  ["D1 化学机理与分子推理", "调用化学领域知识解题（反应、结构、立体化学）", "题干/选项出现化合物、反应、试剂、产物、构型、化学键", "肉桂醛碳数题、产物结构题", "bad1、bad3", "学科知识轴"],
  ["D2 物理计算与定量推理", "靠数值计算、公式、量纲、单位换算得出答案", "题干给数值/公式/常数，解题必须算数", "能量、速率、比例计算题", "5.1 计算类转错", "学科知识轴"],
  ["D3 生物分子与机制", "调用分子生物学、遗传、生化通路知识", "涉及 DNA/RNA/蛋白/病毒/通路/代谢机制", "SARS-CoV-2 分子生物题", "bad2", "学科知识轴"],
  ["D4 推理与指令（联合维）", "多步推理过程 ＋ 回答契约理解（原 D4 多步演绎 + 原 D5 指令理解合并）", "解题需 ≥2 步推理/逐条排除/条件传递，或题含 except/not/incorrect/唯一/最接近等“回答契约”限定词", "逐条判断陈述、except 题、反应序列推产物", "bad2 分析对输出反、idx61 长链断链", "推理过程轴＋任务契约轴"],
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
  "① 每题恰好 1 个主维（必填）；② 次维最多 2 个；③ D4 只在 Q3 触发时标 1，不默认加；④ 主维对应的格子必须填 1；⑤ 备注列在标 D4 时填 M/I/MI，未标 D4 可留空。",
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
g.getRange("A12").format.rowHeight = 22;
for (let r = 13; r <= 15; r++) g.getRange(`A${r}`).format.rowHeight = 42;
g.getRange("A18").format.rowHeight = 52;
g.getRange("A24").format.rowHeight = 22;
g.getRange("A25:A26").format.rowHeight = 24;

// ============================================================
// Sheet 3: 计分说明
// ============================================================
const c = workbook.worksheets.add("计分说明");
c.showGridLines = false;
c.mergeCells("A1:E1");
c.getRange("A1").values = [["一致性检验 · 计分说明"]];
c.mergeCells("A2:E2");
c.getRange("A2").values = [[
  "目的：验证 Q 矩阵标定指南的可重复性。复标者独立完成 15 题标定后，与参考答案（由组织者保存，不随本表发放）比对。",
]];
c.mergeCells("A4:E4");
c.getRange("A4").values = [["一、一致性指标（全部按 15 题计）"]];
c.getRange("A5:E9").values = [
  ["指标", "定义", "判定标准", "示例", ""],
  ["主维一致率", "主维（L 列）相同的题数占比", "≥85% 通过", "15/15 = 100%", ""],
  ["维度向量一致率", "D1–D4 五元组完全相同的题数占比", "≥85% 通过", "13/15 = 86.7%", ""],
  ["备注子类型一致率", "备注 M/I/MI 相同的题数占比", "参考指标（可低于主维）", "11/15 = 73.3%", ""],
  ["Cohen's kappa", "主维分类一致性（校正随机一致）", "≥0.7 优", "1.0 = 完全一致", ""],
];
c.mergeCells("A11:E11");
c.getRange("A11").values = [["二、操作流程"]];
c.getRange("A12:E15").values = [
  ["① 独立完成", "不参考他人答案与既往标定，按“标定指南”逐题填写", "", "", ""],
  ["② 交回表格", "把“复标题目_15”页 L–Q 列填好后保存回传", "", "", ""],
  ["③ 组织者比对", "与参考答案比对，计算上述 4 个指标", "", "", ""],
  ["④ 分歧复盘", "不一致的题集中讨论，修订指南或重新标定", "", "", ""],
];
c.mergeCells("A17:E17");
c.getRange("A17").values = [["三、参考基线（组织者内部两轮自复核）"]];
c.getRange("A18:E19").values = [
  ["主维一致率", "维度向量一致率", "备注一致率", "Cohen's kappa", ""],
  ["15/15 = 100%", "15/15 = 100%", "15/15 = 100%", "1.000", ""],
];
c.getRange("A21:E21").values = [["说明：自复核仅作流程演示；组间一致性以同学实际复标结果为准。", "", "", "", ""]];

c.getRange("A1").format = { fill: DARK, font: { bold: true, color: "#FFFFFF", size: 14 }, horizontalAlignment: "center", verticalAlignment: "center" };
c.getRange("A2").format = { font: { italic: true, color: "#595959", size: 10 }, wrapText: true, verticalAlignment: "center" };
for (const r of ["A4", "A11", "A17"]) c.getRange(`${r}`).format = { fill: HEADER_FILL, font: { bold: true, color: DARK, size: 12 }, verticalAlignment: "center" };
c.getRange("A5:E9").format = { borders: { preset: "all", style: "thin", color: BORDER }, wrapText: true, verticalAlignment: "center" };
c.getRange("A5:E5").format = { fill: HEADER_FILL, font: { bold: true, color: DARK } };
c.getRange("A12:E15").format = { borders: { preset: "all", style: "thin", color: BORDER }, wrapText: true, verticalAlignment: "center" };
c.getRange("A12:E12").format = { fill: HEADER_FILL, font: { bold: true, color: DARK } };
c.getRange("A18:E19").format = { borders: { preset: "all", style: "thin", color: BORDER }, horizontalAlignment: "center", verticalAlignment: "center" };
c.getRange("A18:E18").format = { fill: HEADER_FILL, font: { bold: true, color: DARK } };
c.getRange("A21").format = { font: { italic: true, color: "#595959", size: 9 }, wrapText: true };
c.getRange("A:A").format.columnWidth = 22;
c.getRange("B:E").format.columnWidth = 24;
c.getRange("A1").format.rowHeight = 32;
c.getRange("A2").format.rowHeight = 30;
for (const r of ["A4", "A11", "A17"]) c.getRange(`${r}`).format.rowHeight = 24;
c.getRange("A5").format.rowHeight = 22;
for (let r = 6; r <= 9; r++) c.getRange(`A${r}`).format.rowHeight = 22;
c.getRange("A12").format.rowHeight = 22;
for (let r = 13; r <= 15; r++) c.getRange(`A${r}`).format.rowHeight = 26;
c.getRange("A18").format.rowHeight = 22;
c.getRange("A19").format.rowHeight = 20;

// ============================================================
const outPath = `${outputDir}/Q矩阵复标_15题_独立标定表.xlsx`;
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outPath);

const buf = await fs.readFile(outPath);
const zip = await JSZip.loadAsync(buf);
const sheet1Path = "xl/worksheets/sheet1.xml";
let xml = await zip.file(sheet1Path).async("string");
xml = xml.replace(
  '<x:sheetViews><x:sheetView showGridLines="0" workbookViewId="0" /></x:sheetViews>',
  '<x:sheetViews><x:sheetView showGridLines="0" workbookViewId="0">' +
    '<x:pane x:xSplit="2" x:ySplit="4" x:topLeftCell="C5" x:activePane="bottomRight" x:state="frozen"/>' +
    '<x:selection x:pane="bottomRight" x:activeCell="C5" x:sqref="C5"/>' +
    "</x:sheetView></x:sheetViews>",
);
zip.file(sheet1Path, xml);
const out = await zip.generateAsync({ type: "nodebuffer" });
await fs.writeFile(outPath, out);
console.log("saved:", outPath);
