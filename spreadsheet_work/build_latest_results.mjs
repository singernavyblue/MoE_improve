import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia";
const OUT = path.join(ROOT, "outputs", "最新更新_代码运行_分析结果汇总.xlsx");
const FONT = "Arial";
const COLORS = {
  navy: "#1F4E78",
  blue: "#D9EAF7",
  lightBlue: "#EEF5FB",
  gray: "#F3F4F6",
  green: "#E2F0D9",
  amber: "#FFF2CC",
  red: "#FCE4D6",
  text: "#1F2937",
  border: "#D9E2F3",
};

async function readJson(rel) {
  return JSON.parse(await fs.readFile(path.join(ROOT, rel), "utf8"));
}

async function statFile(rel) {
  const st = await fs.stat(path.join(ROOT, rel));
  return {
    file: rel,
    modified: st.mtime.toISOString().replace("T", " ").replace(".000Z", " UTC"),
    sizeKb: Math.round(st.size / 1024 * 10) / 10,
    sizeBytes: st.size,
  };
}

function pct(n, d) {
  return d ? n / d : null;
}

function pp(n) {
  return n == null ? null : n * 100;
}

function mcnemarP(b, c) {
  const n = b + c;
  if (!n) return 1;
  let tail = 0;
  for (let k = 0; k <= Math.min(b, c); k++) {
    let comb = 1;
    for (let i = 1; i <= k; i++) comb *= (n - i + 1) / i;
    tail += comb;
  }
  return Math.min(1, 2 * tail / (2 ** n));
}

function pairedSummary(ds, rows) {
  const isCode = ds === "humaneval";
  const aKey = isCode ? "A_pass" : "A_correct";
  const jKey = isCode ? "J_pass" : "J_correct";
  const n = rows.length;
  const a = rows.filter(r => r[aKey] === true).length;
  const j = rows.filter(r => r[jKey] === true).length;
  const toCorrect = rows.filter(r => !r[aKey] && r[jKey]).length;
  const toWrong = rows.filter(r => r[aKey] && !r[jKey]).length;
  const pool = isCode ? null : rows.filter(r => r.gold_in_pool === true).length;
  return {
    dataset: ds,
    n,
    A_correct: a,
    A_accuracy: pct(a, n),
    J_correct: j,
    J_accuracy: pct(j, n),
    delta_pp: pp(pct(j, n) - pct(a, n)),
    to_correct: toCorrect,
    to_wrong: toWrong,
    mcnemar_p: mcnemarP(toCorrect, toWrong),
    gold_in_pool: pool,
    gold_in_pool_rate: pool == null ? null : pct(pool, n),
  };
}

function datasetLabel(ds) {
  return {
    medmcqa: "MedMCQA",
    humaneval: "HumanEval（dev，pass@1）",
    math: "MATH",
    mmlu: "MMLU",
    mmlu_pro: "MMLU-Pro",
  }[ds] || ds;
}

function shortJson(value, max = 160) {
  if (value == null) return "";
  const s = typeof value === "string" ? value : JSON.stringify(value);
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}

function winnerModel(row) {
  const idx = row.J_winner;
  return idx == null ? "" : (row.sampled_nodes || [])[idx] || `M${idx}`;
}

function safeCell(v) {
  if (v === undefined) return null;
  if (typeof v === "number" && !Number.isFinite(v)) return null;
  return v;
}

function writeTitle(sheet, title, subtitle) {
  sheet.getRange("A1").values = [[title]];
  sheet.getRange("A1").format = { font: { name: FONT, size: 15, bold: true, color: COLORS.text } };
  sheet.getRange("A2").values = [[subtitle]];
  sheet.getRange("A2").format = { font: { name: FONT, size: 10, italic: true, color: "#5B6573" } };
  sheet.getRange("A3:Z3").format.borders = { bottom: { style: "thin", color: COLORS.navy } };
  sheet.showGridLines = false;
}

