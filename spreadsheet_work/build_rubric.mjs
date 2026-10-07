import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs";
await fs.mkdir(outputDir, { recursive: true });

const workbook = Workbook.create();

const DARK = "#1F4E79";
const HEADER_FILL = "#D9E2F3";
const BORDER_LIGHT = "#D9D9D9";

// ============================================================
// Sheet 1: 四维评判标准
// ============================================================
const s1 = workbook.worksheets.add("四维评判标准");
s1.showGridLines = false;

s1.mergeCells("A1:E1");
s1.getRange("A1").values = [["新版思维评判标准（理论版）· 四维评分锚点"]];
s1.mergeCells("A2:E2");
s1.getRange("A2").values = [[
  "理论依据：Toulmin 论证结构 · SOLO 学习结果结构 · Facione 批判性思维评估 · Mislevy 证据中心设计 · 比较判断理论（Thurstone/ACJ）",
]];

s1.getRange("A4:E4").values = [
  ["维度", "分数", "评分标准描述", "理论依据", "针对的失败模式"],
];

const dims = [
  {
    name: "D1 审题对齐",
    theory:
      "Facione（1990）德尔斐报告：解释与分析技能——先澄清“题目到底问什么”，再检查结论与所问是否一致；Mislevy（2003）证据中心设计：证据必须与任务对齐，答错题型的推理不算证据。",
    bad: "bad2 SARS “except”题：分析过程与最终输出类型错位、错误互相固化；5.1 环己烷醛“closest correct option”：中途把目标换成“找最接近项”。",
    anchors: [
      "正确识别题型（计算/判断/except/结构）并尊重全部限定词；最终主张回答的正是题目所问。",
      "理解题目，但漏掉一个次要限定词。",
      "理解题型，但中途替换目标（如问产物 4 的结构，只论证起始构型）。",
      "回答的是相关但不同的问题（如 except 题按“选正确表述”作答）。",
      "题型反转（except 题却答正确项）或完全答非所问。",
    ],
  },
  {
    name: "D2 证据与正当理由",
    theory:
      "Toulmin（1958）《The Uses of Argument》：论证六要素（主张/数据/正当理由/支援/限定词/反驳）；“完整”=要素齐全而非信息量大——只有数据没有正当理由的链不完整。",
    bad: "bad1 肉桂醛碳数：mathstral 空泛无据、biomedical 靠误差抵消蒙对；idx61 长链数据多但推理错误，被裁判误评高分。",
    anchors: [
      "事实全部正确、用上全部数字与条件、逐条核对选项，并讲清“数据为什么能推出主张”（正当理由）；非平凡推理有支援。",
      "事实基本正确，漏一个非关键条件或选项；正当理由存在但隐晦。",
      "结论看似合理但推理含实质事实/逻辑错误（如误差抵消），或事实正确但无正当理由（罗列数据却没解释数据与主张的联系）。",
      "关键事实/试剂/性质错误导致错误结论。",
      "忽略题干信息或编造事实。",
    ],
  },
  {
    name: "D3 验证与有效性",
    theory:
      "Facione（1990）评估技能（判断前提可信度与推理强度）＋自我调节（发现并纠正错误）；逻辑学 soundness：论证可靠 = 形式有效 ＋ 前提为真。",
    bad: "bad1 qwen 链：“算出 8 个碳，没得选就就近选 10”（结论与推理矛盾）；5.1 “自信但错”的链通过旧版“内部一致”检查；环己烷醛链发现错误却不纠正。",
    anchors: [
      "做了显式检查（结论 vs 推理、结论 vs 选项、数字 vs 题目），并发现/纠正任何失误（自我调节）。",
      "推理与结论一致，但未做显式检查。",
      "自我怀疑但未完全验证；最终结论与推理一致，或内部自洽但建立在错误前提上。",
      "结论直接与自己推理矛盾且未察觉。",
      "无任何验证；结论无依据断言，或自信地给出明显不可能的结果。",
    ],
  },
  {
    name: "D4 结构深度与效率",
    theory:
      "SOLO（Biggs & Collis 1982）：前结构→单点→多点→关联→抽象拓展；“更完整”=结构层级高，不是字数多；Toulmin 相关性：与论证无关的内容是噪音。",
    bad: "idx61 冗长但错误的链被评高分——旧版把“长”误当“完整”；长而散的链只是“多点结构”，远未达到“关联/抽象拓展”。",
    anchors: [
      "抽象拓展：论证完整、检查过替代方案/反驳、无填充。",
      "关联：要点连成连贯论证，仅小缺口，允许轻微冗余。",
      "多点：有多个相关要点但连接论证缺失或有洞；或有一两处重复论证。",
      "单点：只有一个相关要点，或大量绕路/重启、用长度伪装严谨。",
      "前结构：无关、自相矛盾或输出损坏。",
    ],
  },
];

