import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectDir = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia";
const outputDir = `${projectDir}/outputs/01a0bf30-719f-7601-bf05-d9d52b24c4d2`;
const outPath = `${outputDir}/2026-09-21_共享验证改进_10题验证实验.xlsx`;
const summary = JSON.parse(await fs.readFile(`${projectDir}/outputs/proco_keyverify_shared_10_v3_summary.json`, "utf8"));
const records = JSON.parse(await fs.readFile(`${projectDir}/outputs/proco_keyverify_shared_10_v3.json`, "utf8"));

const wb = Workbook.create();
const overview = wb.worksheets.add("实验结论");
const items = wb.worksheets.add("逐题结果");
const evidence = wb.worksheets.add("共享验证记录");
const protocol = wb.worksheets.add("协议与代码");

const font = "Arial";
const navy = "#1F4E78";
const paleBlue = "#EAF2F8";
const paleYellow = "#FFF2CC";
const paleGreen = "#E2F0D9";
const paleRed = "#FCE4D6";
const lightGray = "#F3F6F9";
const border = { preset: "all", style: "thin", color: "#D9E2F3" };

function setup(sheet) {
  sheet.showGridLines = false;
}

function title(sheet, text, endCol) {
  sheet.getRange("A2").values = [[text]];
  sheet.getRange("A2").format.font = { name: font, size: 14, bold: true, color: navy };
  sheet.getRange(`A3:${endCol}3`).format.borders = { bottom: { style: "thin", color: navy } };
}

function header(sheet, range) {
  sheet.getRange(range).format = {
    fill: navy,
    font: { name: font, size: 10, bold: true, color: "#FFFFFF" },
    horizontalAlignment: "center",
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "all", style: "thin", color: "#FFFFFF" },
  };
}

function truncate(value, n = 700) {
  const s = value == null ? "" : String(value);
  return s.length > n ? `${s.slice(0, n)}…` : s;
}

function isCorrect(answer, gold) {
  return answer === gold ? 1 : 0;
}

function consensus(rec, slot) {
  const entries = rec.shared_proco?.[String(slot)] || {};
  const verdicts = Object.values(entries).map((x) => x.verdict);
  if (verdicts.length === 2 && verdicts.every((x) => x === "NO_MATCH")) return "CONFIRMED_NO_MATCH";
  if (verdicts.length === 2 && verdicts.every((x) => x === "MATCH")) return "CONFIRMED_MATCH";
  if (verdicts.length) return "MIXED_OR_INSUFFICIENT";
  return "NO_EVIDENCE";
}

let verifierCalls = 0;
let evidenceRows = [];
for (const rec of records) {
  for (let slot = 0; slot < 3; slot += 1) {
    const entries = rec.shared_proco?.[String(slot)] || {};
    for (const [verifier, e] of Object.entries(entries)) {
      verifierCalls += 1;
      evidenceRows.push([
        rec.idx,
        `M${slot}`,
        rec.sampled_nodes?.[slot] ?? "",
        verifier,
        rec.shared_condition?.type ?? "",
        rec.shared_condition?.text ?? "",
        consensus(rec, slot),
        truncate(e.masked_question, 520),
        e.verification_answer ?? "",
        e.verdict ?? "",
        e.match_reason ?? "",
        truncate(e.solve_raw, 360),
      ]);
    }
  }
}

setup(overview);
title(overview, "共享验证改进：10 题验证性实验", "G");
overview.getRange("A4:G40").format = { font: { name: font, size: 10, color: "#1F2937" }, verticalAlignment: "center" };
overview.getRange("A4:G4").merge();
overview.getRange("A4").values = [["固定同一批初始推理链；题面锚定关键条件；两名外部验证者独立回答同一遮蔽题面；仅在证据充分时使用；加入裁判顺序交换控制。完成日期：2026-09-21"]];
overview.getRange("A4").format = { font: { name: font, size: 10, italic: true, color: "#475569" }, wrapText: true };

