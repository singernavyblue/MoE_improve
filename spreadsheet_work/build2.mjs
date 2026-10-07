import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const xlsxPath =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/措施9_措施5_消融实验.xlsx";

const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));

// ---------- Sheet 1: append D-G rows ----------
const s1 = workbook.worksheets.getItem("消融结果总览");
s1.getRange("A9:G12").values = [
  ["D：投票池化（措施7）", 0.3232, 64, 0.3256, 172, 14, 31],
  ["E：exp 加权池化（措施2）", 0.3838, 76, 0.3864, 176, 16, 19],
  ["F：不对称可信度 R=2（措施1）", 0.3535, 70, 0.3471, 170, 16, 22],
  ["G：可信度 R=2 + exp（措施1+2）", 0.3687, 73, 0.3846, 169, 11, 19],
];
const r1 = s1.getRange("A9:G12");
r1.format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
s1.getRange("B9:B12").format.numberFormat = "0.00%";
s1.getRange("D9:D12").format.numberFormat = "0.00%";
s1.getRange("C9:C12").format.numberFormat = "0";
s1.getRange("E9:G12").format.numberFormat = "0";
s1.getRange("A10:A12").format = { font: { bold: true } };
s1.getRange("A11:G12").format = { fill: "#FFF2CC" };
s1.getRange("A1:G1").unmerge();
s1.getRange("A1:G1").merge();
s1.getRange("A2").values = [
  ["对照基线：pairwise margin（seed=0，top_k=3，mean 池化，temperature=0.7）；共 8 个变体（A-G 为消融）"],
];

// ---------- Sheet 2: extend bad-case table to 7 variants ----------
const s2 = workbook.worksheets.getItem("Bad case 对比");
s2.getRange("A1:H1").unmerge();
s2.getRange("A1:L1").merge();
s2.getRange("A3:L3").values = [
  [
    "Bad case", "类型", "gold", "基线 margin", "A 防从众", "B 分歧边", "C 两者合并",
    "D 投票", "E exp", "F 可信度R2", "G 可信度R2+exp", "结论",
  ],
];
s2.getRange("A4:L6").values = [
  ["1（bad1）", "上下文脆弱性", "C", "C ✓", "C ✓", "D ✗", "C ✓", "D ✗", "C ✓", "B ✗", "A ✗", "多轮/拓扑改动会带偏锚（B/D/F/G）"],
  ["10（bad2）", "指令理解+回音室", "D", "A ✗", "A ✗", "C ✗", "B ✗", "B ✗", "B ✗", "C ✗", "C ✗", "全部版本仍未救回"],
  ["27（bad3）", "谄媚从众", "B", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "初始池中无答 B 的节点，无法救回"],
];
s2.getRange("A8:H8").unmerge();
s2.getRange("A8:L8").merge();
s2.getRange("A8").values = [
  ["注：idx=27 三版节点均为 ['qwen','mathstral','qwen']（两个 qwen 相同节点，三个模型初始都答 A）。"],
];
s2.getRange("A3:L3").format = {
  fill: "#FCE4EC",
  font: { bold: true, color: "#C00000" },
  borders: { preset: "all", style: "thin", color: "#F5B7B1" },
};
s2.getRange("A4:L6").format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
s2.getRange("A4:A6").format = { font: { bold: true } };
s2.getRange("A:A").format.columnWidth = 14;
s2.getRange("B:B").format.columnWidth = 18;
s2.getRange("C:K").format.columnWidth = 12;
s2.getRange("L:L").format.columnWidth = 42;

// ---------- Verify & export ----------
const check = await workbook.inspect({
  kind: "table",
  range: "消融结果总览!A1:G12",
  include: "values",
  tableMaxRows: 14,
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
