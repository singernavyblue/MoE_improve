import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc";

const workbook = Workbook.create();
const sheet = workbook.worksheets.add("第二批消融结果");
sheet.showGridLines = false;

sheet.getRange("A1:G1").merge();
sheet.getRange("A1").values = [["第二批消融实验 · GPQA test 198 题（对照基线 pairwise margin 41.41%）"]];
sheet.getRange("A3:G3").values = [
  ["变体", "改动", "准确率", "严格子集准确率", "严格子集题数", "转对", "转错"],
];
sheet.getRange("A4:G7").values = [
  ["D：投票池化", "措施7", 0.3232, 0.3256, 172, 14, 31],
  ["E：exp 加权池化", "措施2", 0.3838, 0.3864, 176, 16, 19],
  ["F：不对称可信度 R=2", "措施1", 0.3535, 0.3471, 170, 16, 22],
  ["G：可信度 R=2 + exp", "措施1+2", 0.3687, 0.3846, 169, 11, 19],
];
sheet.getRange("A9:G9").merge();
sheet.getRange("A9").values = [
  ["注：所有变体均未超过基线（41.41%）；E（exp 加权）为单变量中最佳；严格子集 = 与基线节点构成一致的题目子集。"],
];

sheet.getRange("A1").format = { fill: "#1F4E79", font: { bold: true, color: "#FFFFFF", size: 14 } };
sheet.getRange("A3:G3").format = {
  fill: "#D9E2F3",
  font: { bold: true, color: "#1F4E79" },
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
};
sheet.getRange("A4:G7").format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
sheet.getRange("C4:C7").format.numberFormat = "0.00%";
sheet.getRange("D4:D7").format.numberFormat = "0.00%";
sheet.getRange("E4:G7").format.numberFormat = "0";
sheet.getRange("A5:G5").format = { fill: "#E2EFDA", font: { bold: true } };
sheet.getRange("A:A").format.columnWidth = 26;
sheet.getRange("B:B").format.columnWidth = 12;
sheet.getRange("C:E").format.columnWidth = 16;
sheet.getRange("F:G").format.columnWidth = 10;
sheet.getRange("A1").format.rowHeight = 30;

const check = await workbook.inspect({
  kind: "table",
  range: "A1:G9",
  include: "values",
  tableMaxRows: 12,
  tableMaxCols: 8,
});
console.log(check.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 50 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

const blob = await workbook.render({ sheetName: "第二批消融结果", autoCrop: "all", scale: 2, format: "png" });
await fs.writeFile(`${outputDir}/preview_batch2.png`, new Uint8Array(await blob.arrayBuffer()));

const out = await SpreadsheetFile.exportXlsx(workbook);
await out.save(`${outputDir}/第二批消融结果.xlsx`);
console.log("EXPORT_OK");