overview.getRange("A6:D6").values = [["方法", "正确数", "准确率", "相对顺序交换基线"]];
header(overview, "A6:D6");
overview.getRange("A7:A11").values = [["原始 GoA"], ["无证据裁判 P0"], ["原方法 ProCo 证据裁判 P1"], ["无证据顺序交换裁判"], ["改进版共享验证裁判"]];
overview.getRange("B7:B11").formulas = [
  ["=SUM('逐题结果'!N5:N14)"],
  ["=SUM('逐题结果'!O5:O14)"],
  ["=SUM('逐题结果'!P5:P14)"],
  ["=SUM('逐题结果'!Q5:Q14)"],
  ["=SUM('逐题结果'!R5:R14)"],
];
overview.getRange("C7:C11").formulas = [["=B7/10"], ["=B8/10"], ["=B9/10"], ["=B10/10"], ["=B11/10"]];
overview.getRange("D7:D11").formulas = [["=C7-$C$10"], ["=C8-$C$10"], ["=C9-$C$10"], ["=C10-$C$10"], ["=C11-$C$10"]];
overview.getRange("A7:D11").format.borders = border;
overview.getRange("A7:D7").format.fill = paleBlue;
overview.getRange("A8:D8").format.fill = paleYellow;
overview.getRange("A9:D9").format.fill = paleRed;
overview.getRange("A10:D10").format.fill = lightGray;
overview.getRange("A11:D11").format.fill = paleGreen;
overview.getRange("B7:B11").format.numberFormat = "0";
overview.getRange("C7:D11").format.numberFormat = "0.0%";

overview.getRange("A14:D14").values = [["配对比较", "改善（错→对）", "退化（对→错）", "McNemar 精确 p 值"]];
header(overview, "A14:D14");
overview.getRange("A15:D17").values = [
  ["共享验证 vs 顺序交换基线", summary.paired_shared_vs_baseline_swap_judge.fixed, summary.paired_shared_vs_baseline_swap_judge.broken, summary.paired_shared_vs_baseline_swap_judge.mcnemar_exact_p],
  ["共享验证 vs 原始无证据 P0", summary.paired_shared_vs_baseline_judge.fixed, summary.paired_shared_vs_baseline_judge.broken, summary.paired_shared_vs_baseline_judge.mcnemar_exact_p],
  ["共享验证 vs 原方法 ProCo P1", summary.paired_shared_vs_proco_judge.fixed, summary.paired_shared_vs_proco_judge.broken, summary.paired_shared_vs_proco_judge.mcnemar_exact_p],
];
overview.getRange("A15:D17").format.borders = border;
overview.getRange("D15:D17").format.numberFormat = "0.000";

overview.getRange("A20:C20").values = [["交叉验证状态", "次数", "解释"]];
header(overview, "A20:C20");
overview.getRange("A21:C24").values = [
  ["CONFIRMED_NO_MATCH", summary.consensus.CONFIRMED_NO_MATCH, "两名验证者都发现目标链条件与独立答案不一致"],
  ["CONFIRMED_MATCH", summary.consensus.CONFIRMED_MATCH, "两名验证者都支持目标链条件"],
  ["MIXED_OR_INSUFFICIENT", summary.consensus.MIXED_OR_INSUFFICIENT, "验证者不一致或证据不足，不触发强制降权"],
  ["NO_EVIDENCE", summary.consensus.NO_EVIDENCE, "没有可用验证记录"],
];
overview.getRange("A21:C24").format.borders = border;
overview.getRange("A21:C21").format.fill = paleRed;
overview.getRange("A23:C24").format.fill = lightGray;

overview.getRange("A27:C27").values = [["单次验证输出", "次数", "比例"]];
header(overview, "A27:C27");
overview.getRange("A28:C31").values = [
  ["MATCH", summary.verifier_verdicts.MATCH, summary.verifier_verdicts.MATCH / verifierCalls],
  ["NO_MATCH", summary.verifier_verdicts.NO_MATCH, summary.verifier_verdicts.NO_MATCH / verifierCalls],
  ["UNKNOWN", summary.verifier_verdicts.UNKNOWN, summary.verifier_verdicts.UNKNOWN / verifierCalls],
  ["合计", verifierCalls, 1],
];
overview.getRange("A28:C31").format.borders = border;
overview.getRange("C28:C31").format.numberFormat = "0.0%";

overview.getRange("A34:G34").merge();
overview.getRange("A34").values = [["结论：改进版共享验证裁判为 6/10（60%），顺序交换无证据基线为 5/10（50%），配对上修复 1 题且没有破坏正确题。相对原始无证据 P0 的 7/10（70%）仍低 1 题。10 题样本量很小，McNemar 精确检验 p=1.000，结果只能作为方向性验证，不能据此宣称统计显著。"]];
overview.getRange("A34").format = { fill: paleGreen, font: { name: font, size: 10, bold: true, color: "#1F5130" }, wrapText: true, verticalAlignment: "top" };
overview.getRange("A34").format.rowHeight = 48;
overview.getRange("A:A").format.columnWidth = 31;
overview.getRange("B:B").format.columnWidth = 14;
overview.getRange("C:D").format.columnWidth = 18;
overview.getRange("E:G").format.columnWidth = 14;

