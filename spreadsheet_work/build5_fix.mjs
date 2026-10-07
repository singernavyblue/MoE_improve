import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const xlsxPath =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/措施9_措施5_消融实验.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));
const s2 = workbook.worksheets.getItem("Bad case 对比");
s2.getRange("A1:P1").unmerge();
s2.getRange("A1:O1").merge();
s2.getRange("A8:P8").unmerge();
s2.getRange("A8:O8").merge();
const out = await SpreadsheetFile.exportXlsx(workbook);
await out.save(xlsxPath);
console.log("FIX_OK");
