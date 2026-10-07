import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const OUT = "outputs/裁判标准_四维表格.xlsx";

const INK = "#0B2545";
const HEADER_FILL = "#E8EEF5";
const NOTE_FILL = "#F4F6F9";
const GOLD_FILL = "#FFF3D6";
const BORDER = "#C7D3E0";
const BODY = "#1A1A1A";
const MUTED = "#4A5A6A";

const DIMS = [
  {
    name: "维度1 目标对齐",
    title: "维度 1｜目标对齐（审题对齐）— 对应 ClawTrack goal alignment",
    desc: "判断这条链是否在回答题目真正问的东西，而不是答了“看起来相关”的东西。",
    weight: "评分角色：乘法门（一票否决）—— 目标对齐 ≤2 分时，整条链最高只能给 2 分，不进入后续维度加权。",
    rows: [
      ["5", "准确识别题目类型（计算/判断/except/选出结构），问题中的每一个限定词都被遵守", "正确的基线链（如 idx 1 基线答 C 的链：三步碳数变化逐项加）"],
      ["4", "识别了题目类型，但忽略了一个次要限定词（如“在低温下”）", "—"],
      ["3", "问题类型理解正确，但中途偷换了目标（如把“合成路线”换成“找最接近的”）", "idx 61 最终回答：“the closest correct option … despite the incorrect final step”——目标从“找正确路线”变成“找最接近的”"],
      ["2", "把题目问的东西答成了相邻但不同的问题", "bad3（idx 27）：题目问“产物 4 的结构”，模型却只论证“初始 (S) 构型保留”就选 A"],
      ["1", "理解反了题目类型", "bad2（idx 10）：except 题（选出唯一正确项）三个模型都输出唯一错误项 A；bad1 的 mathstral：“这些反应不改变碳数”——把“问产物 3 有几个碳”做成了“问碳数变不变”"],
    ],
    tip: "判定口诀：先问“题目到底要什么”，再看推理链的结论落点。结论落点错位 → 直接按 1~2 档处理，不进入后续维度加权。",
  },
  {
    name: "维度2 信息利用",
    title: "维度 2｜信息利用（知识/条件/选项）— 对应 ClawTrack information utilization",
    desc: "判断这条链是否正确调用领域知识、是否用全了题干条件、是否逐条核对选项。",
    weight: "评分角色：核心知识维（权重高）—— 关键事实断言的正确性决定整条链可信度。",
    rows: [
      ["5", "每一步引用的化学/物理/生物事实正确，题干所有数字和条件都被用到，且与选项逐条核对一致", "基线答对的链（如 idx 23 正确链推出 C₂H₄、氢原子总数与选项一致）"],
      ["4", "事实基本正确，遗漏一个非关键条件或未逐一核对选项", "—"],
      ["3", "结论对但推理里有实质事实错误（错误恰好互相抵消）", "bad1 的 biomedical 链：“Cinnamaldehyde has 10 carbon atoms … one carbon added … 11”——起点碳数说错（实际 9→10），但加减抵消后结论 C 正确"],
      ["2", "调用了错误的关键知识/试剂性质，导致结论错", "bad1 的 qwen 链：把 Corey–Chaykovsky 试剂（二甲亚砜叶立德）当成烯烃复分解，推出“碳数不变=10”；bad1 的 mathstral 链：“These reactions do not change the number of carbon atoms”"],
      ["1", "基本没有用题干信息，直接编造或答非所问", "bad3 的 biomedical 链：“The products of cross-nucleophilic coupling reactions are the inverse of the starting materials”——术语和机制都是编的"],
    ],
    tip: "判定口诀：把推理链里的每个“事实断言”单独拎出来问“这是真的吗？这是题目给的吗？”错一个关键断言且结论依赖它 → 2 档；错一个但结论没依赖它（误差抵消）→ 3 档。",
  },
  {
    name: "维度3 结果验证",
    title: "维度 3｜结果验证（自我验证）— 对应 ClawTrack result verification，本实验最重要的一维",
    desc: "判断这条链是否在提交结论前做了一致性检查：结论是否被自己的推理支持、是否与选项吻合、出现矛盾时是否停下来。",
    weight: "评分角色：系统瓶颈维（权重最高）—— ClawTrack 证明这是所有模型的共同短板，本实验的 bad2 / idx 61 均属此类。",
    rows: [
      ["5", "明确做了一致性检查：重新核对结论与推理、结论与选项、数字与题干", "基线答对的链（如 idx 23 正确链：推出氢总数后与每个选项核对）"],
      ["4", "推理与结论一致，但未显式做核对（没有验证动作）", "—"],
      ["3", "中途自我怀疑、修正过，但验证不彻底，最终结论仍与推理一致", "bad3 的 mathstral 链：T→S 改回 B 并写 “The correct structure … is (B), with a confidence level of 0.9”，但没发现“自己 S→T 改口 A 又改回 B”本身就是危险信号"],
      ["2", "结论与自己的推理直接矛盾，且未察觉", "bad2（idx 10）：三个模型都逐条判出“B/C/D 均正确”，却输出“A 是唯一错误项”；idx 61：“This is problematic because cyclohexane cannot be oxidized to cyclohexanal” 仍选 C；bad1 的 qwen：“算 8 个碳 → 选项没有 8 → 就近选 10”"],
      ["1", "无任何验证，直接输出结论；或自信地输出明显不可能的结果", "idx 115：NMR 推出结构后没有核对 “two signals/triplet/quartet” 是否匹配；idx 6：算阈值时 “given the average photon energy…” 直接猜 B"],
    ],
    tip: "判定口诀：问三个问题——① 结论字母在推理文本里出现过吗？② 推理给出的判据（如“B/C/D 都对”）和结论一致吗？③ 模型有没有任何一句“检查/核对/确认”动作？①②③ 全否 → 1~2 档。",
  },
  {
    name: "维度4 效率",
    title: "维度 4｜效率（简洁性）— 对应 ClawTrack efficiency，次要维",
    desc: "判断这条链有没有无关绕路、重复论证、用大量文字掩盖知识空白。",
    weight: "评分角色：次要维（建议权重 ≤0.1）—— 只用于“扣冗余”，禁止因为链短就加分（短而错和长而错同等错）。",
    rows: [
      ["5", "直接、完整、无废话，每句话都在推进推理", "基线答对的链"],
      ["4", "有小段冗余但不影响理解", "—"],
      ["3", "有 1~2 处重复论证或无进展段落", "—"],
      ["2", "大量绕路：复述题目、反复重新开始、用长度堆“严谨感”", "错误链平均比正确链长 252 字符；idx 114（量子力学）用大段守恒方程推导却没有核对初态条件"],
      ["1", "纯复述题目+无内容结论；或严重损坏的输出", "bad3 的 biomedical 消息传递输出 “Model 0 (moderate relevance)”——只有一句残片"],
    ],
    tip: "注意：效率维只用于“扣冗余”，禁止因为链短就加分（短而错和长而错同等错）。这条维在单轮 GPQA 上诊断价值最低，建议权重不超过 0.1。",
  },
];