setup(items);
title(items, "10 题逐题配对结果", "T");
items.getRange("A4:T14").format = { font: { name: font, size: 10, color: "#1F2937" }, verticalAlignment: "center" };
items.getRange("A4:T4").values = [["题号", "标准答案", "M0 来源", "M0 答案", "M1 来源", "M1 答案", "M2 来源", "M2 答案", "GoA 答案", "P0 答案", "P1 答案", "顺序交换答案", "共享验证答案", "GoA 正确", "P0 正确", "P1 正确", "顺序交换正确", "共享验证正确", "共享 vs 顺序交换", "共享 vs P1"]];
header(items, "A4:T4");
const itemRows = records.map((r, i) => {
  const row = 5 + i;
  return [
    r.idx,
    r.gold,
    r.sampled_nodes?.[0] ?? "",
    r.initial_answers?.["0"] ?? "",
    r.sampled_nodes?.[1] ?? "",
    r.initial_answers?.["1"] ?? "",
    r.sampled_nodes?.[2] ?? "",
    r.initial_answers?.["2"] ?? "",
    r.stored_goa_answer ?? "",
    r.baseline_judge?.answer ?? "",
    r.proco_judge?.answer ?? "",
    r.baseline_swap_judge?.answer ?? "",
    r.shared_judge?.answer ?? "",
    null,
    null,
    null,
    null,
    null,
    null,
    null,
  ];
});
items.getRange("A5:T14").values = itemRows;
for (let i = 0; i < records.length; i += 1) {
  const row = 5 + i;
  items.getRange(`N${row}:R${row}`).formulas = [[
    `=IF(I${row}=B${row},1,0)`,
    `=IF(J${row}=B${row},1,0)`,
    `=IF(K${row}=B${row},1,0)`,
    `=IF(L${row}=B${row},1,0)`,
    `=IF(M${row}=B${row},1,0)`,
  ]];
  items.getRange(`S${row}:T${row}`).formulas = [[
    `=IF(R${row}>Q${row},"改善",IF(R${row}<Q${row},"退化","不变"))`,
    `=IF(R${row}>P${row},"改善",IF(R${row}<P${row},"退化","不变"))`,
  ]];
}
items.getRange("A4:T14").format.borders = border;
items.getRange("A5:T14").format.wrapText = true;
items.getRange("A5:B14").format.horizontalAlignment = "center";
items.getRange("D5:D14").format.horizontalAlignment = "center";
items.getRange("F5:F14").format.horizontalAlignment = "center";
items.getRange("H5:T14").format.horizontalAlignment = "center";
items.getRange("N5:R14").conditionalFormats.add("cellIs", { operator: "equal", formula: 1, format: { fill: paleGreen, font: { color: "#1F5130", bold: true } } });
items.getRange("N5:R14").conditionalFormats.add("cellIs", { operator: "equal", formula: 0, format: { fill: paleRed, font: { color: "#9C0006" } } });
items.getRange("S5:T14").conditionalFormats.add("containsText", { text: "改善", format: { fill: paleGreen, font: { color: "#1F5130", bold: true } } });
items.getRange("S5:T14").conditionalFormats.add("containsText", { text: "退化", format: { fill: paleRed, font: { color: "#9C0006", bold: true } } });
items.freezePanes.freezeRows(4);
for (const [col, w] of [["A",8],["B",9],["C",20],["D",9],["E",20],["F",9],["G",20],["H",9],["I",9],["J",9],["K",9],["L",12],["M",12],["N",10],["O",10],["P",10],["Q",12],["R",12],["S",15],["T",12]]) items.getRange(`${col}:${col}`).format.columnWidth = w;

setup(evidence);
title(evidence, "共享题面交叉验证记录", "L");
evidence.getRange(`A4:L${4 + evidenceRows.length}`).format = { font: { name: font, size: 10, color: "#1F2937" }, verticalAlignment: "center" };
evidence.getRange("A4:L4").values = [["题号", "目标链", "来源模型", "验证模型", "条件类型", "关键条件", "共识状态", "遮蔽题面", "独立推断", "验证结论", "匹配原因", "原始输出"]];
header(evidence, "A4:L4");
evidence.getRange(`A5:L${4 + evidenceRows.length}`).values = evidenceRows;
evidence.getRange(`A4:L${4 + evidenceRows.length}`).format.borders = border;
evidence.getRange(`A5:L${4 + evidenceRows.length}`).format.wrapText = true;
evidence.getRange(`A5:L${4 + evidenceRows.length}`).format.verticalAlignment = "top";
evidence.getRange(`J5:J${4 + evidenceRows.length}`).conditionalFormats.add("containsText", { text: "NO_MATCH", format: { fill: paleRed, font: { color: "#9C0006", bold: true } } });
evidence.getRange(`J5:J${4 + evidenceRows.length}`).conditionalFormats.add("containsText", { text: "MATCH", format: { fill: paleGreen, font: { color: "#1F5130", bold: true } } });
evidence.getRange(`J5:J${4 + evidenceRows.length}`).conditionalFormats.add("containsText", { text: "UNKNOWN", format: { fill: paleYellow, font: { color: "#7F6000" } } });
evidence.freezePanes.freezeRows(4);
for (const [col, w] of [["A",8],["B",10],["C",20],["D",20],["E",12],["F",36],["G",25],["H",64],["I",34],["J",14],["K",26],["L",45]]) evidence.getRange(`${col}:${col}`).format.columnWidth = w;
evidence.getRange(`A5:L${4 + evidenceRows.length}`).format.rowHeight = 38;

