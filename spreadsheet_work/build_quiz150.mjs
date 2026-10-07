import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";
import JSZip from "jszip";

const outputDir = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs";
const data = JSON.parse(
  await fs.readFile("/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/gpqa_repo/摸底题集_150.json", "utf8"),
);
const items = data.selected;
const labels = JSON.parse(
  await fs.readFile("/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/gpqa_repo/qmatrix_labels_150.json", "utf8"),
);
if (labels.length !== items.length) {
  throw new Error(`labels ${labels.length} != items ${items.length}`);
}

const workbook = Workbook.create();
const DARK = "#1F4E79";
const HEADER_FILL = "#D9E2F3";
const BORDER = "#D9D9D9";

// ============================================================
// Sheet 1: 摸底题集（150 题，D1–D4 待标定）
// ============================================================
const s = workbook.worksheets.add("摸底题集_150");
s.showGridLines = false;

s.mergeCells("A1:R1");
s.getRange("A1").values = [["GPQA 摸底题集（150 题）——Q 矩阵待标定（D1–D4，D4=推理与指令联合维）"]];
s.mergeCells("A2:R2");
s.getRange("A2").values = [[
  "来源：GPQA main（448）− Diamond 测试集（198）= 250 候选，按学科配额与难度分层抽出 150；与正式测试集零重叠。",
]];

s.getRange("A4:R4").values = [[
  "序号", "Record ID", "学科", "子域", "难度", "题目（题干）", "选项A", "选项B", "选项C", "选项D",
  "正确答案（文本）", "主维", "D1", "D2", "D3", "D4", "校验", "备注",
]];

const rows = items.map((it, i) => {
  const opts = [it.correct, ...it.incorrect];
  const lab = labels[i];
  return [
    i + 1,
    it.record_id,
    it.domain,
    it.subdomain,
    it.difficulty,
    it.question,
    opts[0],
    opts[1],
    opts[2],
    opts[3],
    it.correct,
    lab[0],
    lab[1],
    lab[2],
    lab[3],
    lab[4],
    "",
    lab[5] || "",
  ];
});
s.getRange(`A5:R${4 + 150}`).values = rows;

const checkFormula = Array.from({ length: 150 }, (_, i) => {
  const r = 5 + i;
  return [`=IF($L${r}="","请先填主维",IF(COUNTIF($M${r}:$P${r},1)=0,"请标维度",IF(COUNTIF($M${r}:$P${r},1)>3,"总维度>3",IF(IF($L${r}="D1",$M${r},IF($L${r}="D2",$N${r},IF($L${r}="D3",$O${r},$P${r})))<>1,"主维未标1","OK"))))`];
});
s.getRange(`Q5:Q${4 + 150}`).formulas = checkFormula;

s.getRange(`L5:L${4 + 150}`).dataValidation = { rule: { type: "list", values: ["D1", "D2", "D3", "D4"] } };
s.getRange(`M5:P${4 + 150}`).dataValidation = { rule: { type: "list", values: ["0", "1"] } };
s.getRange(`Q5:Q${4 + 150}`).conditionalFormats.add("containsText", { text: "OK", format: { fill: "#E2EFDA", font: { color: "#375623", bold: true } } });
s.getRange(`Q5:Q${4 + 150}`).conditionalFormats.addCustom(`=AND($Q5<>"",$Q5<>"OK")`, { fill: "#FCE4E4", font: { color: "#9C1C1C" } });

