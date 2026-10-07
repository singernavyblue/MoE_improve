import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia";
const OUT = path.join(ROOT, "outputs", "2026-09-20_运行结果_分析结果.xlsx");
const PREVIEW = OUT.replace(/\.xlsx$/, "_预览.png");
const FONT = "Arial";
const C = { navy: "#1F4E78", blue: "#D9EAF7", light: "#EEF5FB", amber: "#FFF2CC", green: "#E2F0D9", gray: "#F3F4F6", border: "#D9E2F3", text: "#1F2937" };

async function json(rel) { return JSON.parse(await fs.readFile(path.join(ROOT, rel), "utf8")); }
async function stat(rel) { const s = await fs.stat(path.join(ROOT, rel)); return { modified: s.mtime.toISOString().replace("T", " ").replace(".000Z", " UTC"), kb: Math.round(s.size / 1024 * 10) / 10 }; }
function short(v, n = 220) { const raw = v == null ? "" : typeof v === "string" ? v : JSON.stringify(v); const s = raw.replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, ""); return s.length > n ? `${s.slice(0, n - 1)}…` : s; }
function pct(n, d) { return d ? n / d : null; }
function title(sheet, text, sub) {
  sheet.getRange("A1").values = [[text]];
  sheet.getRange("A1").format = { font: { name: FONT, size: 15, bold: true, color: C.text } };
  sheet.getRange("A2").values = [[sub]];
  sheet.getRange("A2").format = { font: { name: FONT, size: 10, italic: true, color: "#5B6573" } };
  sheet.getRange("A3:Z3").format.borders = { bottom: { style: "thin", color: C.navy } };
  sheet.showGridLines = false;
}
function table(sheet, row, col, headers, rows, widths = {}) {
  const matrix = [headers, ...rows];
  sheet.getRangeByIndexes(row - 1, col - 1, matrix.length, headers.length).values = matrix;
  const head = sheet.getRangeByIndexes(row - 1, col - 1, 1, headers.length);
  const body = sheet.getRangeByIndexes(row, col - 1, rows.length, headers.length);
  head.format = { fill: C.navy, font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center", verticalAlignment: "center", wrapText: true };
  body.format = { font: { name: FONT, size: 10, color: C.text }, verticalAlignment: "center", wrapText: false };
  sheet.getRangeByIndexes(row - 1, col - 1, matrix.length, headers.length).format.borders = { insideHorizontal: { style: "thin", color: C.border }, bottom: { style: "thin", color: C.border } };
  for (const [letter, width] of Object.entries(widths)) sheet.getRange(`${letter}1:${letter}2000`).format.columnWidth = width;
}
function correct(r, key) { return (r[key]?.answer ?? r[key]) === r.gold; }
function evidenceFor(r) { return Object.values(r.proco || {}); }
function verdictCount(r) {
  const es = evidenceFor(r);
  return ["MATCH", "NO_MATCH", "UNKNOWN", "MISSING"].map(v => es.filter(e => (e.verdict || "MISSING") === v).length);
}

async function build() {
  const records = await json("outputs/proco_keyverify_40.json");
  const summary = await json("outputs/proco_keyverify_40_summary.json");
  const [resultStat, summaryStat, logStat, pyStat, shStat] = await Promise.all([
    stat("outputs/proco_keyverify_40.json"), stat("outputs/proco_keyverify_40_summary.json"), stat("outputs/proco_keyverify_40.log"), stat("server_work/run_proco_keyverify.py"), stat("server_work/run_proco_keyverify_serial.sh"),
  ]);
  const n = records.length;
  const p0Correct = records.filter(r => correct(r, "baseline_judge")).length;
  const p1Correct = records.filter(r => correct(r, "proco_judge")).length;
  const storedCorrect = records.filter(r => r.stored_goa_answer === r.gold).length;
  const fixed = records.filter(r => !correct(r, "baseline_judge") && correct(r, "proco_judge")).length;
  const broken = records.filter(r => correct(r, "baseline_judge") && !correct(r, "proco_judge")).length;
  const checks = { MATCH: 0, NO_MATCH: 0, UNKNOWN: 0, MISSING: 0 };
  for (const r of records) for (const e of evidenceFor(r)) checks[e.verdict || "MISSING"]++;
  const shifts = records.filter(r => r.baseline_judge.answer !== r.proco_judge.answer).length;

  const wb = Workbook.create();
  const run = wb.worksheets.add("运行汇总");
  const detail = wb.worksheets.add("逐题结果");
  const evidence = wb.worksheets.add("验证证据");
  const analysis = wb.worksheets.add("分析结果");
  const source = wb.worksheets.add("来源文件");
  for (const s of [run, detail, evidence, analysis, source]) {
    s.getRange("A1:Z2000").format.font = { name: FONT, size: 10, color: C.text };
    s.getRange("A1:Z2000").format.verticalAlignment = "center";
  }

  title(run, "2026-09-20 ProCo 运行结果", "正式 40 题最小对照实验；P0=无验证证据裁判，P1=带关键条件验证证据裁判。结果已从远端服务器取回。");
  run.getRange("A5:B12").values = [
    ["实验状态", "已完成 40/40 题；participant、baseline judge、ProCo judge、summary 阶段均已完成"],
    ["固定协议", "同一批冻结三模型初始链；P0/P1 只差是否提供 ProCo 验证证据"],
    ["参与模型", "qwen、mathstral、biomedical_llama；第三方裁判 prometheus"],
    ["标准答案", "仅用于最终评估；未提供给参与模型或裁判"],
    ["P0 基线", `${p0Correct}/${n} = ${pct(p0Correct, n)}`],
    ["P1 ProCo", `${p1Correct}/${n} = ${pct(p1Correct, n)}`],
    ["P1 - P0", `${((pct(p1Correct, n) - pct(p0Correct, n)) * 100).toFixed(1)} pp；转对 ${fixed}，转错 ${broken}，McNemar exact p=${summary.paired_p1_vs_p0.mcnemar_exact_p}`],
    ["验证检查", `MATCH ${checks.MATCH}；NO_MATCH ${checks.NO_MATCH}；UNKNOWN ${checks.UNKNOWN}；MISSING ${checks.MISSING}`],
  ];
  run.getRange("A5:A12").format = { fill: C.blue, font: { name: FONT, size: 10, bold: true, color: C.text } };
  run.getRange("B5:B12").format = { fill: C.light, font: { name: FONT, size: 10, color: C.text }, wrapText: true };
  run.getRange("A5:A12").format.columnWidth = 16; run.getRange("B5:B12").format.columnWidth = 104; run.getRange("A5:B12").format.rowHeight = 34;
  run.getRange("A9:B11").format = { fill: C.green, font: { name: FONT, size: 10, bold: true, color: C.text }, wrapText: true };
  run.getRange("A13:F13").values = [["阶段/产物", "状态", "远端时间", "本地大小(KB)", "记录数", "说明"]];
  run.getRange("A13:F13").format = { fill: C.navy, font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
  run.getRange("A14:F18").values = [
    ["participant: qwen / mathstral / biomedical_llama", "完成", "2026-09-20", "—", "40×3 slots", "每个模型提出关键条件、验证问题并独立作答"],
    ["baseline judge (P0)", "完成", "2026-09-20", "—", "40", "三链三对 pairwise，无 ProCo evidence"],
    ["ProCo judge (P1)", "完成", "2026-09-20", "—", "40", "三链三对 pairwise，带 ProCo evidence"],
    ["outputs/proco_keyverify_40.json", "已取回", "2026-09-20 21:52:51（远端）", resultStat.kb, "40", "逐题原始结果与证据"],
    ["outputs/proco_keyverify_40_summary.json", "已取回", "2026-09-20 21:52:56（远端）", summaryStat.kb, "1", "准确率、配对统计、验证检查计数"],
  ];
  run.getRange("A14:F18").format.borders = { insideHorizontal: { style: "thin", color: C.border }, bottom: { style: "thin", color: C.border } };
  run.getRange("F14:F18").format.wrapText = true;
  for (const [c, w] of Object.entries({ A: 42, B: 104, C: 30, D: 14, E: 14, F: 48 })) run.getRange(`${c}1:${c}100`).format.columnWidth = w;
  run.getRange("A21:B21").values = [["对照统计", "数值"]];
  run.getRange("A21:B21").format = { fill: C.blue, font: { name: FONT, size: 10, bold: true, color: C.text } };
  run.getRange("A22:B27").values = [
    ["stored_goa_answer", `${storedCorrect}/${n} = ${pct(storedCorrect, n)}`],
    ["baseline_judge", `${p0Correct}/${n} = ${pct(p0Correct, n)}`],
    ["proco_judge", `${p1Correct}/${n} = ${pct(p1Correct, n)}`],
    ["fixed: P0 错 → P1 对", fixed],
    ["broken: P0 对 → P1 错", broken],
    ["winner answer changed", shifts],
  ];
  run.getRange("A22:B27").format.borders = { insideHorizontal: { style: "thin", color: C.border }, bottom: { style: "thin", color: C.border } };
  run.freezePanes.freezeRows(13); run.tabColor = C.navy;

  title(detail, "2026-09-20 ProCo 逐题结果", "每题保留 gold、P0/P1 答案、正确性、赢家变化和证据计数；完整原始长文本在 JSON 源文件中。");
  const detailRows = records.map(r => {
    const [m, nm, u, miss] = verdictCount(r);
    const p0 = correct(r, "baseline_judge"); const p1 = correct(r, "proco_judge");
    return [r.idx, r.gold, r.sampled_nodes.join(" / "), r.stored_goa_answer, r.baseline_judge.answer, r.proco_judge.answer, p0, p1, p0 ? (p1 ? "保持正确" : "转错") : (p1 ? "转对" : "保持错误"), r.baseline_judge.winner, r.proco_judge.winner, m, nm, u, miss, r.proco_judge.pairs?.length || 0];
  });
  table(detail, 5, 1, ["题号", "gold", "采样模型", "stored GOA", "P0 答案", "P1 答案", "P0 正确", "P1 正确", "配对变化", "P0 winner", "P1 winner", "MATCH", "NO_MATCH", "UNKNOWN", "MISSING", "P1 pair 数"], detailRows, { A: 9, B: 10, C: 34, D: 14, E: 12, F: 12, G: 10, H: 10, I: 16, J: 11, K: 11, L: 10, M: 12, N: 10, O: 10, P: 10 });
  detail.freezePanes.freezeRows(5); detail.tabColor = "#5B9BD5";

  title(evidence, "2026-09-20 关键条件验证证据", "每行对应一条参与模型的 ProCo 验证记录；长文本已截断展示，原文保留在 proco_keyverify_40.json。");
  const evRows = [];
  for (const r of records) for (const [slot, e] of Object.entries(r.proco || {})) {
    evRows.push([r.idx, slot, r.sampled_nodes[Number(slot)] || "", e.key_type || "", short(e.key_condition), short(e.verification_question), short(e.verification_answer), e.verdict || "MISSING", e.error || "", short(e.match_reason || e.solve_reason, 160)]);
  }
  table(evidence, 5, 1, ["题号", "slot", "模型", "key type", "关键条件", "验证问题", "独立回答", "verdict", "错误", "判定理由"], evRows, { A: 9, B: 8, C: 22, D: 14, E: 42, F: 54, G: 42, H: 12, I: 28, J: 38 });
  evidence.getRange(`E6:G${evRows.length + 5}`).format.wrapText = true;
  evidence.getRange(`I6:J${evRows.length + 5}`).format.wrapText = true;
  evidence.getRange(`E6:J${evRows.length + 5}`).format.rowHeight = 42;
  evidence.freezePanes.freezeRows(5); evidence.tabColor = "#A5A5A5";

  title(analysis, "2026-09-20 ProCo 分析结果", "分析仅基于本次 40 题正式配对结果，不混入此前日期的实验数字。");
  const analysisRows = [
    ["核心结果", `P0 无证据裁判为 ${p0Correct}/${n}（${(pct(p0Correct, n) * 100).toFixed(1)}%）；P1 ProCo 证据裁判为 ${p1Correct}/${n}（${(pct(p1Correct, n) * 100).toFixed(1)}%）。`, "proco_keyverify_40_summary.json"],
    ["方向", `P1 相比 P0 为 ${(pct(p1Correct, n) - pct(p0Correct, n) * 1) * 100} pp；转对 ${fixed}，转错 ${broken}。`, "summary.paired_p1_vs_p0"],
    ["显著性", `McNemar exact p=${summary.paired_p1_vs_p0.mcnemar_exact_p}；在 n=${n} 的小样本下，观察到的差异不显著。`, "summary.paired_p1_vs_p0"],
    ["验证信号", `MATCH=${checks.MATCH}、NO_MATCH=${checks.NO_MATCH}、UNKNOWN=${checks.UNKNOWN}、MISSING=${checks.MISSING}；存在反对性证据，验证阶段不是全量自我确认。`, "summary.verification_checks + 逐题 JSON"],
    ["可支持的判断", "本次结果不支持“ProCo 在该 40 题配对上提升裁判准确率”的结论；点估计上 P1 反而低于 P0 2.5pp，但置信证据不足以判断稳定方向。", "配对统计"],
    ["配对一致性", `${shifts}/40 题的 P0/P1 最终答案发生变化；其中 P0 对→P1 错 4 题，P0 错→P1 对 3 题。`, "逐题结果"],
    ["池内限制", `29/40 题的三条初始答案中包含 gold；P0 在池内 15/29、池外 0/11，P1 在池内 14/29、池外 0/11。三条链全错时，裁判证据无法凭空恢复 gold。`, "逐题 initial_answers + gold"],
    ["证据质量限制", "14 条 evidence 记录带有 error 或未形成标准 verdict，且存在 1 条 UNKNOWN；正式分析应把缺失证据作为质量问题保留，而不能当作 MATCH。", "逐题 proco 字段"],
    ["下一步建议", "若要验证机制是否在更大范围有效，建议扩大到预注册的题目数量，并按 gold 是否在初始池内分层报告；同时单独统计证据生成失败率与裁判对 NO_MATCH 的响应。", "本次结果的可复现性建议"],
  ];
  table(analysis, 5, 1, ["分析项目", "结论", "依据"], analysisRows, { A: 20, B: 104, C: 40 });
  analysis.getRange("B6:C14").format.wrapText = true; analysis.getRange("B6:C14").format.rowHeight = 48;
  analysis.getRange("A6:B8").format = { fill: C.green, font: { name: FONT, size: 10, bold: true, color: C.text }, wrapText: true };
  analysis.freezePanes.freezeRows(5); analysis.tabColor = "#8064A2";

  title(source, "2026-09-20 来源文件", "本工作簿只纳入本次 ProCo 正式运行的代码、结果 JSON、摘要 JSON 和运行日志。");
  const srcRows = [
    ["本地代码", "server_work/run_proco_keyverify.py", "已发现", pyStat.modified, pyStat.kb],
    ["本地启动脚本", "server_work/run_proco_keyverify_serial.sh", "已发现", shStat.modified, shStat.kb],
    ["远端正式结果", "outputs/proco_keyverify_40.json", "已取回", "2026-09-20 21:52:51（远端）", resultStat.kb],
    ["远端正式摘要", "outputs/proco_keyverify_40_summary.json", "已取回", "2026-09-20 21:52:56（远端）", summaryStat.kb],
    ["远端运行日志", "outputs/proco_keyverify_40.log（本地副本）", "已取回", "2026-09-20 21:52:57（远端）", logStat.kb],
  ];
  table(source, 5, 1, ["类型", "路径", "状态", "时间", "大小(KB)"], srcRows, { A: 18, B: 62, C: 14, D: 32, E: 14 });
  source.freezePanes.freezeRows(5); source.tabColor = "#A5A5A5";

  wb.recalculate();
  const preview = await wb.render({ sheetName: "运行汇总", range: "A1:F27", scale: 1, format: "png" });
  await fs.writeFile(PREVIEW, new Uint8Array(await preview.arrayBuffer()));
  const xlsx = await SpreadsheetFile.exportXlsx(wb); await xlsx.save(OUT);
  const check = await wb.inspect({ kind: "sheet", include: "id,name", maxChars: 5000 }); console.log(check.ndjson || check);
  console.log(`WROTE ${OUT}`);
}

await build();
