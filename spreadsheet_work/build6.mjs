import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const xlsxPath =
  "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/019fc06b-f4c5-7e10-b9dd-ef875dcdcbdc/措施9_措施5_消融实验.xlsx";
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(xlsxPath));

// Sheet 1: relabel J2 row and append J2b (8192)
const s1 = workbook.worksheets.getItem("消融结果总览");
s1.getRange("A15").values = [["J2a：judge=mathstral（4096 上下文）"]];
s1.getRange("A16:G16").values = [
  ["J2b：judge=mathstral（8192 上下文）", "更强裁判", 0.3333, 0.3473, 167, 13, 26],
];
const r16 = s1.getRange("A16:G16");
r16.format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
s1.getRange("B16").format.numberFormat = "0.00%";
s1.getRange("D16").format.numberFormat = "0.00%";
s1.getRange("C16").format.numberFormat = "0";
s1.getRange("E16:G16").format.numberFormat = "0";
s1.getRange("A16:G16").format = { fill: "#FCE4EC" };

// Sheet 2: add J2b column
const s2 = workbook.worksheets.getItem("Bad case 对比");
s2.getRange("A1:O1").unmerge();
s2.getRange("A1:P1").merge();
s2.getRange("A3:P3").values = [
  [
    "Bad case", "类型", "gold", "基线 margin", "A 防从众", "B 分歧边", "C 两者合并",
    "D 投票", "E exp", "F 可信度R2", "G 可信度R2+exp", "H1 top_k6", "J1 judge_qwen",
    "J2 judge_mathstral(4096)", "J2b judge_mathstral(8192)", "结论",
  ],
];
s2.getRange("A4:P6").values = [
  ["1（bad1）", "上下文脆弱性", "C", "C ✓", "C ✓", "D ✗", "C ✓", "D ✗", "C ✓", "B ✗", "A ✗", "D ✗", "C ✓", "C ✓", "D ✗", "多轮/拓扑/扩池/长上下文会带偏锚；J2(4096)可保住"],
  ["10（bad2）", "指令理解+回音室", "D", "A ✗", "A ✗", "C ✗", "B ✗", "B ✗", "B ✗", "C ✗", "C ✗", "D ✗", "B ✗", "B ✗", "C ✗", "全部版本仍未救回"],
  ["27（bad3）", "谄媚从众", "B", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "A ✗", "初始池中无答 B 的节点，无法救回"],
];
s2.getRange("A8:O8").unmerge();
s2.getRange("A8:P8").merge();
s2.getRange("A8").values = [
  ["注：idx=27 节点均为 ['qwen','mathstral','qwen']；H1（top_k=6）受上下文溢出污染；J2a(4096) 有 108 次裁判溢出（tie 兜底），J2b(8192) 溢出为 0 但全链判断更差。"],
];
s2.getRange("A3:P3").format = {
  fill: "#FCE4EC",
  font: { bold: true, color: "#C00000" },
  borders: { preset: "all", style: "thin", color: "#F5B7B1" },
};
s2.getRange("A4:P6").format = { borders: { preset: "all", style: "thin", color: "#D9D9D9" } };
s2.getRange("A4:A6").format = { font: { bold: true } };
s2.getRange("C:P").format.columnWidth = 12;
s2.getRange("P:P").format.columnWidth = 46;

const out = await SpreadsheetFile.exportXlsx(workbook);
await out.save(xlsxPath);
console.log("EXPORT_OK");
