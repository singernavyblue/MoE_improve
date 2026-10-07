import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const xlsxPath =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/第三批消融结果.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));
const sheet = workbook.worksheets.getItem("第三批消融结果");
try {
  sheet.getRange("A9:I9").unmerge();
} catch (e) {
  // not merged; fine
}
sheet.getRange("A9:I9").clear({ applyTo: "all" });
const out = await SpreadsheetFile.exportXlsx(workbook);
await out.save(xlsxPath);
console.log("FIX_OK");
