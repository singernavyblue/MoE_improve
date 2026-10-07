import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const xlsxPath =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/第三批消融结果.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));
const sheet = workbook.worksheets.getItem("第三批消融结果");

sheet.getRange("A1:I1").merge();
sheet.getRange("A1").values = [["第三批消融实验 · GPQA test 198 题（更强裁判 / 扩大初始池 / 裁判上下文）"]];
sheet.getRange("A3:I3").values = [
  ["变体", "改动", "准确率", "严格子集准确率", "严格子集题数", "基线同子集准确率", "转对", "转错", "400 错误数"],
];
sheet.getRange("A4:I8").values = [
  ["基线 pairwise margin", "Prometheus 裁判 + top_k=3", 0.4141, null, null, null, null, null, 0],
  ["J2a：judge=mathstral（4096）", "换科学特化 7B 裁判", 0.4091, 0.4260, 169, 0.4142, 21, 19, 108],
  ["J2b：judge=mathstral（8192）", "同裁判，上下文 4096→8192", 0.3333, 0.3473, 167, 0.4251, 13, 26, 0],
  ["J1：judge=qwen", "换通用 7B 裁判", 0.3535, 0.3512, 168, null, 18, 26, 12],
  ["H1：top_k=6", "全模型参与（6 节点）", 0.3182, null, 0, null, null, null, 252],
];
sheet.getRange("A10:I10").merge();
sheet.getRange("A10").values = [
  ["注：J2b（8192）溢出归零但全链判断更差（-7.6pp），说明上下文不是瓶颈；H1 受 252 次上下文溢出污染且严格子集 n=0，非干净对照；基线同子集准确率 = 基线在该变体严格子集上的成绩，用于公平对比。"],
];

sheet.getRange("A1").format = { fill: "#1F4E79", font: { bold: true, color: "#FFFFFF", size: 14 } };
sheet.getRange("A3:I3").format = {
  fill: "#D9E2F3",
  font: { bold: true, color: "#1F4E79" },
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
};
sheet.getRange("A4:I8").format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
sheet.getRange("C4:C8").format.numberFormat = "0.00%";
sheet.getRange("D4:D8").format.numberFormat = "0.00%";
sheet.getRange("F4:F8").format.numberFormat = "0.00%";
sheet.getRange("E4:I8").format.numberFormat = "0";
sheet.getRange("A4:I4").format = { fill: "#F2F2F2", font: { bold: true } };
sheet.getRange("A6:I6").format = { fill: "#FCE4EC", font: { bold: true } };
sheet.getRange("A:A").format.columnWidth = 30;
sheet.getRange("B:B").format.columnWidth = 26;
sheet.getRange("C:F").format.columnWidth = 14;
sheet.getRange("G:I").format.columnWidth = 11;
sheet.getRange("A1").format.rowHeight = 30;

const check = await workbook.inspect({
  kind: "table",
  range: "A1:I10",
  include: "values",
  tableMaxRows: 14,
  tableMaxCols: 10,
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
await fs.writeFile(
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/preview_batch3.png",
  new Uint8Array(await blob.arrayBuffer())
);

const out = await SpreadsheetFile.exportXlsx(workbook);
await out.save(xlsxPath);
console.log("EXPORT_OK");
