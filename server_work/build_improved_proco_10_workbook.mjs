import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectDir = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia";
const outputDir = `${projectDir}/outputs/01a0bf30-719f-7601-bf05-d9d52b24c4d2`;
const outPath = `${outputDir}/2026-09-20_改进ProCo_10题验证实验.xlsx`;
const summary = JSON.parse(await fs.readFile(`${projectDir}/outputs/proco_keyverify_improved_10_v3_summary.json`, "utf8"));
const records = JSON.parse(await fs.readFile(`${projectDir}/outputs/proco_keyverify_improved_10_v3.json`, "utf8"));

const wb = Workbook.create();
const overview = wb.worksheets.add("实验结论");
const items = wb.worksheets.add("题目结果");
const evidence = wb.worksheets.add("交叉验证记录");

const font = "Arial";
const navy = "#1F4E78";
const teal = "#0F766E";
const paleBlue = "#EAF2F8";
const paleYellow = "#FFF2CC";
const paleTeal = "#DDEBF7";
const lightGray = "#F3F6F9";
const border = { preset: "all", style: "thin", color: "#D9E2F3" };

function setup(sheet) {
  sheet.showGridLines = false;
}

function title(sheet, text, width) {
  sheet.getRange("A2").values = [[text]];
  sheet.getRange("A2").format.font = { name: font, size: 14, bold: true, color: navy };
  sheet.getRange(`A3:${width}3`).format.borders = { bottom: { style: "thin", color: navy } };
}