function styleSheet(sheet, nCols, colWidths) {
  const all = sheet.getRange(`A1:C${Math.max(20, nCols + 12)}`);
  all.format.font = { name: "Calibri", size: 11, color: BODY };
  all.format.wrapText = true;
  all.format.verticalAlignment = "top";
  for (let c = 0; c < colWidths.length; c++) {
    const letter = String.fromCharCode(65 + c);
    sheet.getRange(`${letter}1:${letter}60`).format.columnWidth = colWidths[c];
  }
}

function buildDimSheet(wb, dim) {
  const sheet = wb.worksheets.add(dim.name);
  styleSheet(sheet, 3, [8, 52, 66]);

  // title band
  const tRange = sheet.getRange("A1:C1");
  tRange.merge();
  tRange.values = [[dim.title]];
  tRange.format.fill = INK;
  tRange.format.font = { color: "#FFFFFF", bold: true, size: 14 };
  tRange.format.rowHeight = 28;
  tRange.format.verticalAlignment = "center";

  // description
  const dRange = sheet.getRange("A2:C2");
  dRange.merge();
  dRange.values = [[dim.desc]];
  dRange.format.font = { size: 11, color: MUTED, italic: true };
  dRange.format.rowHeight = 20;

  // weight note
  const wRange = sheet.getRange("A3:C3");
  wRange.merge();
  wRange.values = [[dim.weight]];
  wRange.format.fill = NOTE_FILL;
  wRange.format.font = { size: 10, bold: true, color: INK };
  wRange.format.rowHeight = 20;

  // header row
  const header = sheet.getRange("A4:C4");
  header.values = [["档位", "行为锚点", "本实验真实例子"]];
  header.format.fill = HEADER_FILL;
  header.format.font = { bold: true, color: INK, size: 11 };
  header.format.horizontalAlignment = "center";
  header.format.verticalAlignment = "center";
  header.format.borders = { preset: "all", style: "thin", color: BORDER };
  header.format.rowHeight = 22;

  // tier rows (5 -> 1)
  const startRow = 5;
  dim.rows.forEach((row, i) => {
    const r = startRow + i;
    const range = sheet.getRange(`A${r}:C${r}`);
    range.values = [row];
    range.format.borders = { preset: "all", style: "thin", color: BORDER };
    range.format.font = { size: 10, color: BODY };
    range.format.verticalAlignment = "top";
    const a = sheet.getRange(`A${r}`);
    a.format.horizontalAlignment = "center";
    a.format.font = { bold: true, size: 12, color: INK };
    a.format.fill = i === 0 ? "#DCEAF7" : (i === dim.rows.length - 1 ? "#F7DCDC" : "#FFFFFF");
    // estimate height from longest wrapped content
    const len = Math.max(row[1].length, row[2].length);
    const lines = Math.max(1, Math.ceil(len / 26));
    range.format.rowHeight = Math.min(150, Math.max(34, lines * 15 + 10));
  });

  // tip row
  const tipRow = startRow + dim.rows.length;
  const tipRange = sheet.getRange(`A${tipRow}:C${tipRow}`);
  tipRange.merge();
  tipRange.values = [[dim.tip]];
  tipRange.format.fill = GOLD_FILL;
  tipRange.format.font = { size: 10, color: "#7A5A00" };
  tipRange.format.borders = { preset: "all", style: "thin", color: "#E4D5A8" };
  const tipLines = Math.max(1, Math.ceil(dim.tip.length / 60));
  tipRange.format.rowHeight = tipLines * 16 + 12;

  sheet.freezePanes.freezeRows(4);
  return sheet;
}

