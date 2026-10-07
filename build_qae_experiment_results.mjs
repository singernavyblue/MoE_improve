import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "qae_experiment_results");
const outputPath = path.join(outputDir, "qae_localized_experiment_results.xlsx");

const sourceFiles = [
  ["MedMCQA", "outputs/qae_localized_medmcqa_summary.json"],
  ["MMLU", "outputs/qae_localized_mmlu_summary.json"],
  ["MMLU-Pro", "outputs/qae_localized_mmlu_pro_summary.json"],
  ["MATH", "outputs/qae_localized_math_free_summary.json"],
  ["HumanEval", "outputs/qae_localized_humaneval_free_summary.json"],
];

const crossResults = [];
for (const [dataset, rel] of sourceFiles) {
  const s = JSON.parse(await fs.readFile(path.join(root, rel), "utf8"));
  const loc = s.conflict_localization || {};
  const guard = loc.directness_guard || {};
  const paired = s.paired_final_vs_A_pool || {};
  crossResults.push({
    dataset,
    baselineN: s.baseline_n ?? s.n,
    finalN: s.n,
    aPool: s.accuracy.A_pool,
    qae: s.accuracy.qae_final,
    fixed: paired.fixed,
    broken: paired.broken,
    p: paired.mcnemar_exact_p,
    conflicts: (loc.conflict_status || {}).CONFLICT ?? 0,
    admitted: guard.ADMITTED ?? 0,
    rejected: guard.REJECTED ?? 0,
    notEligible: guard.NOT_ELIGIBLE ?? 0,
    claims: loc.claim_count ?? "",
    source: rel,
  });
}

const workbook = Workbook.create();
const overview = workbook.worksheets.add("实验结果");
const details = workbook.worksheets.add("证据与定位");
const notes = workbook.worksheets.add("说明");
for (const sheet of [overview, details, notes]) sheet.showGridLines = false;

