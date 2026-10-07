import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const xlsxPath =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/措施9_措施5_消融实验.xlsx";

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));

// ---------- Sheet 1: append batch-3 rows ----------
const s1 = workbook.worksheets.getItem("消融结果总览");
s1.getRange("A13:G15").values = [
  ["H1：top_k=6（全模型池）", "扩大初始池", 0.3182, null, null, null, null],
  ["J1：judge=qwen（通用 7B 裁判）", "更强裁判", 0.3535, 0.3512, 168, 18, 26],
  ["J2：judge=mathstral（科学 7B 裁判）", "更强裁判", 0.4091, 0.4226, 168, 21, 19],
];
const r1 = s1.getRange("A13:G15");
r1.format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
s1.getRange("B13:B15").format.numberFormat = "0.00%";
s1.getRange("D13:D15").format.numberFormat = "0.00%";
s1.getRange("C13:C15").format.numberFormat = "0";
s1.getRange("E13:G15").format.numberFormat = "0";
s1.getRange("A15:G15").format = { fill: "#FFF2CC", font: { bold: true } };

// ---------- Sheet 2: extend bad-case table with H1/J1/J2 ----------
const s2 = workbook.worksheets.getItem("Bad case 对比");
s2.getRange("A1:L1").unmerge();
s2.getRange("A1:P1").merge();
s2.getRange("A3:P3").values = [
  [
    "Bad case", "类型", "gold", "基线 margin", "A 防从众", "B 分歧边", "C 两者合并",
    "D 投票", "E exp", "F 可信度R2", "G 可信度R2+exp", "H1 top_k6", "J1 judge_qwen",
    "J2 judge_mathstral", "结论",
  ],
];
s2.getRange("A4:P6").values = [
  ["1（bad1）", "上下文脆弱性", "C", "C ✓", "C ✓", "D ✗", "C ✓", "D ✗", "C ✓", "B ✗", "A ✗", "D ✗", "C ✓", "C ✓", "多轮/拓扑/扩池会带偏锚；换裁判可保住"],
  ["10（bad2）", "指令理解+回音室", "D", "A ✗", "A ✗", "C ✗", "B ✗", "B ✗", "B ✗", "C ✗", "C ✗", "D ✗", "B ✗", "B ✗", "全部版本仍未救回"],
  ["27（bad3）", "谄媚从众", "B", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "初始池中无答 B 的节点，无法救回"],
];
s2.getRange("A8:L8").unmerge();
s2.getRange("A8:P8").merge();
s2.getRange("A8").values = [
  ["注：idx=27 节点均为 ['qwen','mathstral','qwen']；H1（top_k=6）受 252 次上下文溢出错误污染，J2 受 108 次（mathstral 上下文 4096）污染。"],
];
s2.getRange("A3:P3").format = {
  fill: "#FCE4EC",
  font: { bold: true, color: "#C00000" },
  borders: { preset: "all", style: "thin", color: "#F5B7B1" },
};
s2.getRange("A4:P6").format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
s2.getRange("A4:A6").format = { font: { bold: true } };
s2.getRange("A:A").format.columnWidth = 14;
s2.getRange("B:B").format.columnWidth = 18;
s2.getRange("C:N").format.columnWidth = 12;
s2.getRange("O:O").format.columnWidth = 15;
s2.getRange("P:P").format.columnWidth = 46;

const check = await workbook.inspect({
  kind: "table",
  range: "消融结果总览!A1:G15",
  include: "values",
  tableMaxRows: 18,
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

for (const [sheetName, tag] of [["消融结果总览", "overview"], ["Bad case 对比", "badcase"]]) {
  const blob = await workbook.render({ sheetName, autoCrop: "all", scale: 2, format: "png" });
  await fs.writeFile(
    `/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/preview_${tag}.png`,
    new Uint8Array(await blob.arrayBuffer())
  );
}

const out = await SpreadsheetFile.exportXlsx(workbook);
await out.save(xlsxPath);
console.log("EXPORT_OK");
