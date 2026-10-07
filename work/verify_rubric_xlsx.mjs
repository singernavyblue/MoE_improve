import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("outputs/裁判标准_四维表格.xlsx");
const wb = await SpreadsheetFile.importXlsx(input);
const info = await wb.inspect({ kind: "workbook,sheet", maxChars: 3000 });
console.log(info.ndjson);

for (const name of ["使用说明", "维度1 目标对齐", "维度2 信息利用", "维度3 结果验证", "维度4 效率"]) {
  const s = wb.worksheets.getItem(name);
  const r = s.getRange("A1:C12");
  console.log(`--- ${name} ---`);
  for (const row of r.values) {
    console.log(row.map((v) => String(v ?? "").slice(0, 42)).join(" | "));
  }
}
