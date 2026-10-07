import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc";
await fs.mkdir(outputDir, { recursive: true });

const workbook = Workbook.create();

// ---------- Sheet 1: 消融结果总览 ----------
const s1 = workbook.worksheets.add("消融结果总览");
s1.showGridLines = false;

s1.getRange("A1:G1").merge();
s1.getRange("A1").values = [["措施 9（防从众提示）+ 措施 5（分歧边）消融实验 · GPQA test 198 题"]];
s1.getRange("A2:G2").merge();
s1.getRange("A2").values = [["对照基线：pairwise margin（seed=0，top_k=3，mean 池化，rounds=1，temperature=0.7）"]];

s1.getRange("A4:G4").values = [
  ["变体", "准确率", "正确数", "严格子集准确率", "严格子集题数", "转对", "转错"],
];

s1.getRange("A5:G8").values = [
  ["基线 pairwise margin", 0.4141, 82, null, null, null, null],
  ["A：防从众提示（措施9）", 0.3687, 73, 0.3779, 172, 17, 22],
  ["B：分歧边（措施5）", 0.3333, 66, 0.3371, 175, 11, 25],
  ["C：两者合并", 0.4091, 81, 0.3941, 170, 19, 22],
];

s1.getRange("A10:G10").merge();
s1.getRange("A10").values = [
  ["注：严格子集 = 与基线节点构成一致的题目子集；转对/转错为该子集内相对基线的翻转数。"],
];

s1.getRange("A1").format = { fill: "#1F4E79", font: { bold: true, color: "#FFFFFF", size: 14 } };
s1.getRange("A2").format = { font: { italic: true, color: "#595959", size: 10 } };
s1.getRange("A4:G4").format = {
  fill: "#D9E2F3",
  font: { bold: true, color: "#1F4E79" },
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
};
s1.getRange("A5:G8").format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
s1.getRange("B5:B8").format.numberFormat = "0.00%";
s1.getRange("D5:D8").format.numberFormat = "0.00%";
s1.getRange("C5:C8").format.numberFormat = "0";
s1.getRange("E5:G8").format.numberFormat = "0";
s1.getRange("A5:G5").format = { fill: "#F2F2F2", font: { bold: true } };
s1.getRange("A8:G8").format = { fill: "#E2EFDA", font: { bold: true } };
s1.getRange("A:A").format.columnWidth = 30;
s1.getRange("B:E").format.columnWidth = 16;
s1.getRange("F:G").format.columnWidth = 10;
s1.getRange("A1").format.rowHeight = 30;
s1.getRange("A2").format.rowHeight = 18;

// ---------- Sheet 2: Bad case 对比 ----------
const s2 = workbook.worksheets.add("Bad case 对比");
s2.showGridLines = false;

s2.getRange("A1:H1").merge();
s2.getRange("A1").values = [["三个典型 Bad case 在各版本中的表现（gold = 标准答案）"]];
s2.getRange("A3:H3").values = [
  ["Bad case", "类型", "gold", "基线 margin", "A 防从众", "B 分歧边", "C 两者合并", "结论"],
];
s2.getRange("A4:H6").values = [
  ["1（bad1）", "上下文脆弱性", "C", "C ✓", "C ✓", "D ✗", "C ✓", "B 版被低分节点带偏（锚保护被破坏）"],
  ["10（bad2）", "指令理解+回音室", "D", "A ✗", "A ✗", "C ✗", "B ✗", "全部版本仍未救回"],
  ["27（bad3）", "谄媚从众", "B", "A ✗", "A ✗", "A ✗", "A ✗", "初始池中无答 B 的节点，无法救回"],
];
s2.getRange("A8:H8").merge();
s2.getRange("A8").values = [
  ["注：idx=27 三版节点均为 ['qwen','mathstral','qwen']（两个 qwen 相同节点，三个模型初始都答 A）。"],
];

s2.getRange("A1").format = { fill: "#C00000", font: { bold: true, color: "#FFFFFF", size: 14 } };
s2.getRange("A3:H3").format = {
  fill: "#FCE4EC",
  font: { bold: true, color: "#C00000" },
  borders: { preset: "all", style: "thin", color: "#F5B7B1" },
};
s2.getRange("A4:H6").format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
s2.getRange("A4:A6").format = { font: { bold: true } };
s2.getRange("A:A").format.columnWidth = 14;
s2.getRange("B:B").format.columnWidth = 18;
s2.getRange("C:G").format.columnWidth = 14;
s2.getRange("H:H").format.columnWidth = 42;
s2.getRange("A1").format.rowHeight = 30;

// ---------- Verify & export ----------
const check = await workbook.inspect({
  kind: "table",
  range: "消融结果总览!A1:G10",
  include: "values,formulas",
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

for (const sheetName of ["消融结果总览", "Bad case 对比"]) {
  const blob = await workbook.render({ sheetName, autoCrop: "all", scale: 2, format: "png" });
  await fs.writeFile(
    `${outputDir}/preview_${sheetName === "消融结果总览" ? "overview" : "badcase"}.png`,
    new Uint8Array(await blob.arrayBuffer())
  );
}

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}/措施9_措施5_消融实验.xlsx`);
console.log("EXPORT_OK");