// ---- 样式 ----
s.getRange("A1").format = { fill: DARK, font: { bold: true, color: "#FFFFFF", size: 14 }, horizontalAlignment: "center", verticalAlignment: "center" };
s.getRange("A2").format = { font: { italic: true, color: "#595959", size: 10 }, wrapText: true, verticalAlignment: "center" };
s.getRange("A4:R4").format = { fill: HEADER_FILL, font: { bold: true, color: DARK, size: 10 }, borders: { preset: "all", style: "thin", color: "#B4C6E7" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
s.getRange(`A5:R${4 + 150}`).format = { borders: { preset: "all", style: "thin", color: BORDER }, verticalAlignment: "center" };
s.getRange(`A5:A${4 + 150}`).format = { horizontalAlignment: "center", font: { color: "#595959" } };
s.getRange(`C5:E${4 + 150}`).format = { horizontalAlignment: "center", font: { size: 9 } };
s.getRange(`F5:F${4 + 150}`).format = { wrapText: true, horizontalAlignment: "left", font: { size: 9 } };
s.getRange(`G5:K${4 + 150}`).format = { wrapText: true, horizontalAlignment: "left", font: { size: 9 } };
s.getRange(`L5:L${4 + 150}`).format = { horizontalAlignment: "center", font: { bold: true } };
s.getRange(`M5:P${4 + 150}`).format = { horizontalAlignment: "center" };
s.getRange(`Q5:Q${4 + 150}`).format = { horizontalAlignment: "center" };
s.getRange(`R5:R${4 + 150}`).format = { horizontalAlignment: "center", font: { color: "#7A5A00", size: 9 } };

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
s.getRange("Q:Q").format.columnWidth = 12;
s.getRange("R:R").format.columnWidth = 12;
s.getRange("A1").format.rowHeight = 32;
s.getRange("A2").format.rowHeight = 22;
s.getRange("A4").format.rowHeight = 30;
for (let r = 5; r <= 154; r++) {
  const q = s.getRange(`F${r}`).values[0][0] || "";
  s.getRange(`A${r}`).format.rowHeight = Math.min(120, 22 + Math.ceil(q.length / 26) * 13);
}

const sRow = 157;
s.mergeCells(`A${sRow}:R${sRow}`);
s.getRange(`A${sRow}`).values = [["标定进度统计（每维目标 ≥30）"]];
s.getRange(`A${sRow + 1}:R${sRow + 1}`).values = [["指标", "D1", "D2", "D3", "D4", "", "", "", "", "", "", "", "", "", "", "", "校验通过数", ""]];
s.getRange(`A${sRow + 2}:R${sRow + 2}`).formulas = [
  ["标1题数", `=COUNTIF($M$5:$M$154,1)`, `=COUNTIF($N$5:$N$154,1)`, `=COUNTIF($O$5:$O$154,1)`, `=COUNTIF($P$5:$P$154,1)`, "", "", "", "", "", "", "", "", "", "", "", `=COUNTIF($Q$5:$Q$154,"OK")`, ""],
];
s.getRange(`A${sRow + 3}:R${sRow + 3}`).formulas = [
  ["主维数", `=COUNTIF($L$5:$L$154,"D1")`, `=COUNTIF($L$5:$L$154,"D2")`, `=COUNTIF($L$5:$L$154,"D3")`, `=COUNTIF($L$5:$L$154,"D4")`, "", "", "", "", "", "", "", "", "", "", "", "", ""],
];
s.getRange(`A${sRow + 2}`).values = [["标1题数"]];
s.getRange(`A${sRow + 3}`).values = [["主维数"]];
s.getRange(`A${sRow}`).format = { fill: HEADER_FILL, font: { bold: true, color: DARK, size: 11 }, verticalAlignment: "center" };
s.getRange(`A${sRow + 1}`).format = { fill: HEADER_FILL, font: { bold: true, color: DARK }, borders: { preset: "all", style: "thin", color: "#B4C6E7" }, horizontalAlignment: "center" };
s.getRange(`A${sRow + 2}:R${sRow + 3}`).format = { borders: { preset: "all", style: "thin", color: BORDER }, horizontalAlignment: "center" };
s.getRange(`A${sRow}`).format.rowHeight = 24;
s.getRange(`A${sRow + 1}`).format.rowHeight = 22;

// ============================================================
// Sheet 2: 选样说明
// ============================================================
const m = workbook.worksheets.add("选样说明");
m.showGridLines = false;
m.mergeCells("A1:F1");
m.getRange("A1").values = [["摸底题集选样说明"]];
m.mergeCells("A2:F2");
m.getRange("A2").values = [[
  "目的：从 GPQA main（448 题）中剔除正式测试的 Diamond 198 题后，从剩余 250 题中选出 150 道作摸底题，构建 Q 矩阵与能力画像。",
]];
m.mergeCells("A4:F4");
m.getRange("A4").values = [["一、选样结果"]];
m.getRange("A5:F8").values = [
  ["学科", "候选池（250）", "选中（150）", "占比", "", ""],
  ["chemistry", 90, 54, "=C6/B6", "", ""],
  ["physics", 101, 61, "=C7/B7", "", ""],
  ["biology", 59, 35, "=C8/B8", "", ""],
];
m.getRange("A9:F9").values = [["合计", 250, 150, "=C9/B9", "", ""]];
m.getRange("A11:F11").values = [["难度分布（选中）：undergrad 77 / grad 53 / postgrad 20", "", "", "", "", ""]];
m.getRange("A12:F12").values = [["维度合并说明：D5（指令理解）已并入 D4（推理与指令联合维）；指令型题全池仅 5 道，已全部纳入并在备注列标“指令型(D4)”。", "", "", "", "", ""]];

m.mergeCells("A14:F14");
m.getRange("A14").values = [["二、防泄漏说明"]];
m.getRange("A15:F17").values = [
  ["核对项", "结果", "", "", "", ""],
  ["本地 198 题 ↔ 官方 Diamond", "198/198 全部匹配（含修订前文本 90 题）", "", "", "", ""],
  ["摸底 150 题 ∩ 测试 198 题", "零重叠（Record ID 校验 + 文本相似度 >0.9 复查）", "", "", "", ""],
];

m.mergeCells("A19:F19");
m.getRange("A19").values = [["三、使用说明"]];
m.getRange("A20:F22").values = [
  ["① 在“摸底题集_150”页逐行标定：先选主维（L 列），再填 D1–D4（1=需要该能力）；校验列自动检查。", "", "", "", "", ""],
  ["② 选项 A–D 为资料原始顺序（A=官方正确项文本），正式跑模型时须重新随机打乱选项顺序，避免位置偏差。", "", "", "", "", ""],
  ["③ D4 为联合维：备注列记录 M（多步）/ I（指令）/ MI（两者），供事后细分分析；IRT 按 D1–D4 四维拟合。", "", "", "", "", ""],
];

m.getRange("A1").format = { fill: DARK, font: { bold: true, color: "#FFFFFF", size: 14 }, horizontalAlignment: "center", verticalAlignment: "center" };
m.getRange("A2").format = { font: { italic: true, color: "#595959", size: 10 }, wrapText: true, verticalAlignment: "center" };
for (const r of ["A4", "A14", "A19"]) m.getRange(`${r}`).format = { fill: HEADER_FILL, font: { bold: true, color: DARK, size: 12 }, verticalAlignment: "center" };
m.getRange("A5:F9").format = { borders: { preset: "all", style: "thin", color: BORDER }, horizontalAlignment: "center", verticalAlignment: "center" };
m.getRange("A5:F5").format = { fill: HEADER_FILL, font: { bold: true, color: DARK } };
m.getRange("A15:F17").format = { borders: { preset: "all", style: "thin", color: BORDER }, verticalAlignment: "center", wrapText: true };
m.getRange("A15:F15").format = { fill: HEADER_FILL, font: { bold: true, color: DARK } };
m.getRange("A20:F22").format = { wrapText: true, verticalAlignment: "top" };
m.getRange("B6:C9").format.numberFormat = "0";
m.getRange("D6:D9").format.numberFormat = "0.0%";
m.getRange("A:A").format.columnWidth = 14;
m.getRange("B:E").format.columnWidth = 16;
m.getRange("F:F").format.columnWidth = 46;
m.getRange("A1").format.rowHeight = 32;
m.getRange("A2").format.rowHeight = 30;
for (const r of ["A4", "A14", "A19"]) m.getRange(`${r}`).format.rowHeight = 24;
m.getRange("A5").format.rowHeight = 22;
for (let r = 6; r <= 9; r++) m.getRange(`A${r}`).format.rowHeight = 20;
m.getRange("A11:A12").format.rowHeight = 28;
m.getRange("A15").format.rowHeight = 22;
for (let r = 16; r <= 17; r++) m.getRange(`A${r}`).format.rowHeight = 28;
m.getRange("A20:A22").format.rowHeight = 30;

// ============================================================
// Sheet 3: 标定指南（4 维）
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
const outPath = `${outputDir}/摸底题集_150题_待标定Q矩阵.xlsx`;
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
