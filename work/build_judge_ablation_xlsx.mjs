import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const OUT = "outputs/四维裁判与DeepSeek对照.xlsx";

const INK = "#0B2545";
const HEADER_FILL = "#E8EEF5";
const NOTE_FILL = "#F4F6F9";
const GOOD_FILL = "#E3F2E4";
const BAD_FILL = "#FBE9E7";
const GOLD_FILL = "#FFF3D6";
const BORDER = "#C7D3E0";
const BODY = "#1A1A1A";
const MUTED = "#4A5A6A";


function styleSheet(sheet, nCols, colWidths, height) {
  const all = sheet.getRange(`A1:C${Math.max(30, height + 5)}`);
  all.format.font = { name: "Calibri", size: 11, color: BODY };
  all.format.wrapText = true;
  all.format.verticalAlignment = "top";
  for (let c = 0; c < colWidths.length; c++) {
    const letter = String.fromCharCode(65 + c);
    sheet.getRange(`${letter}1:${letter}${Math.max(30, height + 5)}`).format.columnWidth = colWidths[c];
  }
}


function titleBand(sheet, text, row = 1, span = "C") {
  const r = sheet.getRange(`A${row}:${span}${row}`);
  r.merge();
  r.values = [[text]];
  r.format.fill = INK;
  r.format.font = { color: "#FFFFFF", bold: true, size: 14 };
  r.format.rowHeight = 28;
  r.format.verticalAlignment = "center";
  return row + 1;
}


function metaLine(sheet, text, row) {
  const r = sheet.getRange(`A${row}:C${row}`);
  r.merge();
  r.values = [[text]];
  r.format.font = { size: 10, color: MUTED };
  r.format.rowHeight = 18;
  return row + 1;
}


function sectionHead(sheet, text, row) {
  const r = sheet.getRange(`A${row}:C${row}`);
  r.merge();
  r.values = [[text]];
  r.format.fill = HEADER_FILL;
  r.format.font = { bold: true, color: INK, size: 12 };
  r.format.rowHeight = 22;
  return row + 1;
}


function table(sheet, row, headers, rows, widths, opts = {}) {
  const nCols = headers.length;
  const header = sheet.getRange(`A${row}:${String.fromCharCode(64 + nCols)}${row}`);
  header.values = [headers];
  header.format.fill = HEADER_FILL;
  header.format.font = { bold: true, color: INK };
  header.format.horizontalAlignment = "center";
  header.format.verticalAlignment = "center";
  header.format.borders = { preset: "all", style: "thin", color: BORDER };
  header.format.rowHeight = 22;

  rows.forEach((r, i) => {
    const rr = row + 1 + i;
    const range = sheet.getRange(`A${rr}:${String.fromCharCode(64 + nCols)}${rr}`);
    range.values = [r];
    range.format.borders = { preset: "all", style: "thin", color: BORDER };
    range.format.font = { size: 10, color: BODY };
    range.format.verticalAlignment = "top";
    if (opts.highlightRow === i) {
      range.format.fill = GOOD_FILL;
      range.format.font = { size: 10, bold: true, color: INK };
    } else if (opts.badRows && opts.badRows.includes(i)) {
      range.format.fill = BAD_FILL;
    }
    const len = Math.max(...r.map((v) => String(v ?? "").length));
    range.format.rowHeight = Math.min(90, Math.max(24, Math.ceil(len / 45) * 15 + 10));
  });

  const total = row + rows.length + 1;
  const cols = String.fromCharCode(64 + nCols);
  for (let c = 0; c < nCols; c++) {
    const letter = String.fromCharCode(65 + c);
    sheet.getRange(`${letter}1:${letter}${total + 10}`).format.columnWidth = widths[c];
  }
  return total;
}


function noteLine(sheet, text, row, fill = NOTE_FILL, color = BODY) {
  const r = sheet.getRange(`A${row}:C${row}`);
  r.merge();
  r.values = [[text]];
  r.format.fill = fill;
  r.format.font = { size: 10, color };
  r.format.borders = { preset: "all", style: "thin", color: BORDER };
  const lines = Math.max(1, Math.ceil(text.length / 55));
  r.format.rowHeight = lines * 16 + 12;
  return row + 1;
}


const wb = Workbook.create();