let row = 5;
dims.forEach((d) => {
  const start = row;
  const rows = d.anchors.map((a, i) => [i === 0 ? d.name : "", 5 - i, a, i === 2 ? d.theory : "", i === 2 ? d.bad : ""]);
  s1.getRange(`A${start}:E${start + 4}`).values = rows;
  s1.mergeCells(`A${start}:A${start + 4}`);
  row += 5;
});

s1.mergeCells("A26:E26");
s1.getRange("A26").values = [[
  "注：与基线 pairwise_margin（41.41%）唯一差异 = 本评分标准文本及 1b 输出要求；判定格式（[RESULT]+[PREFERENCE]）、margin 映射（0.85/0.70/0.60/0.50）、归一化与 mean 池化、6 模型 top_k=3、198 题、seed=0 均不变。",
]];

// ---- 样式 ----
s1.getRange("A1").format = {
  fill: DARK,
  font: { bold: true, color: "#FFFFFF", size: 14 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
s1.getRange("A2").format = {
  font: { italic: true, color: "#595959", size: 10 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
s1.getRange("A4:E4").format = {
  fill: HEADER_FILL,
  font: { bold: true, color: DARK },
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
const dataRange = s1.getRange("A5:E24");
dataRange.format = {
  borders: { preset: "all", style: "thin", color: BORDER_LIGHT },
  verticalAlignment: "center",
};
s1.getRange("C5:E24").format = { wrapText: true, horizontalAlignment: "left" };
s1.getRange("B5:B24").format = {
  horizontalAlignment: "center",
  font: { bold: true },
  numberFormat: "0",
};
s1.getRange("A5:A24").format = {
  fill: HEADER_FILL,
  font: { bold: true, color: DARK },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
s1.getRange("A26").format = {
  font: { italic: true, color: "#595959", size: 9 },
  wrapText: true,
  verticalAlignment: "top",
};

s1.getRange("A:A").format.columnWidth = 15;
s1.getRange("B:B").format.columnWidth = 7;
s1.getRange("C:C").format.columnWidth = 68;
s1.getRange("D:E").format.columnWidth = 30;
s1.getRange("A1").format.rowHeight = 34;
s1.getRange("A2").format.rowHeight = 20;
s1.getRange("A4").format.rowHeight = 26;
for (let r = 5; r <= 24; r++) {
  const desc = s1.getRange(`C${r}`).values[0][0] || "";
  const theory = s1.getRange(`D${r}`).values[0][0] || "";
  const bad = s1.getRange(`E${r}`).values[0][0] || "";
  // 各列可容纳的汉字数/行：C 列宽 68 字符≈34 汉字，D/E 列宽 30 字符≈15 汉字
  const lines = Math.max(
    Math.ceil(desc.length / 34),
    Math.ceil(theory.length / 15),
    Math.ceil(bad.length / 15),
    1,
  );
  s1.getRange(`A${r}`).format.rowHeight = Math.min(150, 24 + lines * 15);
}
s1.getRange("A26").format.rowHeight = 30;
s1.freezePanes.freezeRows(4);

// ============================================================
// Sheet 2: 决策规则与输出要求
// ============================================================
const s2 = workbook.worksheets.add("决策规则与输出要求");
s2.showGridLines = false;

s2.mergeCells("A1:D1");
s2.getRange("A1").values = [["决策规则与输出要求"]];
s2.mergeCells("A2:D2");
s2.getRange("A2").values = [[
  "比较判断理论（Thurstone 1927 / Pollitt ACJ 2012）：裁判只做“哪个更好”的整体判断，尺度交给聚合；本组规则用于防止打分趋同与“长度=质量”偏差。",
]];
s2.getRange("A4:D4").values = [["类别", "规则内容", "理论依据", "说明 / 对应问题"]];

const rules = [
  [
    "决策规则 1",
    "正确性优先于结构：可靠而短的链胜过长而错误的链。",
    "比较判断理论（Thurstone/ACJ）",
    "治“冗长骗高分”（idx61）",
  ],
  [
    "决策规则 2",
    "两条链可靠性相当时，优先 SOLO 层级更高者；Warrant（正当理由）与 Rebuttal（反驳）对完整性最重要。",
    "Toulmin 1958 ＋ SOLO 1982",
    "治“长而散”冒充“深”",
  ],
  [
    "决策规则 3",
    "D1 得 1 分的链，不能胜过 D1 得 2 分及以上的链（审题失败一票否决）。",
    "ECD 任务模型 ＋ Facione 解释",
    "治 bad2（SARS except 题）",
  ],
  [
    "决策规则 4",
    "长度和自信不等于正确。",
    "比较判断理论",
    "治打分趋同（85% 分差≤1）",
  ],
  [
    "输出要求（1b）",
    "裁判 feedback 先写每条链的 SOLO 层级（1–5）与缺失的最关键 Toulmin 要素（Claim/Data/Warrant/Backing/Qualifier/Rebuttal），再输出 [RESULT] ＋ [PREFERENCE]。",
    "ACJ 可追溯性",
    "让判断可审计、可复盘",
  ],
];
s2.getRange("A5:D9").values = rules;
s2.mergeCells("A11:D11");
s2.getRange("A11").values = [[
  "控制变量说明：与基线 pairwise_margin 相比，仅替换 ###Score Rubric 文本并新增 1b 输出要求；其余流程（pairwise 判定、margin 加权、归一化、mean 池化、6 模型 top_k=3、198 题全量、seed=0、temperature=0.7）完全一致。",
]];

s2.getRange("A1").format = {
  fill: DARK,
  font: { bold: true, color: "#FFFFFF", size: 14 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
s2.getRange("A2").format = {
  font: { italic: true, color: "#595959", size: 10 },
  wrapText: true,
  verticalAlignment: "center",
};
s2.getRange("A4:D4").format = {
  fill: HEADER_FILL,
  font: { bold: true, color: DARK },
  borders: { preset: "all", style: "thin", color: "#B4C6E7" },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
s2.getRange("A5:D9").format = {
  borders: { preset: "all", style: "thin", color: BORDER_LIGHT },
  wrapText: true,
  verticalAlignment: "center",
};
s2.getRange("A5:A9").format = { font: { bold: true, color: DARK }, horizontalAlignment: "center" };
s2.getRange("A11").format = {
  font: { italic: true, color: "#595959", size: 9 },
  wrapText: true,
  verticalAlignment: "top",
};

s2.getRange("A:A").format.columnWidth = 18;
s2.getRange("B:B").format.columnWidth = 66;
s2.getRange("C:D").format.columnWidth = 30;
s2.getRange("A1").format.rowHeight = 34;
s2.getRange("A2").format.rowHeight = 30;
s2.getRange("A4").format.rowHeight = 24;
for (let r = 5; r <= 9; r++) {
  const text = s2.getRange(`B${r}`).values[0][0] || "";
  s2.getRange(`A${r}`).format.rowHeight = Math.min(84, 36 + Math.ceil(text.length / 33) * 15);
}
s2.getRange("A11").format.rowHeight = 30;
s2.freezePanes.freezeRows(4);

// ============================================================
// Sheet 3: 英文原版 Prompt（代码使用）
// ============================================================
const s3 = workbook.worksheets.add("英文原版 Prompt");
s3.showGridLines = false;
s3.mergeCells("A1:C1");
s3.getRange("A1").values = [["英文原版 rubric（modules.py · pairwise_margin_theory 实际喂给裁判的文本）"]];

const promptLines = [
  "Evaluate the two reasoning chains with a rubric grounded in argumentation theory (Toulmin), learning-outcome structure (SOLO), critical-thinking assessment (Facione), and evidence-centered design (Mislevy). Use the four dimensions below as a checklist to see where the chains differ, then apply the decision rule to pick the winner.",
  "",
  "D1 QUESTION ALIGNMENT (Facione interpretation/analysis; ECD task model).",
  "Does the chain answer the question that was actually asked?",
  "5: correctly identifies the question type (calculation/judgment/except/structure) and respects every qualifier; the final claim answers exactly what was asked.",
  "4: understands the question but misses one minor qualifier.",
  "3: understands the question type but substitutes the goal midway (e.g., asked for the structure of product 4 but argues only the starting configuration).",
  "2: answers a related but different question (e.g., an 'except' question argued as if selecting the correct statement).",
  "1: inverts the question type (an 'except' question answered with the correct item) or answers a completely different question.",
  "",
  "D2 EVIDENCE AND WARRANT (Toulmin Data + Warrant + Backing).",
  "Does the chain use correct evidence AND explain why the evidence supports the claim?",
  "5: every fact correct, all numbers/conditions used, options checked one by one, and the chain states WHY the data support the claim (warrant); non-trivial inferences carry backing.",
  "4: facts mostly correct; one non-critical condition or option missed; warrant present but implicit.",
  "3: conclusion plausible but the reasoning contains a substantive factual or logical error (e.g., errors that cancel out), OR correct facts with no warrant (data listed but the link to the claim is unexplained).",
  "2: a wrong key fact/reagent/property drives the wrong conclusion.",
  "1: ignores the given information or fabricates facts.",
  "",
  "D3 VERIFICATION AND SOUNDNESS (Facione evaluation + self-regulation; logical soundness).",
  "Is the inference valid, are the premises true, and is the conclusion consistent?",
  "5: performs an explicit check - conclusion vs reasoning, conclusion vs options, numbers vs question - and notices/corrects any slip (self-regulation).",
  "4: reasoning and conclusion consistent, but no explicit check performed.",
  "3: second-guesses itself but does not fully verify; final conclusion consistent with the reasoning, or internally consistent but resting on a false premise.",
  "2: the conclusion directly contradicts the chain's own reasoning, unnoticed.",
  "1: no verification; conclusion asserted without support, or an obviously impossible result given confidently.",
  "",
  "D4 STRUCTURAL DEPTH AND EFFICIENCY (SOLO ladder; Toulmin relevance).",
  "How complete is the argument structure, without padding?",
  "5 Extended abstract: argument complete, alternatives/rebuttals checked, no filler.",
  "4 Relational: points linked into a coherent argument; only minor gaps; minor redundancy allowed.",
  "3 Multistructural: several relevant points but the linking argument is missing or gappy; one or two repeated arguments.",
  "2 Unistructural: only one relevant point, or many detours/restarts padding length to fake rigor.",
  "1 Prestructural: irrelevant, self-contradictory, or a corrupted output.",
  "",
  "DECISION RULE (comparative judgement; Thurstone/ACJ):",
  "- Correctness dominates structure: a sound short chain beats a long but wrong one.",
  "- Between two chains of comparable reliability, prefer the higher SOLO level; Warrant and Rebuttal matter most for completeness.",
  "- A chain scoring 1 on D1 cannot be preferred over any chain scoring 2 or above on D1.",
  "- Length and confidence are NOT correctness.",
];

s3.getRange("A3:A41").values = promptLines.map((l) => [l]);
s3.getRange("A1").format = {
  fill: DARK,
  font: { bold: true, color: "#FFFFFF", size: 12 },
  horizontalAlignment: "center",
  verticalAlignment: "center",
};
s3.getRange("A3:A41").format = {
  font: { name: "Courier New", size: 9 },
  verticalAlignment: "top",
  wrapText: false,
};
s3.getRange("A:A").format.columnWidth = 120;
s3.getRange("A1").format.rowHeight = 30;

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(`${outputDir}/新版思维评判标准_理论版.xlsx`);
console.log("saved:", `${outputDir}/新版思维评判标准_理论版.xlsx`);
