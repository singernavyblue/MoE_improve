import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const xlsxPath =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/第二批消融结果.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));
const sheet = workbook.worksheets.getItem("第二批消融结果");

// Rewrite table with baseline row included (rows 4-8)
sheet.getRange("A3:G8").values = [
  ["变体", "改动", "准确率", "严格子集准确率", "严格子集题数", "转对", "转错"],
  ["基线 pairwise margin", "无", 0.4141, null, null, null, null],
  ["D：投票池化", "措施7", 0.3232, 0.3256, 172, 14, 31],
  ["E：exp 加权池化", "措施2", 0.3838, 0.3864, 176, 16, 19],
  ["F：不对称可信度 R=2", "措施1", 0.3535, 0.3471, 170, 16, 22],
  ["G：可信度 R=2 + exp", "措施1+2", 0.3687, 0.3846, 169, 11, 19],
];

sheet.getRange("A3:G3").format = {
  fill: "#D9E2F3",
  font: { bold: true, color: "#1F4E79" },
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
};
sheet.getRange("A4:G8").format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
sheet.getRange("C4:C8").format.numberFormat = "0.00%";
sheet.getRange("D4:D8").format.numberFormat = "0.00%";
sheet.getRange("E4:G8").format.numberFormat = "0";
sheet.getRange("A4:G4").format = { fill: "#F2F2F2", font: { bold: true } };
sheet.getRange("A6:G6").format = { fill: "#E2EFDA", font: { bold: true } };

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
await fs.writeFile(
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/preview_batch2.png",
  new Uint8Array(await blob.arrayBuffer())
);

const out = await SpreadsheetFile.exportXlsx(workbook);
await out.save(xlsxPath);
console.log("EXPORT_OK");