setup(protocol);
title(protocol, "实验协议与代码要点", "D");
protocol.getRange("A4:D4").values = [["项目", "本次设置", "理论依据 / 目的", "执行结果"]];
header(protocol, "A4:D4");
protocol.getRange("A5:D14").values = [
  ["样本", "固定原实验中同一批 10 题和三条初始链", "配对实验控制题目与初始输出，减少样本差异", "10/10 完成"],
  ["条件选择", "优先选择题面中可定位的数值跨度，否则选择题面短语", "操作化定义关键条件，避免每条链选择不同验证对象", "10/10 生成条件"],
  ["信息隔离", "验证者只看遮蔽后的题面，不看原始推理链和标准答案", "减少验证者被原结论锚定，近似独立复核", "执行成功"],
  ["数值匹配", "数值条件采用归一化数值比较", "避免单位、大小写或 LaTeX 写法造成伪差异", "识别数值 NO_MATCH"],
  ["文本匹配", "只有明确包含或精确匹配才判定，其他为 UNKNOWN", "将不确定性显式保留，避免弱证据误伤", "大量 UNKNOWN"],
  ["共识门槛", "两名验证者一致 NO_MATCH 才形成确认负证据", "类似多数表决与证据阈值，降低单模型噪声", "CONFIRMED_NO_MATCH=2"],
  ["裁判控制", "无证据基线额外交换 Response A/B 顺序", "控制 pairwise judge 的位置偏好", "基线 5/10"],
  ["比较指标", "逐题正确率与 fixed/broken 配对计数", "直接回答是否修复错误、是否破坏正确", "fixed=1, broken=0"],
  ["执行脚本", "run_proco_keyverify_shared_10.sh + run_proco_keyverify_shared.py", "保留可复现的运行入口与协议实现", "服务器已完整运行"],
  ["原始结果", "proco_keyverify_shared_10_v3.json / summary.json", "原始逐题记录和汇总统计", "已下载并核验"],
];
protocol.getRange("A5:D14").format.borders = border;
protocol.getRange("A5:D14").format.wrapText = true;
protocol.getRange("A5:D14").format.verticalAlignment = "top";
protocol.getRange("A:A").format.columnWidth = 16;
protocol.getRange("B:B").format.columnWidth = 55;
protocol.getRange("C:C").format.columnWidth = 50;
protocol.getRange("D:D").format.columnWidth = 24;
protocol.getRange("A17:D17").merge();
protocol.getRange("A17").values = [["解释：NO_MATCH 表示独立验证者推断出的关键条件与目标链所基于的条件不一致。UNKNOWN 表示输出无法可靠解析或题面条件不足以做确定比较，因此不应被当作支持或反对证据。"]];
protocol.getRange("A17").format = { fill: paleYellow, font: { name: font, size: 10, color: "#7F6000" }, wrapText: true, verticalAlignment: "top" };
protocol.getRange("A17").format.rowHeight = 38;

wb.recalculate();
const overviewCheck = await wb.inspect({ kind: "table", range: "实验结论!A2:G34", include: "values,formulas", tableMaxRows: 36, tableMaxCols: 7 });
console.log(overviewCheck.ndjson);
const itemCheck = await wb.inspect({ kind: "table", range: "逐题结果!A4:T14", include: "values,formulas", tableMaxRows: 12, tableMaxCols: 20 });
console.log(itemCheck.ndjson);
const errorCheck = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errorCheck.ndjson);

await fs.mkdir(outputDir, { recursive: true });
for (const [sheetName, range, filename] of [["实验结论", "A1:G34", "2026-09-21_共享验证改进_10题验证实验_实验结论.png"], ["逐题结果", "A1:T14", "2026-09-21_共享验证改进_10题验证实验_逐题结果.png"], ["协议与代码", "A1:D17", "2026-09-21_共享验证改进_10题验证实验_协议.png"]]) {
  const preview = await wb.render({ sheetName, range, scale: 1.2, format: "png" });
  await fs.writeFile(`${outputDir}/${filename}`, new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outPath);
console.log(outPath);
