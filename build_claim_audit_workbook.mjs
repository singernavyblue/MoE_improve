import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const root = process.cwd();
const outputDir = path.join(root, "outputs", "qae_claim_audit");
const outputPath = path.join(outputDir, "qae_localized_claim_audit.xlsx");
const sources = [
  ["MedMCQA", "MCQ", "MC_Claim_Extractor", "outputs/qae_localized_medmcqa.json"],
  ["MMLU", "MCQ", "MC_Claim_Extractor", "outputs/qae_localized_mmlu.json"],
  ["MMLU-Pro", "MCQ", "MC_Claim_Extractor", "outputs/qae_localized_mmlu_pro.json"],
  ["MATH", "Free response", "FREE_Claim_Extractor", "outputs/qae_localized_math_free.json"],
  ["HumanEval", "Code", "FREE_Claim_Extractor", "outputs/qae_localized_humaneval_free.json"],
];

const mcPrompt = `You are the Claim Extractor in an evidence-audit workflow. Extract
atomic, checkable claims explicitly made in each frozen attempt below. Do NOT
solve the question, rank attempts, infer an answer option, or add domain facts.

Question:
{question}

Frozen attempts:
{attempts}

For each attempt return at most four claims. A claim must quote a short exact
substring from that attempt (quote) and paraphrase only that statement. Prefer
upstream definitions, assumptions, formulas, substitutions, calculations, and
comparisons over final conclusions. Do not fabricate dependencies.

Return JSON only:
{"claims":[{"model":"M0","id":"C1","type":"definition|assumption|formula|substitution|calculation|comparison|option_mapping","claim":"atomic paraphrase","quote":"exact short substring","depends_on":[],"answer_impact":"low|medium|high"}]}`;

const freePrompt = `Extract atomic, checkable claims explicitly stated in the frozen attempts.
Do not solve the problem or introduce new knowledge. Each claim must include a short
exact quote from its source. Prefer definitions, assumptions, formulas,
substitutions, calculations, comparisons, or program specifications. Return at
most four claims per attempt.

Problem:
{problem}

Frozen attempts:
{attempts}

Return JSON only:
{"claims":[{"model":"M0","type":"definition|assumption|formula|substitution|calculation|comparison|specification","claim":"atomic paraphrase","quote":"exact substring","answer_impact":"low|medium|high"}]}`;

function text(value) {
  // Excel XML 1.0 forbids most C0 control characters. Model outputs can
  // occasionally contain them, so remove only the characters that Excel
  // cannot represent (while preserving tabs, newlines, and ordinary Unicode).
  return value == null
    ? ""
    : String(value).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
}

function modelValue(record, key, field) {
  const collection = record[field] || {};
  return collection[key] ?? collection[`M${key}`] ?? collection[String(key)] ?? "";
}

const questionRows = [];
const claimRows = [];
const summaryRows = [];
for (const [dataset, mode, promptId, relativePath] of sources) {
  const records = JSON.parse(await fs.readFile(path.join(root, relativePath), "utf8"));
  let claims = 0;
  for (const record of records) {
    const extracted = record.swarm_claims?.claims || [];
    claims += extracted.length;
    const answers = record.initial_answers || {};
    const chains = record.initial_responses || {};
    questionRows.push([
      dataset,
      record.idx,
      mode,
      promptId,
      text(record.question ?? record.problem),
      text(record.stored_goa_answer ?? record.baseline_answer),
      text(record.gold),
      text(modelValue(record, "0", "initial_answers")),
      text(modelValue(record, "0", "initial_responses")),
      text(modelValue(record, "1", "initial_answers")),
      text(modelValue(record, "1", "initial_responses")),
      text(modelValue(record, "2", "initial_answers")),
      text(modelValue(record, "2", "initial_responses")),
      extracted.length,
      text(record.swarm_claims?.raw),
    ]);
    for (const claim of extracted) {
      const slot = text(claim.model).replace(/^M/, "");
      claimRows.push([
        dataset,
        record.idx,
        mode,
        promptId,
        text(claim.claim_id),
        text(claim.model),
        text(modelValue(record, slot, "initial_answers")),
        text(claim.type),
        text(claim.answer_impact),
        text(claim.claim),
        text(claim.quote),
        Array.isArray(claim.depends_on) ? claim.depends_on.join(", ") : "",
      ]);
    }
  }
  summaryRows.push([dataset, mode, records.length, claims, records.length ? claims / records.length : 0, promptId, relativePath]);
}

const workbook = Workbook.create();
const overview = workbook.worksheets.add("说明");
const chainsSheet = workbook.worksheets.add("题目与推理链");
const claimsSheet = workbook.worksheets.add("原子主张");
const promptSheet = workbook.worksheets.add("提示词");
for (const sheet of [overview, chainsSheet, claimsSheet, promptSheet]) {
  sheet.showGridLines = false;
}

