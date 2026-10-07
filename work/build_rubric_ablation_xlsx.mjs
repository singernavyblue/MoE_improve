import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const OUT = "outputs/裁判方式对比表.xlsx";

const INK = "#0B2545";
const HEADER_FILL = "#E8EEF5";
const GOOD_FILL = "#E3F2E4";
const BAD_FILL = "#FBE9E7";
const BORDER = "#C7D3E0";

const wb = Workbook.create();
const s = wb.worksheets.add("裁判方式对比");

// base styling
s.getRange("A1:C40").format.font = { name: "Calibri", size: 11, color: "#1A1A1A" };
s.getRange("A1:C40").format.wrapText = true;
s.getRange("A1:C40").format.verticalAlignment = "top";
s.getRange("A1:A40").format.columnWidth = 28;
s.getRange("B1:B40").format.columnWidth = 16;
s.getRange("C1:C40").format.columnWidth = 44;

// title band
const t = s.getRange("A1:C1");
t.merge();
t.values = [["无 gold 裁判方式对比（全量 198 题 GPQA）"]];
t.format.fill = INK;
t.format.font = { color: "#FFFFFF", bold: true, size: 14 };
t.format.rowHeight = 28;
t.format.verticalAlignment = "center";

const m = s.getRange("A2:C2");
m.merge();
m.values = [["配置：6 模型 ｜ top_k=3 ｜ mean 池化 ｜ rounds=1 ｜ seed=0 ｜ 无标准答案（no gold）"]];
m.format.font = { size: 10, color: "#4A5A6A" };
m.format.rowHeight = 18;

// header
const h = s.getRange("A4:C4");
h.values = [["变体", "全量 198", "说明"]];
h.format.fill = HEADER_FILL;
h.format.font = { bold: true, color: INK };
h.format.horizontalAlignment = "center";
h.format.verticalAlignment = "center";
h.format.borders = { preset: "all", style: "thin", color: BORDER };
h.format.rowHeight = 22;

const rows = [
  ["绝对打分 7B + 单条 rubric", "32.32%（64）", "7B Prometheus 绝对打分（无 gold），单条 1~5 rubric"],
  ["绝对打分 7B + 四维 rubric", "37.88%（75）", "同配置仅换 rubric 为四维标准（严格控制变量，+5.56pp）"],
  ["显式四维分数 + DeepSeek", "38.38%（76）", "DeepSeek 输出四维 JSON 分数，公式合成边权重"],
  ["pairwise margin 7B（当前基线）", "41.41%（82）", "幅度加权 pairwise 比较（无 gold），当前最高"],
];

rows.forEach((r, i) => {
  const rr = 5 + i;
  const range = s.getRange(`A${rr}:C${rr}`);
  range.values = [r];
  range.format.borders = { preset: "all", style: "thin", color: BORDER };
  range.format.font = { size: 10, color: "#1A1A1A" };
  range.format.verticalAlignment = "top";
  range.format.rowHeight = 30;
  const a = s.getRange(`A${rr}`);
  a.format.verticalAlignment = "center";
  const b = s.getRange(`B${rr}`);
  b.format.horizontalAlignment = "center";
  b.format.verticalAlignment = "center";
  b.format.font = { size: 11, bold: true, color: INK };
  if (i === 1) range.format.fill = "#FFF3D6";       // +5.56pp highlight
  if (i === 3) range.format.fill = GOOD_FILL;        // best row
});

const n = s.getRange("A10:C10");
n.merge();
n.values = [["结论：四维标准在严格控制变量下有效（+5.56pp）；但打分方式的影响更大——pairwise 幅度比较（41.41%）仍高于所有绝对打分变体。"]];
n.format.fill = "#F4F6F9";
n.format.font = { size: 10, color: "#0B2545" };
n.format.borders = { preset: "all", style: "thin", color: BORDER };
n.format.rowHeight = 34;

await fs.mkdir("outputs", { recursive: true });
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(OUT);
console.log("saved", OUT);
