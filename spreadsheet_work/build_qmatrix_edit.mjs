import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";
import JSZip from "jszip";

const outPath = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/Q矩阵标定模板_150题.xlsx";

const input = await FileBlob.load(outPath);
const wb = await SpreadsheetFile.importXlsx(input);
const g = wb.worksheets.getItem("标定指南");

// 1. 读取旧“四、示例”区内容
const sectionHeader = g.getRange("A22").values[0][0];
const examples = g.getRange("A23:G25").values;

// 2. 清空 A22:G25（含格式与合并）
g.getRange("A22:G25").clear({ applyTo: "all" });

// 3. 三条裁决写入 A21:A23（每行合并 A:F）
const rulings = [
  "裁决 1｜纯计算题不标 D4：算术/数值步骤归 D2；D4 只标“推理/判断型”多步（中间结论传递、逐条排除、条件推理）。",
  "裁决 2｜主维按学科知识定，数值计算只作次维加标（如 pH 题主维 = D1 化学，即使大量算数）。",
  "裁决 3｜Q4 只认“回答契约”型限定词（except/not/incorrect/唯一/最接近）；化学术语（如 exo/endo）不触发 D5。",
];
for (let i = 0; i < 3; i++) {
  const r = 21 + i;
  g.mergeCells(`A${r}:F${r}`);
  g.getRange(`A${r}`).values = [[rulings[i]]];
}

// 4. 示例区下移到 A25:G28
g.mergeCells("A25:F25");
g.getRange("A25").values = [[sectionHeader]];
g.getRange("A26:G28").values = examples;

// 5. 样式
const DARK = "#1F4E79";
const HEADER_FILL = "#D9E2F3";
const BORDER = "#D9D9D9";
for (let i = 0; i < 3; i++) {
  const r = 21 + i;
  g.getRange(`A${r}:F${r}`).format = {
    fill: "#FBF3E2",
    font: { color: "#7A5A00", size: 10 },
    borders: { preset: "all", style: "thin", color: "#E5D5A8" },
    wrapText: true,
    verticalAlignment: "center",
    horizontalAlignment: "left",
  };
  g.getRange(`A${r}`).format.rowHeight = 32;
}
g.getRange("A25").format = { fill: HEADER_FILL, font: { bold: true, color: DARK, size: 12 }, verticalAlignment: "center" };
g.getRange("A26:G26").format = {
  fill: HEADER_FILL,
  font: { bold: true, color: DARK },
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
g.getRange("A27:G28").format = {
  borders: { preset: "all", style: "thin", color: BORDER },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
g.getRange("A25").format.rowHeight = 24;
g.getRange("A26").format.rowHeight = 22;
g.getRange("A27:A28").format.rowHeight = 24;

const xlsx = await SpreadsheetFile.exportXlsx(wb);
await xlsx.save(outPath);

// 6. 重新补写冻结窗格（import/export 可能丢 pane）
const buf = await fs.readFile(outPath);
const zip = await JSZip.loadAsync(buf);
const sheet2Path = "xl/worksheets/sheet2.xml";
let xml = await zip.file(sheet2Path).async("string");
if (!xml.includes("<x:pane")) {
  xml = xml.replace(
    '<x:sheetViews><x:sheetView showGridLines="0" workbookViewId="0" /></x:sheetViews>',
    '<x:sheetViews><x:sheetView showGridLines="0" workbookViewId="0">' +
      '<x:pane x:xSplit="4" x:ySplit="4" x:topLeftCell="E5" x:activePane="bottomRight" x:state="frozen"/>' +
      '<x:selection x:pane="bottomRight" x:activeCell="E5" x:sqref="E5"/>' +
      "</x:sheetView></x:sheetViews>",
  );
  zip.file(sheet2Path, xml);
}
const out = await zip.generateAsync({ type: "nodebuffer" });
await fs.writeFile(outPath, out);
console.log("edited:", outPath);
