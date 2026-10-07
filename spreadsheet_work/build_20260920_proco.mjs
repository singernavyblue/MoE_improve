import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const ROOT = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia";
const OUT = path.join(ROOT, "outputs", "2026-09-20_运行结果_分析结果.xlsx");
const PREVIEW = OUT.replace(/\.xlsx$/, "_预览.png");
const FONT = "Arial";
const C = { navy: "#1F4E78", blue: "#D9EAF7", light: "#EEF5FB", amber: "#FFF2CC", gray: "#F3F4F6", red: "#FCE4D6", border: "#D9E2F3", text: "#1F2937" };

async function exists(rel) {
  try { await fs.stat(path.join(ROOT, rel)); return true; } catch { return false; }
}

async function stat(rel) {
  const s = await fs.stat(path.join(ROOT, rel));
  return [rel, s.mtime.toISOString().replace("T", " ").replace(".000Z", " UTC"), Math.round(s.size / 1024 * 10) / 10];
}

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
  for (const [letter, width] of Object.entries(widths)) sheet.getRange(`${letter}1:${letter}100`).format.columnWidth = width;
}

async function build() {
  const files = [
    "server_work/run_proco_keyverify.py",
    "server_work/run_proco_keyverify_serial.sh",
    "outputs/proco_keyverify_40.json",
    "outputs/proco_keyverify_40_summary.json",
  ];
  const fileRows = [];
  for (const rel of files) {
    if (await exists(rel)) {
      const [p, m, kb] = await stat(rel);
      fileRows.push([p.includes("run_proco") ? "代码" : "结果产物", p, "已发现", m, kb]);
    } else {
      fileRows.push(["结果产物", rel, "未发现", "—", "—"]);
    }
  }
  const logCandidates = ["outputs/proco_keyverify_40.log", "outputs/proco_run.log", "outputs/proco_keyverify.log"];
  const logFound = [];
  for (const rel of logCandidates) if (await exists(rel)) logFound.push(rel);

  const wb = Workbook.create();
  const run = wb.worksheets.add("2026-09-20运行结果");
  const analysis = wb.worksheets.add("2026-09-20分析结果");
  const source = wb.worksheets.add("来源文件");
  for (const s of [run, analysis, source]) {
    s.getRange("A1:Z200").format.font = { name: FONT, size: 10, color: C.text };
    s.getRange("A1:Z200").format.verticalAlignment = "center";
  }

  title(run, "2026-09-20 运行结果", "仅纳入 2026-09-20 当天更新/检查到的 ProCo 运行文件；未混入此前实验结果。");
  run.getRange("A5:B9").values = [
    ["运行项目", "ProCo key-condition verification on frozen GPQA chains"],
    ["日期", "2026-09-20"],
    ["当前状态", "当前工作区未发现当天实际运行结果文件"],
    ["结果范围", "没有可报告的 participant/judge/summary 数值；不能据此判定远端任务成功或失败"],
    ["检查结论", "已发现代码更新；未发现 outputs/proco_keyverify_40.json、outputs/proco_keyverify_40_summary.json 或 ProCo 日志"],
  ];
  run.getRange("A5:A9").format = { fill: C.blue, font: { name: FONT, size: 10, bold: true, color: C.text } };
  run.getRange("B5:B9").format = { fill: C.light, font: { name: FONT, size: 10, color: C.text }, wrapText: true };
  run.getRange("A5:A9").format.columnWidth = 16;
  run.getRange("B5:B9").format.columnWidth = 100;
  run.getRange("A5:B9").format.rowHeight = 34;
  run.getRange("A7:B7").format = { fill: C.amber, font: { name: FONT, size: 10, bold: true, color: C.text }, wrapText: true };
  run.getRange("A11:E11").values = [["文件类别", "文件路径", "状态", "修改时间", "大小(KB)"]];
  run.getRange("A11:E11").format = { fill: C.navy, font: { name: FONT, size: 10, bold: true, color: "#FFFFFF" }, horizontalAlignment: "center" };
  run.getRange("A12:E15").values = fileRows;
  run.getRange("A12:E15").format.borders = { insideHorizontal: { style: "thin", color: C.border }, bottom: { style: "thin", color: C.border } };
  run.getRange("C12:C15").format = { fill: C.green || "#E2F0D9", font: { name: FONT, size: 10, bold: true, color: C.text } };
  run.getRange("C14:C15").format = { fill: C.amber, font: { name: FONT, size: 10, bold: true, color: C.text } };
  for (const [col, w] of Object.entries({ A: 16, B: 58, C: 16, D: 24, E: 12 })) run.getRange(`${col}1:${col}100`).format.columnWidth = w;
  run.getRange("A18:E18").values = [["当天代码定义的输出字段", null, null, null, null]];
  run.getRange("A18:E18").format = { fill: C.blue, font: { name: FONT, size: 11, bold: true, color: C.text } };
  table(run, 19, 1, ["输出/指标", "含义", "代码位置", "当天是否有值", "备注"], [
    ["proco_keyverify_40.json", "每题的冻结三模型链、key condition、verification answer、MATCH/NO_MATCH、P0/P1 裁判结果", "run_proco_keyverify.py", "否", "结果文件未发现"],
    ["proco_keyverify_40_summary.json", "n、stored_goa/baseline_judge/proco_judge 准确率、配对固定/翻转数、McNemar exact p、验证检查计数", "summarize()", "否", "摘要文件未发现"],
    ["participant stage", "每个参与模型识别一个必要条件、生成验证问题、独立作答并给出 MATCH/NO_MATCH", "run_participant()", "否", "无 participant 结果产物"],
    ["judge stage", "Prometheus 对三条冻结链做 pairwise 比较，分别计算 baseline 与带 ProCo evidence 的结果", "run_judge()", "否", "无 judge 结果产物"],
  ], { A: 30, B: 62, C: 24, D: 16, E: 28 });
  run.getRange("B20:B23").format.wrapText = true;
  run.getRange("E20:E23").format.wrapText = true;
  run.getRange("B20:E23").format.rowHeight = 42;
  run.freezePanes.freezeRows(11);
  run.tabColor = C.navy;

  title(analysis, "2026-09-20 分析结果", "分析对象仅为当天更新的 ProCo 代码和当前工作区文件状态，不使用 9 月 9 日以前的实验数值。");
  const rows = [
    ["运行目标", "验证 ProCo key-condition verification 是否能帮助裁判在同一组三模型冻结链中选择更可信的答案链。", "代码 docstring；run_proco_keyverify.py"],
    ["P0 基线", "Prometheus 直接在原始三条链上做 pairwise 选择，得到 baseline_judge。", "_judge_pairwise(..., with_evidence=false)"],
    ["P1 ProCo", "先给每条链生成必要条件验证证据，再让 Prometheus 在含证据的链之间做 pairwise 选择，得到 proco_judge。", "_judge_pairwise(..., with_evidence=true)"],
    ["参与模型", "qwen、mathstral、biomedical_llama；裁判为 prometheus。", "PARTICIPANTS / JUDGE 常量"],
    ["默认输入", "outputs/hard_full_198.json 作为冻结链来源；data/test/GPQA_test.json 作为题目来源；默认 limit=40。", "main() 参数默认值"],
    ["验证流程", "每个参与模型：抽取 key condition → 生成含 [X] 的验证问题 → 独立回答 → 判断 MATCH/NO_MATCH。", "run_participant()"],
    ["裁判流程", "三条链两两比较（M0-M1、M0-M2、M1-M2），A/B/tie 转换为分数，按总分选择 winner。", "_judge_pairwise()"],
    ["统计指标", "各方法准确率、P1 相对 P0 的 fixed/broken 数量、McNemar exact p、验证检查 MATCH/NO_MATCH/UNKNOWN 计数。", "summarize()"],
    ["当前可证结论", "截至当前工作区检查，只有代码更新被记录；没有当天运行产物，因此不能报告 ProCo 的准确率、显著性或效果方向。", "文件存在性检查"],
    ["待补数据", "需要回传/生成 proco_keyverify_40.json、proco_keyverify_40_summary.json，以及可选运行日志后，才能完成数值分析。", "serial runner 默认 OUT/SUMMARY"],
  ];
  table(analysis, 5, 1, ["分析项目", "分析结果", "依据"], rows, { A: 22, B: 100, C: 42 });
  analysis.getRange("B6:B15").format.wrapText = true;
  analysis.getRange("C6:C15").format.wrapText = true;
  analysis.getRange("B6:C15").format.rowHeight = 46;
  analysis.getRange("A13:C14").format = { fill: C.amber, font: { name: FONT, size: 10, bold: true, color: C.text }, wrapText: true };
  analysis.freezePanes.freezeRows(5);
  analysis.tabColor = "#8064A2";

  title(source, "2026-09-20 来源文件", "仅列出当天更新的代码与当天结果文件检查项。");
  const sourceRows = [
    ["代码", "server_work/run_proco_keyverify.py", "已发现", "2026-09-20 21:38"],
    ["代码", "server_work/run_proco_keyverify_serial.sh", "已发现", "2026-09-20 20:55"],
    ["预期结果", "outputs/proco_keyverify_40.json", "未发现", "—"],
    ["预期摘要", "outputs/proco_keyverify_40_summary.json", "未发现", "—"],
    ["预期日志", logFound.length ? logFound.join("；") : "outputs/proco_keyverify_40.log / outputs/proco_run.log / outputs/proco_keyverify.log", logFound.length ? "已发现" : "未发现", "—"],
  ];
  table(source, 5, 1, ["类型", "路径", "状态", "时间"], sourceRows, { A: 16, B: 78, C: 16, D: 24 });
  source.getRange("C8:C9").format = { fill: C.amber, font: { name: FONT, size: 10, bold: true, color: C.text } };
  source.getRange("C10:C10").format = { fill: C.amber, font: { name: FONT, size: 10, bold: true, color: C.text } };
  source.freezePanes.freezeRows(5);
  source.tabColor = "#A5A5A5";

  wb.recalculate();
  const preview = await wb.render({ sheetName: "2026-09-20运行结果", range: "A1:E23", scale: 1, format: "png" });
  await fs.writeFile(PREVIEW, new Uint8Array(await preview.arrayBuffer()));
  const xlsx = await SpreadsheetFile.exportXlsx(wb);
  await xlsx.save(OUT);
  const inspect = await wb.inspect({ kind: "sheet", include: "id,name", maxChars: 4000 });
  console.log(inspect.ndjson || inspect);
  console.log(`WROTE ${OUT}`);
}

await build();