const title = { font: { name: "Arial", size: 14, bold: true, color: "#1F2937" } };
const header = { fill: "#1F4E78", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
const body = { font: { name: "Arial", size: 10, color: "#1F2937" }, verticalAlignment: "center", wrapText: true };
const note = { font: { name: "Arial", size: 10, italic: true, color: "#4B5563" }, verticalAlignment: "top", wrapText: true };

overview.getRange("A2").values = [["QAE-Pooling + 分歧定位：实验结果汇总"]];
overview.getRange("A2").format = title;
overview.getRange("A4:L4").values = [["数据集", "A_pool 样本数", "QAE 样本数", "A_pool 正确率", "QAE 正确率", "变化（百分点）", "修正", "退化", "McNemar p 值", "定位冲突数", "通过直接性门控", "直接性拒绝"]];
overview.getRange("A4:L4").format = header;

const gpqa = ["GPQA（既有全量）", 195, 198, 67 / 195, 72 / 198, null, "未提供", "未提供", "未提供", "未提供", "未提供", "未提供"];
const rows = [gpqa, ...crossResults.map(r => [r.dataset, r.baselineN, r.finalN, r.aPool, r.qae, null, r.fixed, r.broken, r.p, r.conflicts, r.admitted, r.rejected])];
overview.getRangeByIndexes(4, 0, rows.length, 12).values = rows;
for (let excelRow = 5; excelRow <= 10; excelRow += 1) {
  overview.getRange(`F${excelRow}`).formulas = [[`=E${excelRow}-D${excelRow}`]];
}
overview.getRange("A5:L10").format = body;
overview.getRange("D5:F10").format.numberFormat = [["0.0%", "0.0%", "0.0%"], ["0.0%", "0.0%", "0.0%"], ["0.0%", "0.0%", "0.0%"], ["0.0%", "0.0%", "0.0%"], ["0.0%", "0.0%", "0.0%"], ["0.0%", "0.0%", "0.0%"]];
overview.getRange("I6:I10").format.numberFormat = [["0.000"], ["0.000"], ["0.000"], ["0.000"], ["0.000"]];
overview.getRange("A4:L10").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D9E2F3" };
overview.tables.add("A4:L10", true, "ExperimentResultsTable");
overview.freezePanes.freezeRows(4);
for (const [col, width] of [["A:A", 22], ["B:C", 13], ["D:F", 14], ["G:H", 10], ["I:I", 13], ["J:L", 15]]) overview.getRange(col).format.columnWidth = width;
overview.getRange("A12").values = [["结论提示"]];
overview.getRange("A12").format = { font: { name: "Arial", size: 11, bold: true, color: "#1F2937" } };
overview.getRange("A13:L13").merge();
overview.getRange("A13").values = [["五个跨数据集小样本合计：A_pool 与 QAE 均为 436/650（67.1%）；MMLU-Pro 修正 1 题，MMLU 退化 1 题，均未达到统计显著。GPQA 的两种正确率分母不同，不能据此直接计算配对修正/退化或 McNemar 检验。"]];
overview.getRange("A13").format = note;

details.getRange("A2").values = [["定位、直接性门控与主张覆盖"]];
details.getRange("A2").format = title;
details.getRange("A4:J4").values = [["数据集", "样本数", "原子主张数", "平均主张/题", "定位冲突数", "冲突占比", "直接性通过", "直接性拒绝", "未满足资格", "结果来源"]];
details.getRange("A4:J4").format = header;
const detailRows = crossResults.map(r => [r.dataset, r.finalN, r.claims, r.claims / r.finalN, r.conflicts, r.conflicts / r.finalN, r.admitted, r.rejected, r.notEligible, r.source]);
details.getRangeByIndexes(4, 0, detailRows.length, 10).values = detailRows;
details.getRange("A5:J9").format = body;
details.getRange("D5:D9").format.numberFormat = [["0.000"], ["0.000"], ["0.000"], ["0.000"], ["0.000"]];
details.getRange("F5:F9").format.numberFormat = [["0.0%"], ["0.0%"], ["0.0%"], ["0.0%"], ["0.0%"]];
details.getRange("A4:J9").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D9E2F3" };
details.tables.add("A4:J9", true, "LocalizationTable");
details.freezePanes.freezeRows(4);
for (const [col, width] of [["A:A", 15], ["B:B", 11], ["C:C", 13], ["D:F", 13], ["G:I", 13], ["J:J", 52]]) details.getRange(col).format.columnWidth = width;

notes.getRange("A2").values = [["指标说明与口径"]];
notes.getRange("A2").format = title;
notes.getRange("A4:B4").values = [["字段", "含义"]];
notes.getRange("A4:B4").format = header;
notes.getRange("A5:B12").values = [
  ["A_pool", "初始多模型池化答案的正确率。"],
  ["QAE", "经分歧定位、盲验证、直接性门控和安全池化后的最终正确率。"],
  ["修正 / 退化", "分别指 A_pool 原本错误而 QAE 正确，及 A_pool 原本正确而 QAE 错误的题数。"],
  ["McNemar p 值", "基于修正和退化这两个配对变化计数的双侧精确检验；p 值高说明没有显著差异证据。"],
  ["定位冲突数", "定位器判定为可验证的跨模型关键分歧的题数。"],
  ["通过直接性门控", "STRONG 证据被审核为直接回答已定位分歧、因此可参与安全池化的题数。"],
  ["直接性拒绝", "证据相关但不直接解决分歧，或未满足接纳条件，因此不能授权改答案的题数。"],
  ["GPQA 口径", "该行来自用户提供的既有全量结果：A_pool 为 67/195，QAE 为 72/198；两者分母不同，不能计算配对指标。"],
];
notes.getRange("A5:B12").format = body;
notes.getRange("A4:B12").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D9E2F3" };
notes.getRange("A:A").format.columnWidth = 24;
notes.getRange("B:B").format.columnWidth = 105;
notes.freezePanes.freezeRows(4);

workbook.recalculate();
await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "实验结果", range: "A1:L13", scale: 1.2, format: "png" });
await fs.writeFile(path.join(outputDir, "qae_experiment_results_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const errors = await workbook.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 50 }, summary: "formula error scan" });
console.log(errors.ndjson);
const check = await workbook.inspect({ kind: "table", range: "实验结果!A4:L13", include: "values,formulas", tableMaxRows: 10, tableMaxCols: 12 });
console.log(check.ndjson);
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(JSON.stringify({ outputPath }));