// ============ Sheet 1: 全量对比 ============
{
  const s = wb.worksheets.add("四维裁判全量对比");
  styleSheet(s, 3, [22, 14, 42], 40);
  let r = titleBand(s, "四维裁判版 vs pairwise margin 基线（全量 198 题 GPQA）");
  r = metaLine(s, "配置：6 模型 + Prometheus-7B 裁判 ｜ top_k=3 ｜ mean 池化 ｜ 仅裁判 rubric 变化：单条标准 → ClawTrack 四维标准", r);
  r = sectionHead(s, "总准确率", r);
  r = table(s, r, ["变体", "全量 198 题", "严格子集（176 题）"],
    [
      ["pairwise margin 基线", "41.41%（82）", "40.91%（72）"],
      ["四维裁判版", "35.86%（71）", "35.80%（63）"],
      ["差异", "-5.55pp", "-5.11pp"],
    ],
    [22, 14, 42],
    { badRows: [1, 2] });
  r += 1;
  r = sectionHead(s, "严格子集翻转明细", r);
  r = table(s, r, ["变体", "翻转", "说明"],
    [
      ["四维裁判版 vs 基线", "转对 14 题", "化学 8 / 物理 5 / 其他 1"],
      ["四维裁判版 vs 基线", "转错 23 题", "物理 11 / 化学 9 / 生物 1 / 其他 2 —— 净转错 9"],
      ["bad1（idx 1）肉桂醛碳数", "基线 ✓ / 四维 ✓", "gold=C，两版都答对"],
      ["bad2（idx 10）SARS except", "基线 ✗ / 四维 ✗", "gold=D，基线 A、四维 C，均错"],
      ["bad3（idx 27）立体化学", "基线 ✗ / 四维 ✗", "gold=B，两版都答 A"],
    ],
    [22, 24, 32],
    { badRows: [1] });
  r += 1;
  r = noteLine(s, "结论：四维标准直接作为 pairwise rubric 丢给 7B 裁判不升反降（-5.55pp），转错（23）显著多于转对（14），三个经典 bad case 均未修复。", r, BAD_FILL, "#7A2E2E");
}

// ============ Sheet 2: 40 题裁判消融 ============
{
  const s = wb.worksheets.add("40题裁判消融");
  styleSheet(s, 3, [34, 16, 30], 50);
  let r = titleBand(s, "裁判消融：Prometheus-7B vs DeepSeek-V3（同一批 40 题、同一批初始链）");
  r = metaLine(s, "样本：40 题（化学 18 / 物理 12 / 其他 6 / 生物 4，基线对 22 / 错 18，含 19 个翻转题）｜ 任务：对每题 3 条初始链做四维 pairwise 打分，选权重最高的链", r);
  r = sectionHead(s, "选链正确率", r);
  r = table(s, r, ["方法", "正确数 / 题数", "正确率"],
    [
      ["3 条链平均（= 均匀随机选链期望）", "51 / 120", "42.50%"],
      ["多数投票（32 题有明确多数）", "16 / 32", "50.00%"],
      ["Prometheus-7B 四维选链", "15 / 40", "37.50%"],
      ["DeepSeek-V3 四维选链", "15 / 40", "37.50%"],
    ],
    [34, 16, 30],
    { badRows: [2, 3] });
  r += 1;
  r = sectionHead(s, "裁判行为", r);
  r = table(s, r, ["指标", "数值", "说明"],
    [
      ["两个裁判 top 链一致率", "40 / 40（100%）", "不同模型、不同参数量，选链结果完全相同"],
      ["Prometheus 解析兜底", "4 / 120 对", "输出格式不稳定"],
      ["DeepSeek-V3 解析兜底", "0 / 120 对", "严格输出 [RESULT]/[PREFERENCE]"],
      ["两裁判 vs 随机", "-5.00pp", "均低于均匀随机选链期望 42.50%"],
    ],
    [34, 18, 34]);
  r += 1;
  r = noteLine(s, "结论：① 瓶颈不在裁判能力——DeepSeek-V3 与 Prometheus-7B 结果完全一致（37.50%，且 40/40 选同一条链）；② 四维 pairwise 选链在 GPQA 上是负信息（低于随机）；③ 裁判被链的表面特征（长度/结构化/自信）驱动，而这些特征与结论正确性负相关（错误链平均长 252 字符）。", r, GOLD_FILL, "#7A5A00");
}

// ============ Sheet 3: 关键结论 ============
{
  const s = wb.worksheets.add("关键结论");
  styleSheet(s, 3, [30, 66], 40);
  let r = titleBand(s, "实验路线判定");
  r = metaLine(s, "围绕“把 ClawTrack 四维标准接入 GoA 实验”的三轮验证结论", r);
  r = sectionHead(s, "假设验证", r);
  r = table(s, r, ["假设", "验证结果", "结论"],
    [
      ["四维 rubric 直接替换 pairwise 裁判标准能提升", "全量 41.41% → 35.86%（-5.55pp）", "❌ 不成立，反而下降"],
      ["失败原因是 7B 裁判能力不足", "DeepSeek-V3 同样 37.50%，40/40 选链一致", "❌ 排除，与裁判规模无关"],
      ["四维 pairwise 选链信号在 GPQA 上有信息量", "两裁判均低于随机期望（37.5% < 42.5%）", "❌ 负信息，表面特征驱动"],
    ],
    [30, 42, 20]);
  r += 1;
  r = sectionHead(s, "四维标准的有效用途", r);
  r = table(s, r, ["用途", "做法", "状态"],
    [
      ["诊断 / 画像", "对每条链输出四维 profile，统计错误集中在哪一维", "可立即执行（已有 116 条错误链）"],
      ["过滤坏链", "D3≤2（结论与推理矛盾）的链强制降权/剔除，不用于选最优", "需 30~50 题小样本验证"],
      ["人工打标标准", "作为人工标注手册 + 蒸馏成 skill 的锚点", "已产出 Excel 版标准"],
      ["直接作为 pairwise rubric", "让裁判自己综合四维判断胜负", "❌ 已验证失败，放弃"],
    ],
    [30, 42, 20]);
}

await fs.mkdir("outputs", { recursive: true });
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(OUT);
console.log("saved", OUT);