function writeTable(sheet, startRow, startCol, headers, rows, widths = {}) {
  const endRow = startRow + rows.length;
  const endCol = startCol + headers.length - 1;
  const matrix = [headers, ...rows].map(row => row.map(safeCell));
  const range = sheet.getRangeByIndexes(startRow - 1, startCol - 1, matrix.length, headers.length);
  range.values = matrix;
  const header = sheet.getRangeByIndexes(startRow - 1, startCol - 1, 1, headers.length);
  header.format = {
    fill: COLORS.navy,
    font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
  };
  const body = sheet.getRangeByIndexes(startRow, startCol - 1, rows.length, headers.length);
  body.format = {
    font: { name: FONT, size: 10, color: COLORS.text },
    verticalAlignment: "center",
    wrapText: false,
  };
  range.format.borders = { insideHorizontal: { style: "thin", color: COLORS.border }, bottom: { style: "thin", color: COLORS.border } };
  for (const [col, width] of Object.entries(widths)) {
    sheet.getRange(`${col}1:${col}${Math.max(endRow, 20)}`).format.columnWidth = width;
  }
  return { startRow, endRow, startCol, endCol };
}

function formatNumeric(sheet, range, format) {
  sheet.getRange(range).format.numberFormat = format;
}

async function build() {
  const pairedFiles = {
    medmcqa: "outputs/paired_medmcqa_Aquick.json",
    humaneval: "outputs/paired_humaneval_Aquick.json",
    math: "outputs/paired_math_Aquick.json",
    mmlu: "outputs/paired_mmlu_Aquick.json",
    mmlu_pro: "outputs/paired_mmlu_pro_Aquick.json",
  };
  const paired = {};
  for (const [ds, rel] of Object.entries(pairedFiles)) paired[ds] = await readJson(rel);

  const gpqaFiles = {
    baseline_prom: "outputs/baseline_prom_replay_198.json",
    deepseek: "outputs/deepseek_baseline_full_198.json",
    four_dim_prom: "outputs/4dim_prom_full_198.json",
    four_dim_ds: "outputs/4dim_ds_full_198.json",
    judge: "outputs/judge_adjudicate_198.json",
    judge_all: "outputs/judge_adjudicate_198_all.json",
  };
  const gpqa = {};
  for (const [k, rel] of Object.entries(gpqaFiles)) gpqa[k] = await readJson(rel);

  const pairedSummaries = Object.entries(paired).map(([ds, rows]) => pairedSummary(ds, rows));
  const gpqaSpecs = [
    ["Prometheus pairwise 基线", "baseline_prom", "A_prom", "outputs/baseline_prom_replay_198.json"],
    ["DeepSeek pairwise", "deepseek", "A_ds", "outputs/deepseek_baseline_full_198.json"],
    ["Prometheus 四维 pairwise", "four_dim_prom", "A_prom", "outputs/4dim_prom_full_198.json"],
    ["DeepSeek 四维 pairwise", "four_dim_ds", "A_ds", "outputs/4dim_ds_full_198.json"],
    ["机制裁决闭环 J（分层版）", "judge", "J_answer", "outputs/judge_adjudicate_198.json"],
    ["机制裁决闭环 J（全量存档版）", "judge_all", "J_answer", "outputs/judge_adjudicate_198_all.json"],
  ];
  const gpqaSummary = gpqaSpecs.map(([label, key, answerKey, source]) => {
    const rows = gpqa[key];
    const n = rows.length;
    const correct = rows.filter(r => String(r[answerKey]) === String(r.gold)).length;
    return { label, n, correct, accuracy: pct(correct, n), source };
  });

  const workbook = Workbook.create();
  const overview = workbook.worksheets.add("概览");
  const dsSheet = workbook.worksheets.add("数据集结果");
  const pairSheet = workbook.worksheets.add("配对明细");
  const gpqaSheet = workbook.worksheets.add("GPQA裁判结果");
  const codeSheet = workbook.worksheets.add("代码运行状态");
  const analysisSheet = workbook.worksheets.add("分析结果");
  const sourceSheet = workbook.worksheets.add("来源文件");
  for (const s of [overview, dsSheet, pairSheet, gpqaSheet, codeSheet, analysisSheet, sourceSheet]) {
    s.getRange("A1:Z2000").format.font = { name: FONT, size: 10, color: COLORS.text };
    s.getRange("A1:Z2000").format.verticalAlignment = "center";
  }

  // Overview
  writeTitle(overview, "最新更新、代码运行与分析结果汇总", "汇总截至 2026-09-20；完整实验输出最近更新至 2026-09-09。数据来自工作区现有 JSON、Markdown 与运行脚本。");
  overview.getRange("A5:B8").values = [
    ["范围", "已纳入 2026-09-09 五数据集配对实验、2026-09-09 GPQA 裁判对照、相关分析报告与最近脚本状态"],
    ["重要状态", "2026-09-20 更新的 ProCo 脚本已纳入代码状态页，但当前工作区未发现其对应结果 JSON/摘要文件"],
    ["输出用途", "便于查看最新数值、逐题结果、代码产物和分析结论；原始文件路径保留在来源文件页"],
    ["口径提醒", "GPQA J 的 198 题分层版与全量存档版是两个不同结果口径，已分行展示"],
  ];
  overview.getRange("A5:A8").format = { fill: COLORS.blue, font: { name: FONT, size: 10, bold: true, color: COLORS.text } };
  overview.getRange("B5:B8").format = { fill: COLORS.lightBlue, font: { name: FONT, size: 10, color: COLORS.text }, wrapText: true };
  overview.getRange("A5:A8").format.columnWidth = 14;
  overview.getRange("B5:B8").format.columnWidth = 100;
  overview.getRange("A5:B8").format.rowHeight = 34;
  overview.getRange("A10:F10").values = [["数据集", "n", "A / 原版正确数", "A 准确率", "J 正确数", "J 准确率"]];
  overview.getRange("A10:F10").format = { fill: COLORS.navy, font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
  overview.getRange("A11:F15").values = pairedSummaries.map(r => [datasetLabel(r.dataset), r.n, r.A_correct, r.A_accuracy, r.J_correct, r.J_accuracy]);
  overview.getRange("A11:F15").format.borders = { insideHorizontal: { style: "thin", color: COLORS.border }, bottom: { style: "thin", color: COLORS.border } };
  formatNumeric(overview, "D11:D15", "0.0%");
  formatNumeric(overview, "F11:F15", "0.0%");
  overview.getRange("H10:K10").values = [["GPQA 裁判变体", "n", "正确数", "准确率"]];
  overview.getRange("H10:K10").format = { fill: COLORS.navy, font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
  overview.getRange("H11:K16").values = gpqaSummary.map(r => [r.label, r.n, r.correct, r.accuracy]);
  overview.getRange("H11:K16").format.borders = { insideHorizontal: { style: "thin", color: COLORS.border }, bottom: { style: "thin", color: COLORS.border } };
  formatNumeric(overview, "K11:K16", "0.0%");
  overview.getRange("A18:K18").values = [["最新分析摘要", null, null, null, null, null, null, null, null, null, null]];
  overview.getRange("A18:K18").format = { fill: COLORS.blue, font: { name: FONT, size: 11, bold: true, color: COLORS.text } };
  overview.getRange("A19:K22").values = [
    ["五数据集", "J 在 MMLU-Pro 上 +5.5pp 且显著；在 MATH（−21pp）和 HumanEval（−14pp）上明显变差；MMLU 与 MedMCQA 基本持平。", null, null, null, null, null, null, null, null, null],
    ["机制解释", "J 更像针对低置信/高难度任务的纠错开关，不宜作为所有任务的通用池化替代。", null, null, null, null, null, null, null, null, null],
    ["GPQA 裁判", "换裁判本身不是关键；直接选 top 链或采用证据质询闭环，比把 DeepSeek 仅用于打分/传播更有效。", null, null, null, null, null, null, null, null, null],
    ["限制", "五数据集是快速配对子集；HumanEval 与 MATH 的 J 口径存在适配差异；GPQA 分层版依赖池内分层口径。", null, null, null, null, null, null, null, null, null],
  ];
  overview.getRange("A19:A22").format = { fill: COLORS.gray, font: { name: FONT, size: 10, bold: true, color: COLORS.text } };
  overview.getRange("B19:K22").format = { wrapText: true, font: { name: FONT, size: 10, color: COLORS.text } };
  overview.getRange("B19:B22").format.columnWidth = 100;
  overview.getRange("C19:K22").format.columnWidth = 14;
  overview.getRange("A19:A22").format.columnWidth = 14;
  overview.getRange("B19:K22").format.rowHeight = 34;
  for (const c of ["C", "D", "E", "F", "G", "H", "I", "J", "K"]) overview.getRange(`${c}1:${c}30`).format.columnWidth = 14;
  overview.getRange("H1:H30").format.columnWidth = 30;
  overview.tabColor = COLORS.navy;

  // Dataset result summary
  writeTitle(dsSheet, "五数据集配对实验结果", "来源：outputs/paired_*_Aquick.json；A=原版 GoA 互评/池化，J=同一冻结初始链上裁判选链。");
  const dsRows = pairedSummaries.map(r => [
    datasetLabel(r.dataset), r.n, r.A_correct, r.A_accuracy, r.J_correct, r.J_accuracy,
    r.delta_pp / 100, r.to_correct, r.to_wrong, r.mcnemar_p, r.gold_in_pool, r.gold_in_pool_rate,
    r.dataset === "humaneval" ? "J 为代码选链适配口径；无 gold_in_pool" : "A/J 同批冻结链；gold_in_pool 为初始模型池是否含正确答案",
  ]);
  writeTable(dsSheet, 5, 1, ["数据集", "n", "A 正确数", "A 准确率", "J 正确数", "J 准确率", "J-A 差值", "转对", "转错", "McNemar p", "gold 在池内数", "gold 在池内比例", "说明"], dsRows, { A: 22, B: 9, C: 12, D: 12, E: 12, F: 12, G: 12, H: 9, I: 9, J: 12, K: 14, L: 15, M: 58 });
  formatNumeric(dsSheet, "D6:D10", "0.0%"); formatNumeric(dsSheet, "F6:F10", "0.0%"); formatNumeric(dsSheet, "G6:G10", "0.0%"); formatNumeric(dsSheet, "J6:J10", "0.0000"); formatNumeric(dsSheet, "L6:L10", "0.0%");
  dsSheet.getRange("M6:M10").format.wrapText = true;
  dsSheet.getRange("M6:M10").format.rowHeight = 34;
  dsSheet.freezePanes.freezeRows(5);
  dsSheet.tabColor = "#5B9BD5";

  // Paired detail
  writeTitle(pairSheet, "五数据集逐题配对明细", "保留关键可复核字段；模型原始长文本仍在源 JSON 中，未重复塞入工作簿。");
  const pairRows = [];
  for (const [ds, rows] of Object.entries(paired)) {
    for (const r of rows) {
      const isCode = ds === "humaneval";
      pairRows.push([
        datasetLabel(ds), r.idx, r.gold, shortJson(r.A_answer, 240), shortJson(r.J_answer, 240),
        isCode ? r.A_pass : r.A_correct, isCode ? r.J_pass : r.J_correct, isCode ? "" : r.gold_in_pool,
        r.J_winner, winnerModel(r), (r.sampled_nodes || []).join(" / "), shortJson(r.A_score_dict, 120), r.time_s,
      ]);
    }
  }
  writeTable(pairSheet, 5, 1, ["数据集", "题号", "gold", "A 答案（截断）", "J 答案（截断）", "A 正确/通过", "J 正确/通过", "gold 在池内", "J winner index", "J winner 模型", "采样模型", "A 分数", "耗时(s)"], pairRows, { A: 22, B: 9, C: 18, D: 34, E: 34, F: 12, G: 12, H: 12, I: 12, J: 18, K: 34, L: 24, M: 11 });
  pairSheet.getRange(`D6:E${pairRows.length + 5}`).format.wrapText = true;
  pairSheet.getRange(`D6:E${pairRows.length + 5}`).format.rowHeight = 32;
  pairSheet.freezePanes.freezeRows(5);
  pairSheet.tabColor = "#A5A5A5";

  // GPQA sheet: summary then detail
  writeTitle(gpqaSheet, "GPQA 裁判对照结果", "198 题冻结链；不同 JSON 文件代表不同裁判/闭环口径。J 分层版与全量存档版分开保留。");
  const gpqaSummaryRows = gpqaSummary.map(r => [r.label, r.n, r.correct, r.accuracy, r.source]);
  writeTable(gpqaSheet, 5, 1, ["裁判变体", "n", "正确数", "准确率", "来源"], gpqaSummaryRows, { A: 30, B: 9, C: 12, D: 12, E: 44 });
  formatNumeric(gpqaSheet, "D6:D11", "0.0%");
  gpqaSheet.getRange("A14:E14").values = [["逐题对照明细", null, null, null, null]];
  gpqaSheet.getRange("A14:E14").format = { fill: COLORS.blue, font: { name: FONT, size: 11, bold: true, color: COLORS.text } };
  const maps = Object.fromEntries(Object.entries(gpqa).map(([k, rows]) => [k, new Map(rows.map(r => [r.idx, r]))]));
  const ids = Array.from(new Set(gpqa.baseline_prom.map(r => r.idx))).sort((a, b) => a - b);
  const gpqaDetail = ids.map(idx => {
    const b = maps.baseline_prom.get(idx) || {};
    const d = maps.deepseek.get(idx) || {};
    const p = maps.four_dim_prom.get(idx) || {};
    const q = maps.four_dim_ds.get(idx) || {};
    const j = maps.judge.get(idx) || {};
    const ja = maps.judge_all.get(idx) || {};
    return [
      idx, b.gold || d.gold || p.gold || q.gold || j.gold || ja.gold || "",
      b.A_prom || "", d.A_ds || "", p.A_prom || "", q.A_ds || "", j.J_answer || "", ja.J_answer || "",
      b.A_prom === b.gold, d.A_ds === d.gold, p.A_prom === p.gold, q.A_ds === q.gold, j.J_answer === j.gold, ja.J_answer === ja.gold,
      j.winner_model || "", j.gold_in_pool, shortJson(j.note, 120),
    ];
  });
  writeTable(gpqaSheet, 15, 1, ["题号", "gold", "Prom 基线", "DeepSeek", "Prom 四维", "DeepSeek 四维", "J 分层", "J 全量存档", "Prom 对", "DS 对", "Prom 四维对", "DS 四维对", "J 分层对", "J 全量对", "J winner 模型", "gold 在池内", "J 备注"], gpqaDetail, { A: 9, B: 10, C: 12, D: 12, E: 12, F: 14, G: 12, H: 14, I: 10, J: 10, K: 12, L: 12, M: 10, N: 10, O: 20, P: 12, Q: 26 });
  gpqaSheet.getRange(`Q16:Q${gpqaDetail.length + 15}`).format.wrapText = true;
  gpqaSheet.freezePanes.freezeRows(15);
  gpqaSheet.tabColor = "#70AD47";

  // Code run status
  writeTitle(codeSheet, "代码运行状态与产物", "按最近修改时间整理；“未发现”仅表示当前工作区没有对应输出文件，不代表远端运行一定失败。");
  const scripts = [
    ["server_work/run_proco_keyverify.py", "2026-09-20", "ProCo key-condition verification participant/judge/summary runner", "outputs/proco_keyverify_40.json；outputs/proco_keyverify_40_summary.json", "未发现对应结果文件", "脚本已更新，结果待回传/生成"],
    ["server_work/run_proco_keyverify_serial.sh", "2026-09-20", "单 GPU 串行启动 qwen、mathstral、biomedical_llama、prometheus 并执行 ProCo", "同上", "未发现对应结果文件", "脚本已更新，结果待回传/生成"],
    ["server_work/run_paired_multi_dataset.py", "2026-09-10", "五数据集 A_orig vs J 快速配对实验", "outputs/paired_{medmcqa,humaneval,math,mmlu,mmlu_pro}_Aquick.json", "已发现 5 个 JSON 结果", "已有运行产物"],
    ["server_work/run_paired_A_quick.sh", "2026-09-09", "五数据集快速配对启动脚本", "outputs/paired_*_Aquick.json；outputs/五数据集_原版互评vsJ_快速配对_20260909.md", "已发现 JSON 与 Markdown", "已有运行产物"],
    ["server_work/run_deepseek_baseline_full.py", "2026-09-09", "GPQA 198 题不同裁判/边打分模式运行器", "outputs/baseline_prom_replay_198.json；deepseek/4dim JSON", "已发现 4 个 JSON 结果", "已有运行产物"],
  ];
  writeTable(codeSheet, 5, 1, ["脚本", "最近更新", "用途", "预期输出", "当前发现", "状态"], scripts, { A: 38, B: 14, C: 52, D: 55, E: 30, F: 24 });
  codeSheet.getRange("C6:E10").format.wrapText = true;
  codeSheet.getRange("C6:E10").format.rowHeight = 40;
  codeSheet.getRange("F6:F10").format = { fill: COLORS.green, font: { name: FONT, size: 10, bold: true, color: COLORS.text } };
  codeSheet.getRange("F6:F7").format = { fill: COLORS.amber, font: { name: FONT, size: 10, bold: true, color: COLORS.text } };
  codeSheet.getRange("A13:G13").values = [["已发现的最新结果/报告产物", null, null, null, null, null, null]];
  codeSheet.getRange("A13:G13").format = { fill: COLORS.blue, font: { name: FONT, size: 11, bold: true, color: COLORS.text } };
  const artifactList = [
    ["结果 JSON", "outputs/paired_medmcqa_Aquick.json", "100", "五数据集快速配对", "纳入数据集结果与逐题明细"],
    ["结果 JSON", "outputs/paired_humaneval_Aquick.json", "50", "五数据集快速配对", "纳入数据集结果与逐题明细"],
    ["结果 JSON", "outputs/paired_math_Aquick.json", "100", "五数据集快速配对", "纳入数据集结果与逐题明细"],
    ["结果 JSON", "outputs/paired_mmlu_Aquick.json", "200", "五数据集快速配对", "纳入数据集结果与逐题明细"],
    ["结果 JSON", "outputs/paired_mmlu_pro_Aquick.json", "200", "五数据集快速配对", "纳入数据集结果与逐题明细"],
    ["结果 JSON", "outputs/baseline_prom_replay_198.json", "198", "GPQA Prometheus 基线", "纳入 GPQA 对照"],
    ["结果 JSON", "outputs/deepseek_baseline_full_198.json", "198", "GPQA DeepSeek", "纳入 GPQA 对照"],
    ["结果 JSON", "outputs/4dim_prom_full_198.json", "198", "GPQA Prometheus 四维", "纳入 GPQA 对照"],
    ["结果 JSON", "outputs/4dim_ds_full_198.json", "198", "GPQA DeepSeek 四维", "纳入 GPQA 对照"],
    ["结果 JSON", "outputs/judge_adjudicate_198.json", "198", "GPQA J 分层版", "纳入 GPQA 对照"],
    ["结果 JSON", "outputs/judge_adjudicate_198_all.json", "198", "GPQA J 全量存档版", "纳入 GPQA 对照"],
    ["分析报告", "outputs/五数据集_原版互评vsJ_快速配对_20260909.md", "—", "五数据集结论/口径说明", "纳入分析结果"],
    ["分析报告", "outputs/三种裁判角色_DeepSeek对照_20260909.md", "—", "GPQA 裁判角色对照", "纳入分析结果"],
    ["分析报告", "outputs/gpqa_pairwise_margin_analysis.md", "—", "GPQA pairwise margin 历史分析", "纳入分析结果"],
    ["分析报告", "outputs/gpqa_analysis_report.md", "—", "GPQA 错误分析与改进方向", "纳入分析结果"],
  ];
  writeTable(codeSheet, 14, 1, ["类型", "文件", "记录数", "内容", "本工作簿用途"], artifactList, { A: 14, B: 50, C: 10, D: 32, E: 32 });
  codeSheet.getRange("D15:E29").format.wrapText = true;
  codeSheet.freezePanes.freezeRows(5);
  codeSheet.tabColor = "#ED7D31";

  // Analysis results
  writeTitle(analysisSheet, "分析结果与口径说明", "把已有 Markdown 报告中的结论、机制解释与限制整理为结构化记录；原文仍保留在来源文件中。");
  const analysisRows = [
    ["五数据集配对", "主要结果", "J 在 MMLU-Pro 上 51.0%→56.5%，+5.5pp，McNemar p=0.035；在 MATH 上 76.0%→55.0%，−21.0pp；HumanEval 84.0%→70.0%，−14.0pp。", "outputs/五数据集_原版互评vsJ_快速配对_20260909.md"],
    ["五数据集配对", "机制结论", "J 只在模型池自身表现较弱、讨论/池化容易把正确链带偏的任务上更可能有效；在讨论本身已较强的任务上，直接选一条初始链会放弃池化红利。", "outputs/五数据集_原版互评vsJ_快速配对_20260909.md"],
    ["五数据集配对", "建议", "把 J 当作低置信/高难度任务的针对性纠错开关，而不是通用池化替代。", "outputs/五数据集_原版互评vsJ_快速配对_20260909.md"],
    ["五数据集配对", "限制", "本轮是快速配对子集；HumanEval 的证据环节对代码意义有限；MATH 与 HumanEval 的 J 是适配口径；GPQA 历史行不是同轮配对。", "outputs/五数据集_原版互评vsJ_快速配对_20260909.md"],
    ["GPQA 裁判角色", "主要结果", "仅换裁判而保留传播/池化时，Prometheus 基线 34.34%，DeepSeek pairwise 31.82%，Prometheus 四维 34.85%，DeepSeek 四维 34.34%；直接选链的 J 分层版 44.44%。", "outputs/三种裁判角色_DeepSeek对照_20260909.md"],
    ["GPQA 裁判角色", "机制结论", "关键不在于把裁判换成 DeepSeek，而在于让裁判直接完成可信链选择；若仍交给消息传递/池化，裁判优势会被改写或稀释。", "outputs/三种裁判角色_DeepSeek对照_20260909.md"],
    ["GPQA 裁判角色", "下一步", "建议把 DeepSeek 直接选 top 链作为更简单基线，再跑一版正式 198 题确认；J 分层版依赖池内分层口径，需谨慎并排比较。", "outputs/三种裁判角色_DeepSeek对照_20260909.md"],
    ["GPQA pairwise margin", "主要结果", "pairwise margin 41.41%（82/198），高于原版互评基线 35.86%（71/198），接近有 gold 裁判 41.92%（83/198）。", "outputs/gpqa_pairwise_margin_analysis.md"],
    ["GPQA pairwise margin", "机制结论", "相对比较加幅度信息比只数胜负更能拉开正确链与错误链的权重；严格子集上 margin 对 Copeland 的转对/转错为 25/12。", "outputs/gpqa_pairwise_margin_analysis.md"],
    ["GPQA 错误分析", "主要原因", "化学题占比高且表现弱；7B 模型在知识盲点上会高置信度答错；多数意见、消息传递与池化可能放大回音室效应。", "outputs/gpqa_analysis_report.md"],
    ["GPQA 错误分析", "改进方向", "优先换更强底座或补齐真正覆盖化学/物理的领域模型；其次再考虑增加 rounds/top_k；修复答案解析正则和 except/not 指令提示。", "outputs/gpqa_analysis_report.md"],
    ["当前工作区状态", "ProCo", "2026-09-20 更新了 ProCo 参与者/裁判/汇总脚本，但当前工作区未发现 proco_keyverify_40.json 或摘要文件，因此没有把未生成的数值写入结果表。", "server_work/run_proco_keyverify.py；server_work/run_proco_keyverify_serial.sh"],
  ];
  writeTable(analysisSheet, 5, 1, ["主题", "类别", "分析结果", "来源"], analysisRows, { A: 20, B: 16, C: 100, D: 58 });
  analysisSheet.getRange(`C6:C${analysisRows.length + 5}`).format.wrapText = true;
  analysisSheet.getRange(`C6:C${analysisRows.length + 5}`).format.rowHeight = 48;
  analysisSheet.freezePanes.freezeRows(5);
  analysisSheet.tabColor = "#8064A2";

  // Sources inventory
  writeTitle(sourceSheet, "来源文件清单", "列出本次汇总实际读取或引用的关键文件，便于回溯；路径均相对于当前工作区根目录。");
  const sourceRels = [
    ...Object.values(pairedFiles), ...Object.values(gpqaFiles),
    "outputs/五数据集_原版互评vsJ_快速配对_20260909.md",
    "outputs/三种裁判角色_DeepSeek对照_20260909.md",
    "outputs/gpqa_pairwise_margin_analysis.md",
    "outputs/gpqa_analysis_report.md",
    "server_work/run_proco_keyverify.py",
    "server_work/run_proco_keyverify_serial.sh",
    "server_work/run_paired_multi_dataset.py",
    "server_work/run_paired_A_quick.sh",
    "server_work/run_deepseek_baseline_full.py",
  ];
  const sourceRows = [];
  for (const rel of sourceRels) {
    const st = await statFile(rel);
    const ext = path.extname(rel).toLowerCase();
    let type = ext === ".json" ? "JSON 结果" : ext === ".md" ? "Markdown 分析" : ext === ".py" || ext === ".sh" ? "代码" : ext.slice(1).toUpperCase();
    let recordCount = "";
    try {
      if (ext === ".json") {
        const value = await readJson(rel);
        recordCount = Array.isArray(value) ? value.length : "对象";
      }
    } catch {}
    sourceRows.push([type, rel, st.modified, st.sizeKb, recordCount, rel.includes("proco") ? "脚本/预期产物检查" : "本次汇总输入"]);
  }
  writeTable(sourceSheet, 5, 1, ["类型", "相对路径", "修改时间", "大小(KB)", "记录数", "用途"], sourceRows, { A: 16, B: 62, C: 24, D: 12, E: 12, F: 24 });
  sourceSheet.freezePanes.freezeRows(5);
  sourceSheet.tabColor = "#A5A5A5";

  workbook.recalculate();
  const preview = await workbook.render({ sheetName: "概览", range: "A1:K22", scale: 1, format: "png" });
  await fs.writeFile(OUT.replace(/\.xlsx$/, "_预览.png"), new Uint8Array(await preview.arrayBuffer()));
  const xlsx = await SpreadsheetFile.exportXlsx(workbook);
  await xlsx.save(OUT);
  const check = await workbook.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
  console.log(check.ndjson || check);
  console.log(`WROTE ${OUT}`);
}

await build();
