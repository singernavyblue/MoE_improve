import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc";

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("第三批消融结果");
sheet.showGridLines = false;

sheet.getRange("A1:H1").merge();
sheet.getRange("A1").values = [["第三批消融实验 · GPQA test 198 题（更强裁判 / 扩大初始池）"]];
sheet.getRange("A3:H3").values = [
  ["变体", "改动", "准确率", "严格子集准确率", "严格子集题数", "转对", "转错", "400 错误数"],
];
sheet.getRange("A4:H7").values = [
  ["基线 pairwise margin", "Prometheus 裁判 + top_k=3", 0.4141, null, null, null, null, 0],
  ["J2：judge=mathstral", "换科学特化 7B 裁判", 0.4091, 0.4226, 168, 21, 19, 108],
  ["J1：judge=qwen", "换通用 7B 裁判", 0.3535, 0.3512, 168, 18, 26, 12],
  ["H1：top_k=6", "全模型参与（6 节点）", 0.3182, null, 0, null, null, 252],
];
sheet.getRange("A9:H9").merge();
sheet.getRange("A9").values = [
  ["注：H1 受 252 次上下文溢出错误污染且节点与基线全不一致（严格子集 n=0），非干净的池大小对照；J2 受 108 次裁判上下文溢出（mathstral 4096）影响，仍接近基线；J2 8192 重跑（33.33%）见总览表。"],
];

sheet.getRange("A1").format = { fill: "#1F4E79", font: { bold: true, color: "#FFFFFF", size: 14 } };
sheet.getRange("A3:H3").format = {
  fill: "#D9E2F3",
  font: { bold: true, color: "#1F4E79" },
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
};
sheet.getRange("A4:H7").format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
sheet.getRange("C4:C7").format.numberFormat = "0.00%";
sheet.getRange("D4:D7").format.numberFormat = "0.00%";
sheet.getRange("E4:H7").format.numberFormat = "0";
sheet.getRange("A4:H4").format = { fill: "#F2F2F2", font: { bold: true } };
sheet.getRange("A5:H5").format = { fill: "#E2EFDA", font: { bold: true } };
sheet.getRange("A:A").format.columnWidth = 26;
sheet.getRange("B:B").format.columnWidth = 24;
sheet.getRange("C:F").format.columnWidth = 14;
sheet.getRange("G:H").format.columnWidth = 12;
sheet.getRange("A1").format.rowHeight = 30;

const check = await workbook.inspect({
  kind: "table",
  range: "A1:H9",
  include: "values",
  tableMaxRows: 12,
  tableMaxCols: 9,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

const blob = await workbook.render({ sheetName: "第三批消融结果", autoCrop: "all", scale: 2, format: "png" });
await fs.writeFile(`${outputDir}/preview_batch3.png`, new Uint8Array(await blob.arrayBuffer()));

const out = await SpreadsheetFile.exportXlsx(workbook);
await out.save(`${outputDir}/第三批消融结果.xlsx`);
console.log("EXPORT_OK");