const titleStyle = { font: { name: "Arial", size: 14, bold: true, color: "#1F2937" } };
const headerStyle = { fill: "#1F4E78", font: { name: "Arial", size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
const bodyStyle = { font: { name: "Arial", size: 10, color: "#1F2937" }, verticalAlignment: "top", wrapText: true };

overview.getRange("A2").values = [["QAE-Pooling：冻结推理链与原子主张审计账本"]];
overview.getRange("A2").format = titleStyle;
overview.getRange("A4:G4").values = [["数据集", "模式", "题目数", "原子主张数", "平均主张/题", "提示词 ID", "来源结果文件"]];
overview.getRange("A5:G" + (4 + summaryRows.length)).values = summaryRows;
overview.getRange("A4:G4").format = headerStyle;
overview.getRange("A5:G" + (4 + summaryRows.length)).format = bodyStyle;
overview.getRange("E5:E" + (4 + summaryRows.length)).format.numberFormat = [["0.000"]];
overview.getRange("A11").values = [["阅读方式"]];
overview.getRange("A11").format = { font: { name: "Arial", size: 11, bold: true, color: "#1F2937" } };
overview.getRange("A12").values = [["先在“题目与推理链”按数据集和 idx 查看同一题的三条冻结推理链；再用相同的“数据集 + idx”在“原子主张”筛选对应主张。提示词 ID 可在“提示词”页查看完整模板。"]];
overview.getRange("A12:G12").merge();
overview.getRange("A12").format = { ...bodyStyle, font: { name: "Arial", size: 10, italic: true, color: "#4B5563" } };
overview.getRange("A:A").format.columnWidth = 17;
overview.getRange("B:B").format.columnWidth = 14;
overview.getRange("C:E").format.columnWidth = 14;
overview.getRange("F:F").format.columnWidth = 25;
overview.getRange("G:G").format.columnWidth = 45;

const chainHeaders = ["数据集", "题目索引 idx", "模式", "提示词 ID", "题目", "A_pool", "金标准", "M0 答案", "M0 冻结推理链", "M1 答案", "M1 冻结推理链", "M2 答案", "M2 冻结推理链", "原子主张数", "提取器原始 JSON 输出"];
chainsSheet.getRangeByIndexes(0, 0, 1, chainHeaders.length).values = [chainHeaders];
chainsSheet.getRangeByIndexes(1, 0, questionRows.length, chainHeaders.length).values = questionRows;
chainsSheet.getRangeByIndexes(0, 0, 1, chainHeaders.length).format = headerStyle;
chainsSheet.getRangeByIndexes(1, 0, questionRows.length, chainHeaders.length).format = bodyStyle;
chainsSheet.getRange(`A1:O${questionRows.length + 1}`).format.borders = { preset: "insideHorizontal", style: "thin", color: "#E5E7EB" };
chainsSheet.tables.add(`A1:O${questionRows.length + 1}`, true, "FrozenChainsTable");
chainsSheet.freezePanes.freezeRows(1);
chainsSheet.freezePanes.freezeColumns(4);
for (const [column, width] of [["A:A", 14], ["B:B", 12], ["C:C", 12], ["D:D", 23], ["E:E", 58], ["F:G", 10], ["H:H", 10], ["I:I", 68], ["J:J", 10], ["K:K", 68], ["L:L", 10], ["M:M", 68], ["N:N", 13], ["O:O", 50]]) {
  chainsSheet.getRange(column).format.columnWidth = width;
}

const claimHeaders = ["数据集", "题目索引 idx", "模式", "提示词 ID", "主张 ID", "来源模型", "该模型答案", "主张类型", "答案影响", "原子主张转述", "原文引句 quote", "依赖主张"];
claimsSheet.getRangeByIndexes(0, 0, 1, claimHeaders.length).values = [claimHeaders];
claimsSheet.getRangeByIndexes(1, 0, claimRows.length, claimHeaders.length).values = claimRows;
claimsSheet.getRangeByIndexes(0, 0, 1, claimHeaders.length).format = headerStyle;
claimsSheet.getRangeByIndexes(1, 0, claimRows.length, claimHeaders.length).format = bodyStyle;
claimsSheet.getRange(`A1:L${claimRows.length + 1}`).format.borders = { preset: "insideHorizontal", style: "thin", color: "#E5E7EB" };
claimsSheet.tables.add(`A1:L${claimRows.length + 1}`, true, "AtomicClaimsTable");
claimsSheet.freezePanes.freezeRows(1);
claimsSheet.freezePanes.freezeColumns(4);
for (const [column, width] of [["A:A", 14], ["B:B", 12], ["C:C", 12], ["D:D", 23], ["E:E", 12], ["F:G", 12], ["H:I", 16], ["J:J", 55], ["K:K", 55], ["L:L", 18]]) {
  claimsSheet.getRange(column).format.columnWidth = width;
}

promptSheet.getRange("A2").values = [["主张提取器提示词模板"]];
promptSheet.getRange("A2").format = titleStyle;
promptSheet.getRange("A4:D4").values = [["提示词 ID", "适用数据", "执行模型", "完整提示词模板"]];
promptSheet.getRange("A5:D6").values = [
  ["MC_Claim_Extractor", "MedMCQA、MMLU、MMLU-Pro", "Qwen2.5-7B-Instruct", mcPrompt],
  ["FREE_Claim_Extractor", "MATH、HumanEval", "Qwen2.5-7B-Instruct", freePrompt],
];
promptSheet.getRange("A4:D4").format = headerStyle;
promptSheet.getRange("A5:D6").format = bodyStyle;
promptSheet.getRange("A4:D6").format.borders = { preset: "insideHorizontal", style: "thin", color: "#E5E7EB" };
promptSheet.getRange("A:A").format.columnWidth = 25;
promptSheet.getRange("B:B").format.columnWidth = 30;
promptSheet.getRange("C:C").format.columnWidth = 25;
promptSheet.getRange("D:D").format.columnWidth = 100;
promptSheet.getRange("D5:D6").format.rowHeight = 300;
promptSheet.freezePanes.freezeRows(4);

workbook.recalculate();
await fs.mkdir(outputDir, { recursive: true });
const preview = await workbook.render({ sheetName: "说明", range: "A1:G12", scale: 1.2, format: "png" });
await fs.writeFile(path.join(outputDir, "claim_audit_preview.png"), new Uint8Array(await preview.arrayBuffer()));
const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
const check = await workbook.inspect({ kind: "table", range: "说明!A2:G12", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 7 });
console.log(check.ndjson);
console.log(JSON.stringify({ outputPath, questions: questionRows.length, claims: claimRows.length }));
