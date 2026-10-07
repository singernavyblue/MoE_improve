import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("outputs/四维裁判与DeepSeek对照.xlsx");
const wb = await SpreadsheetFile.importXlsx(input);
const info = await wb.inspect({ kind: "workbook,sheet", maxChars: 2000 });
console.log(info.ndjson);
for (const name of ["四维裁判全量对比", "40题裁判消融", "关键结论"]) {
  const s = wb.worksheets.getItem(name);
  const r = s.getRange("A1:C30");
  console.log(`--- ${name} ---`);
  for (const row of r.values) {
    console.log(row.map((v) => String(v ?? "").slice(0, 38)).join(" | "));
  }
}