function buildOverviewSheet(wb) {
  const sheet = wb.worksheets.add("使用说明");
  styleSheet(sheet, 2, [22, 104]);

  const tRange = sheet.getRange("A1:B1");
  tRange.merge();
  tRange.values = [["GPQA 推理链四维裁判标准（ClawTrack 适配版）"]];
  tRange.format.fill = INK;
  tRange.format.font = { color: "#FFFFFF", bold: true, size: 15 };
  tRange.format.rowHeight = 30;

  const meta = sheet.getRange("A2:B2");
  meta.merge();
  meta.values = [["日期：2026-08-26 ｜ 数据集：GPQA Diamond（198 题）｜ 基线：6 模型 + pairwise margin 裁判（41.41%）｜ 依据：ClawTrack arXiv:2607.28037 §3.3 / §3.4"]];
  meta.format.font = { size: 10, color: MUTED };
  meta.format.rowHeight = 18;

  const h1 = sheet.getRange("A4:B4");
  h1.merge();
  h1.values = [["评分总规则（照搬 ClawTrack 三原则）"]];
  h1.format.fill = HEADER_FILL;
  h1.format.font = { bold: true, color: INK, size: 12 };
  h1.format.rowHeight = 22;

  const rules = [
    "1. 每维独立打分 1~5，四维都要出分，禁止只给一个总分。",
    "2. 目标对齐是乘法门：目标对齐 ≤2 时，整条链最高只能给 2 分（一票否决）。",
    "3. 反光环提示：打分开写前必须自查“我是不是因为整体印象给了相同分？长度和自信不是正确性”。",
  ];
  rules.forEach((r, i) => {
    const row = 5 + i;
    const range = sheet.getRange(`A${row}:B${row}`);
    range.merge();
    range.values = [[r]];
    range.format.font = { size: 11, color: BODY };
    range.format.rowHeight = 18;
  });

  const h2 = sheet.getRange("A9:B9");
  h2.merge();
  h2.values = [["四维权重与评分角色"]];
  h2.format.fill = HEADER_FILL;
  h2.format.font = { bold: true, color: INK, size: 12 };
  h2.format.rowHeight = 22;

  const weightHeader = sheet.getRange("A10:B10");
  weightHeader.values = [["维度", "评分角色与权重"]];
  weightHeader.format.fill = NOTE_FILL;
  weightHeader.format.font = { bold: true, color: INK };
  weightHeader.format.borders = { preset: "all", style: "thin", color: BORDER };
  weightHeader.format.rowHeight = 20;

  const weightRows = [
    ["维度1 目标对齐", "乘法门（一票否决）：理解错题目类型 → 整链归零"],
    ["维度2 信息利用", "核心知识维（高权重）：关键事实断言正确性决定可信度"],
    ["维度3 结果验证", "系统瓶颈维（最高权重）：结论-推理一致性检查，本实验 bad2 / idx 61 的病灶"],
    ["维度4 效率", "次要维（≤0.1）：只扣冗余，不因短加分"],
  ];
  weightRows.forEach((r, i) => {
    const row = 11 + i;
    const range = sheet.getRange(`A${row}:B${row}`);
    range.values = [r];
    range.format.borders = { preset: "all", style: "thin", color: BORDER };
    range.format.font = { size: 10 };
    range.format.verticalAlignment = "top";
    range.format.rowHeight = 30;
  });

  const h3 = sheet.getRange("A16:B16");
  h3.merge();
  h3.values = [["使用方式"]];
  h3.format.fill = HEADER_FILL;
  h3.format.font = { bold: true, color: INK, size: 12 };
  h3.format.rowHeight = 22;

  const usage = [
    "1. 每个维度一张工作表：维度1~维度4，含 5 档行为锚点 + 本实验真实例子 + 判定口诀。",
    "2. 标注时对每条推理链依次打四维分（1~5），先看目标对齐是否 ≤2（一票否决），再评其余三维。",
    "3. 锚点不够具体时（不同 judge 打分一致性低），用 116 条错误链补充更多真实例子。",
    "4. 对照 ClawTrack：四维接近正交（r=0.49~0.67），结果验证是系统性瓶颈，评分时应避免各维同分（反光环）。",
  ];
  usage.forEach((r, i) => {
    const row = 17 + i;
    const range = sheet.getRange(`A${row}:B${row}`);
    range.merge();
    range.values = [[r]];
    range.format.font = { size: 11 };
    range.format.rowHeight = 20;
  });

  sheet.freezePanes.freezeRows(4);
  return sheet;
}

const wb = Workbook.create();
buildOverviewSheet(wb);
DIMS.forEach((dim) => buildDimSheet(wb, dim));

await fs.mkdir("outputs", { recursive: true });
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(OUT);
console.log("saved", OUT);