function header(sheet, range) {
  const r = sheet.getRange(range);
  r.format = {
    fill: navy,
    font: { name: font, size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#FFFFFF" },
  };
}

function correct(answer, gold) {
  return answer === gold ? 1 : 0;
}

function consensus(rec, slot) {
  const evidenceByVerifier = rec.improved_proco?.[String(slot)] || {};
  const verdicts = Object.values(evidenceByVerifier).map((x) => x.verdict);
  if (verdicts.length === 2 && verdicts.every((x) => x === "NO_MATCH")) return "CONFIRMED_NO_MATCH";
  if (verdicts.length === 2 && verdicts.every((x) => x === "MATCH")) return "CONFIRMED_MATCH";
  if (verdicts.length) return "MIXED_OR_INSUFFICIENT";
  return "NO_EVIDENCE";
}

setup(overview);
title(overview, "改进 ProCo：10 题验证实验", "F");
overview.getRange("A4:F32").format = { font: { name: font, size: 10, color: "#1F2937" }, verticalAlignment: "center" };
overview.getRange("A4").values = [["固定初始推理链；题目锚定关键条件、跨模型独立验证、双验证一致才降权、裁判顺序交换。运行日期：2026-09-20"]];
overview.getRange("A4:F4").merge();
overview.getRange("A4").format = { font: { name: font, size: 10, italic: true, color: "#475569" }, wrapText: true };
overview.getRange("A6:D6").values = [["方法", "正确数", "准确率", "相对无验证基线"]];
header(overview, "A6:D6");
overview.getRange("A7:A10").values = [["原始 GoA"], ["无验证裁判（P0）"], ["原方法 ProCo 证据裁判（P1）"], ["改进版：交叉验证 + 顺序交换裁判"]];
overview.getRange("B7:B10").formulas = [["=SUM('题目结果'!G5:G14)"], ["=SUM('题目结果'!H5:H14)"], ["=SUM('题目结果'!I5:I14)"], ["=SUM('题目结果'!J5:J14)"]];
overview.getRange("C7:C10").formulas = [["=B7/10"], ["=B8/10"], ["=B9/10"], ["=B10/10"]];
overview.getRange("D7:D10").formulas = [["=C7-$C$8"], ["=C8-$C$8"], ["=C9-$C$8"], ["=C10-$C$8"]];
overview.getRange("A7:D10").format.borders = border;
overview.getRange("A7:D7").format.fill = paleBlue;
overview.getRange("A8:D8").format.fill = paleYellow;
overview.getRange("A9:D9").format.fill = "#FCE4D6";
overview.getRange("A10:D10").format.fill = paleTeal;
overview.getRange("B7:B10").format.numberFormat = "0";
overview.getRange("C7:D10").format.numberFormat = "0.0%";

overview.getRange("A13:D13").values = [["配对比较", "改善（错→对）", "退化（对→错）", "McNemar 精确 p 值"]];
header(overview, "A13:D13");
overview.getRange("A14:D15").values = [
  ["改进版 vs 无验证裁判", summary.paired_improved_vs_baseline_judge.fixed, summary.paired_improved_vs_baseline_judge.broken, summary.paired_improved_vs_baseline_judge.mcnemar_exact_p],
  ["改进版 vs 原方法 ProCo", summary.paired_improved_vs_proco_judge.fixed, summary.paired_improved_vs_proco_judge.broken, summary.paired_improved_vs_proco_judge.mcnemar_exact_p],
];
overview.getRange("A14:D15").format.borders = border;
overview.getRange("D14:D15").format.numberFormat = "0.000";

overview.getRange("A18:C18").values = [["双验证共识状态", "链数", "含义"]];
header(overview, "A18:C18");
overview.getRange("A19:C22").values = [
  ["CONFIRMED_NO_MATCH", summary.consensus.CONFIRMED_NO_MATCH, "两名外部验证者均发现矛盾，可作为负证据"],
  ["CONFIRMED_MATCH", summary.consensus.CONFIRMED_MATCH, "两名外部验证者均一致"],
  ["MIXED_OR_INSUFFICIENT", summary.consensus.MIXED_OR_INSUFFICIENT, "验证者不一致或只有一条有效证据，不降权"],
  ["NO_EVIDENCE", summary.consensus.NO_EVIDENCE, "无可用交叉验证记录"],
];
overview.getRange("A19:C22").format.borders = border;
overview.getRange("A19:C19").format.fill = "#FCE4D6";
overview.getRange("A21:C22").format.fill = lightGray;

overview.getRange("A25:C25").values = [["单模型验证结论", "次数 / 比例", "备注"]];
header(overview, "A25:C25");
overview.getRange("A26:C29").values = [
  ["MATCH", 3, "通过结构与内容校验"],
  ["NO_MATCH", 1, "单一模型发现矛盾"],
  ["UNKNOWN", 44, "关键条件不是可验证题面跨度或输出不可解析"],
  ["可用验证比例", 4 / 48, "4 / 48 次实际验证调用"],
];
overview.getRange("A26:C29").format.borders = border;
overview.getRange("B29").format.numberFormat = "0.0%";
overview.getRange("A32:F32").values = [["结论：改进版为 5/10，较原方法 P1 的 4/10 回升 1 题，但仍低于无验证基线 P0 的 7/10。48 次实际交叉验证中仅 4 次有效（8.3%），没有形成任何双验证一致结论；当前改进降低了单一噪声标签的误伤，但验证覆盖与一致性不足，尚不支持替代 P0。"]];
overview.getRange("A32:F32").merge();
overview.getRange("A32").format = { fill: "#E2F0D9", font: { name: font, bold: true, color: "#1F5130" }, wrapText: true, verticalAlignment: "top" };
overview.getRange("A32").format.rowHeight = 44;
overview.getRange("A1:F34").format.wrapText = true;
overview.getRange("A:A").format.columnWidth = 31;
overview.getRange("B:B").format.columnWidth = 13;
overview.getRange("C:D").format.columnWidth = 18;
overview.getRange("E:F").format.columnWidth = 16;

setup(items);
title(items, "10 题配对结果", "N");
items.getRange("A4:N14").format = { font: { name: font, size: 10, color: "#1F2937" }, verticalAlignment: "center" };
items.getRange("A4:N4").values = [["题号", "标准答案", "M0（来源模型）", "M0 答案", "M1（来源模型）", "M1 答案", "GoA 正确", "P0 正确", "P1 正确", "改进版正确", "P0 答案", "P1 答案", "改进版答案", "改进版 vs P0"]];
header(items, "A4:N4");
const itemRows = records.map((r) => {
  const b = r.baseline_judge?.answer;
  const p1 = r.proco_judge?.answer;
  const improved = r.improved_judge?.answer;
  return [
    r.idx,
    r.gold,
    r.sampled_nodes?.[0] ?? "",
    r.initial_answers?.["0"] ?? "",
    r.sampled_nodes?.[1] ?? "",
    r.initial_answers?.["1"] ?? "",
    correct(r.stored_goa_answer, r.gold),
    correct(b, r.gold),
    correct(p1, r.gold),
    correct(improved, r.gold),
    b ?? "",
    p1 ?? "",
    improved ?? "",
    correct(improved, r.gold) > correct(b, r.gold) ? "改善" : correct(improved, r.gold) < correct(b, r.gold) ? "退化" : "不变",
  ];
});
items.getRange(`A5:N${4 + itemRows.length}`).values = itemRows;
items.getRange(`A4:N${4 + itemRows.length}`).format.borders = border;
items.getRange(`A5:N${4 + itemRows.length}`).format.wrapText = true;
items.getRange(`A5:B${4 + itemRows.length}`).format.horizontalAlignment = "center";
items.getRange(`D5:D${4 + itemRows.length}`).format.horizontalAlignment = "center";
items.getRange(`F5:J${4 + itemRows.length}`).format.horizontalAlignment = "center";
items.getRange(`K5:N${4 + itemRows.length}`).format.horizontalAlignment = "center";
items.getRange(`G5:J${4 + itemRows.length}`).conditionalFormats.add("cellIs", { operator: "equal", formula: 1, format: { fill: "#E2F0D9", font: { color: "#1F5130", bold: true } } });
items.getRange(`G5:J${4 + itemRows.length}`).conditionalFormats.add("cellIs", { operator: "equal", formula: 0, format: { fill: "#FCE4D6", font: { color: "#9C0006" } } });
items.getRange(`N5:N${4 + itemRows.length}`).conditionalFormats.add("containsText", { text: "改善", format: { fill: "#E2F0D9", font: { color: "#1F5130", bold: true } } });
items.getRange(`N5:N${4 + itemRows.length}`).conditionalFormats.add("containsText", { text: "退化", format: { fill: "#FCE4D6", font: { color: "#9C0006", bold: true } } });
items.freezePanes.freezeRows(4);
for (const [col, w] of [["A",9],["B",10],["C",22],["D",10],["E",22],["F",10],["G",11],["H",10],["I",10],["J",12],["K",10],["L",10],["M",12],["N",13]]) items.getRange(`${col}:${col}`).format.columnWidth = w;

setup(evidence);
title(evidence, "交叉验证证据", "J");
evidence.getRange("A4:J64").format = { font: { name: font, size: 10, color: "#1F2937" }, verticalAlignment: "center" };
evidence.getRange("A4:J4").values = [["题号", "目标链", "来源模型", "验证模型", "共识状态", "关键条件类型", "关键条件", "独立推断", "验证结论", "异常原因"]];
header(evidence, "A4:J4");
const evidenceRows = [];
for (const rec of records) {
  for (let slot = 0; slot < 3; slot += 1) {
    const entries = rec.improved_proco?.[String(slot)] || {};
    const state = consensus(rec, slot);
    for (const [verifier, e] of Object.entries(entries)) {
      evidenceRows.push([
        rec.idx,
        `M${slot}`,
        rec.sampled_nodes?.[slot] ?? "",
        verifier,
        state,
        e.key_type ?? "",
        e.key_condition ?? "",
        e.verification_answer ?? "",
        e.verdict ?? "",
        e.error ?? "",
      ]);
    }
  }
}
evidence.getRange(`A5:J${4 + evidenceRows.length}`).values = evidenceRows;
evidence.getRange(`A4:J${4 + evidenceRows.length}`).format.borders = border;
evidence.getRange(`A5:J${4 + evidenceRows.length}`).format.wrapText = true;
evidence.getRange(`A5:F${4 + evidenceRows.length}`).format.verticalAlignment = "top";
evidence.getRange(`I5:I${4 + evidenceRows.length}`).conditionalFormats.add("containsText", { text: "NO_MATCH", format: { fill: "#FCE4D6", font: { color: "#9C0006", bold: true } } });
evidence.getRange(`I5:I${4 + evidenceRows.length}`).conditionalFormats.add("containsText", { text: "MATCH", format: { fill: "#E2F0D9", font: { color: "#1F5130", bold: true } } });
evidence.getRange(`I5:I${4 + evidenceRows.length}`).conditionalFormats.add("containsText", { text: "UNKNOWN", format: { fill: "#FFF2CC", font: { color: "#7F6000" } } });
evidence.freezePanes.freezeRows(4);
for (const [col, w] of [["A",9],["B",10],["C",19],["D",19],["E",25],["F",14],["G",44],["H",42],["I",14],["J",31]]) evidence.getRange(`${col}:${col}`).format.columnWidth = w;
evidence.getRange(`A5:J${4 + evidenceRows.length}`).format.rowHeight = 30;

wb.recalculate();
const overviewCheck = await wb.inspect({ kind: "table", range: "实验结论!A2:F32", include: "values,formulas", tableMaxRows: 33, tableMaxCols: 6 });
console.log(overviewCheck.ndjson);
const errorCheck = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errorCheck.ndjson);
await fs.mkdir(outputDir, { recursive: true });
const preview = await wb.render({ sheetName: "实验结论", range: "A1:F32", scale: 1.5, format: "png" });
await fs.writeFile(`${outputDir}/2026-09-20_改进ProCo_10题验证实验_preview.png`, new Uint8Array(await preview.arrayBuffer()));
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outPath);
console.log(outPath);
