import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const projectDir = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia";
const outputDir = `${projectDir}/outputs/01a0bf30-719f-7601-bf05-d9d52b24c4d2`;
const outPath = `${outputDir}/2026-09-21_共享验证再生成再池化_10题验证实验.xlsx`;
const summary = JSON.parse(await fs.readFile(`${projectDir}/outputs/proco_keyverify_pool_repair_10_v2_summary.json`, "utf8"));
const records = JSON.parse(await fs.readFile(`${projectDir}/outputs/proco_keyverify_pool_repair_10_v2.json`, "utf8"));

const wb = Workbook.create();
const overview = wb.worksheets.add("实验结论");
const items = wb.worksheets.add("逐题结果");
const repairs = wb.worksheets.add("修复生成记录");
const protocol = wb.worksheets.add("协议与失败分析");

const font = "Arial";
const navy = "#1F4E78";
const paleBlue = "#EAF2F8";
const paleYellow = "#FFF2CC";
const paleGreen = "#E2F0D9";
const paleRed = "#FCE4D6";
const lightGray = "#F3F6F9";
const border = { preset: "all", style: "thin", color: "#D9E2F3" };

function setup(sheet) { sheet.showGridLines = false; }
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
function truncate(value, n = 500) {
  const text = (value == null ? "" : String(value)).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, "");
  return text.length > n ? `${text.slice(0, n)}…` : text;
}

setup(overview);
title(overview, "共享验证 + 再生成 + 再池化：10 题验证性实验", "G");
overview.getRange("A4:G4").merge();
overview.getRange("A4").values = [["所有题目都执行共享验证和修复生成；原始池化答案保留为控制候选；只有两个修复模型与最终池化器一致时才允许替换。最终修正版运行日期：2026-09-21"]];
overview.getRange("A4").format = { font: { name: font, size: 10, italic: true, color: "#475569" }, wrapText: true };
overview.getRange("A6:D6").values = [["方法", "正确数", "准确率", "相对 A_pool"]];
header(overview, "A6:D6");
overview.getRange("A7:A12").values = [["原始池化 A_pool"], ["无证据裁判 P0"], ["原方法 ProCo P1"], ["共享验证裁判"], ["二次池化器原始输出"], ["最终接受答案"]];
overview.getRange("B7:B12").formulas = [
  ["=SUM('逐题结果'!O5:O14)"],
  ["=SUM('逐题结果'!P5:P14)"],
  ["=SUM('逐题结果'!Q5:Q14)"],
  ["=SUM('逐题结果'!S5:S14)"],
  ["=SUM('逐题结果'!T5:T14)"],
  ["=SUM('逐题结果'!U5:U14)"],
];
overview.getRange("C7:C12").formulas = [["=B7/10"], ["=B8/10"], ["=B9/10"], ["=B10/10"], ["=B11/10"], ["=B12/10"]];
overview.getRange("D7:D12").formulas = [["=C7-$C$7"], ["=C8-$C$7"], ["=C9-$C$7"], ["=C10-$C$7"], ["=C11-$C$7"], ["=C12-$C$7"]];
overview.getRange("A7:D12").format.borders = border;
overview.getRange("A7:D7").format.fill = paleBlue;
overview.getRange("A8:D9").format.fill = paleYellow;
overview.getRange("A10:D10").format.fill = paleGreen;
overview.getRange("A11:D11").format.fill = paleRed;
overview.getRange("A12:D12").format.fill = paleRed;
overview.getRange("B7:B12").format.numberFormat = "0";
overview.getRange("C7:D12").format.numberFormat = "0.0%";

overview.getRange("A15:D15").values = [["最终答案配对比较", "改善（错→对）", "退化（对→错）", "McNemar 精确 p 值"]];
header(overview, "A15:D15");
overview.getRange("A16:D19").values = [
  ["最终答案 vs A_pool", summary.paired.final_vs_stored_goa_answer.fixed, summary.paired.final_vs_stored_goa_answer.broken, summary.paired.final_vs_stored_goa_answer.mcnemar_exact_p],
  ["最终答案 vs 顺序交换 P0", summary.paired.final_vs_baseline_swap_judge.fixed, summary.paired.final_vs_baseline_swap_judge.broken, summary.paired.final_vs_baseline_swap_judge.mcnemar_exact_p],
  ["最终答案 vs 共享验证裁判", summary.paired.final_vs_shared_judge.fixed, summary.paired.final_vs_shared_judge.broken, summary.paired.final_vs_shared_judge.mcnemar_exact_p],
  ["最终答案 vs 原方法 P1", summary.paired.final_vs_proco_judge.fixed, summary.paired.final_vs_proco_judge.broken, summary.paired.final_vs_proco_judge.mcnemar_exact_p],
];
overview.getRange("A16:D19").format.borders = border;
overview.getRange("D16:D19").format.numberFormat = "0.000";

overview.getRange("A22:C22").values = [["修复阶段统计", "数量", "解释"]];
header(overview, "A22:C22");
overview.getRange("A23:C27").values = [
  ["修复模型形成 2/3 共识", summary.repair.repair_consensus, "至少两个修复模型给出同一选项"],
  ["原始池化条件被确认矛盾", summary.repair.pool_contradicted, "与 A_pool 相同的初始链出现双验证 NO_MATCH"],
  ["实际接受改写", summary.repair.accepted_repair, "修复共识与最终池化器一致"],
  ["最终改写题数", summary.repair.changed_from_A_pool, "最终答案不同于 A_pool"],
  ["回退到 A_pool", summary.repair.fallback_to_A_pool, "证据不足时保留原始池化答案"],
];
overview.getRange("A23:C27").format.borders = border;
overview.getRange("A24:C26").format.fill = paleRed;
overview.getRange("A27:C27").format.fill = paleBlue;

overview.getRange("A30:G30").merge();
overview.getRange("A30").values = [["结论：本次最终接受答案为 4/10（40%），低于原始池化 A_pool 的 5/10（50%）和共享验证裁判的 6/10（60%）。只有 1 题被改写，且该题由两个修复模型一致错误地改写，造成 1 次退化、0 次修复。当前版本尚未证明有效，主要问题是修复模型答案塌缩与“共识不等于独立证据”。"]];
overview.getRange("A30").format = { fill: paleRed, font: { name: font, size: 10, bold: true, color: "#9C0006" }, wrapText: true, verticalAlignment: "top" };
overview.getRange("A30").format.rowHeight = 50;
overview.getRange("A:A").format.columnWidth = 31;
overview.getRange("B:B").format.columnWidth = 14;
overview.getRange("C:D").format.columnWidth = 18;
overview.getRange("E:G").format.columnWidth = 14;

setup(items);
title(items, "10 题逐题结果", "X");
items.getRange("A4:X14").format = { font: { name: font, size: 10, color: "#1F2937" }, verticalAlignment: "center" };
items.getRange("A4:X4").values = [["题号", "标准答案", "A_pool", "原始 P0", "原始 P1", "顺序交换 P0", "共享验证裁判", "二次池化器", "Qwen 修复", "Mathstral 修复", "BioMistral 修复", "修复共识", "最终答案", "最终原因", "A_pool 正确", "原始 P0 正确", "原始 P1 正确", "顺序交换正确", "共享裁判正确", "池化器正确", "最终正确", "接受改写", "最终 vs A_pool", "池化条件矛盾"]];
header(items, "A4:X4");
const rows = records.map((r, i) => {
  const row = 5 + i;
  const final = r.final_answer ?? "";
  const pool = r.stored_goa_answer ?? "";
  return [
    r.idx, r.gold, pool, r.baseline_judge?.answer ?? "", r.proco_judge?.answer ?? "", r.baseline_swap_judge?.answer ?? "", r.shared_judge?.answer ?? "", r.pooler?.answer ?? "",
    r.repair_pool?.qwen?.answer ?? "", r.repair_pool?.mathstral?.answer ?? "", r.repair_pool?.biomedical_llama?.answer ?? "", r.repair_consensus ?? "", final, r.final_reason ?? "", null, null, null, null, null, null, null,
    r.final_reason?.startsWith("two_repairs") ? "是" : "否",
    final === pool ? "不变" : (final === r.gold ? "修复" : "退化"),
    r.pool_contradicted ? "是" : "否",
  ];
});
items.getRange("A5:X14").values = rows;
for (let i = 0; i < records.length; i += 1) {
  const row = 5 + i;
  items.getRange(`O${row}:U${row}`).formulas = [[
    `=IF(C${row}=B${row},1,0)`, `=IF(D${row}=B${row},1,0)`, `=IF(E${row}=B${row},1,0)`,
    `=IF(F${row}=B${row},1,0)`, `=IF(G${row}=B${row},1,0)`, `=IF(H${row}=B${row},1,0)`, `=IF(M${row}=B${row},1,0)`,
  ]];
}
items.getRange("A4:X14").format.borders = border;
items.getRange("A5:X14").format.wrapText = true;
items.getRange("A5:B14").format.horizontalAlignment = "center";
items.getRange("C5:X14").format.horizontalAlignment = "center";
items.getRange("O5:U14").conditionalFormats.add("cellIs", { operator: "equal", formula: 1, format: { fill: paleGreen, font: { color: "#1F5130", bold: true } } });
items.getRange("O5:U14").conditionalFormats.add("cellIs", { operator: "equal", formula: 0, format: { fill: paleRed, font: { color: "#9C0006" } } });
items.getRange("W5:W14").conditionalFormats.add("containsText", { text: "修复", format: { fill: paleGreen, font: { color: "#1F5130", bold: true } } });
items.getRange("W5:W14").conditionalFormats.add("containsText", { text: "退化", format: { fill: paleRed, font: { color: "#9C0006", bold: true } } });
items.freezePanes.freezeRows(4);
for (const [col, w] of [["A",8],["B",9],["C",9],["D",9],["E",9],["F",12],["G",14],["H",12],["I",12],["J",15],["K",15],["L",12],["M",10],["N",35],["O",10],["P",12],["Q",12],["R",12],["S",12],["T",12],["U",10],["V",10],["W",13],["X",13]]) items.getRange(`${col}:${col}`).format.columnWidth = w;

setup(repairs);
title(repairs, "三模型修复生成记录", "H");
repairs.getRange("A4:H34").format = { font: { name: font, size: 10, color: "#1F2937" }, verticalAlignment: "top" };
repairs.getRange("A4:H4").values = [["题号", "修复模型", "修复答案", "2/3 共识", "输出是否可解析", "修复理由", "关键主张", "原始输出片段"]];
header(repairs, "A4:H4");
const repairRows = [];
for (const r of records) {
  for (const model of ["qwen", "mathstral", "biomedical_llama"]) {
    const item = r.repair_pool?.[model] ?? {};
    repairRows.push([r.idx, model, item.answer ?? "PARSE_FAIL", r.repair_consensus ?? "", item.answer ? "是" : "否", truncate(item.reason, 600), truncate(Array.isArray(item.key_claims) ? item.key_claims.join("; ") : String(item.key_claims ?? ""), 700), truncate(item.raw, 700)]);
  }
}
repairs.getRange(`A5:H${4 + repairRows.length}`).values = repairRows;
repairs.getRange(`A4:H${4 + repairRows.length}`).format.borders = border;
repairs.getRange(`A5:H${4 + repairRows.length}`).format.wrapText = true;
repairs.getRange(`C5:C${4 + repairRows.length}`).conditionalFormats.add("containsText", { text: "PARSE_FAIL", format: { fill: paleRed, font: { color: "#9C0006", bold: true } } });
repairs.freezePanes.freezeRows(4);
for (const [col, w] of [["A",8],["B",20],["C",12],["D",12],["E",14],["F",35],["G",42],["H",68]]) repairs.getRange(`${col}:${col}`).format.columnWidth = w;
repairs.getRange(`A5:H${4 + repairRows.length}`).format.rowHeight = 34;

setup(protocol);
title(protocol, "协议与失败分析", "D");
protocol.getRange("A4:D4").values = [["阶段", "实际实现", "规则", "本次观察"]];
header(protocol, "A4:D4");
protocol.getRange("A5:D13").values = [
  ["固定输入", "复用上一轮共享验证的 10 道题、三条初始链和验证证据", "不重新抽样，不泄露标准答案", "可比"],
  ["修复生成", "Qwen、Mathstral、BioMistral 各自重新求解", "允许输出初始候选之外的新选项", "Mathstral/BioMistral 大量输出只含 A 或无法解析"],
  ["二次池化", "Qwen 综合 A_pool、三条初始链、三个修复答案和验证证据", "不能只按多数投票，允许重新推导", "池化器原始输出仅 2/10 正确"],
  ["接受规则", "只有两个修复模型一致且池化器也同意才替换 A_pool", "否则回退到 A_pool", "10 题仅 1 题接受改写"],
  ["退化样本", "idx=4：A_pool=B，两个修复模型和池化器均给 A", "模型共识不等于独立正确证据", "B 为标准答案，改写后错误"],
  ["最终结果", "最终答案 vs A_pool", "逐题配对计数", "fixed=0, broken=1, p=1.000"],
  ["失败运行处理", "第一次运行因旧字母正则兼容问题中止", "未写入有效统计，不纳入汇总", "最终 v2 使用显式 FINAL_ANSWER 解析"],
  ["主要限制", "修复模型输出分布塌缩，修复共识高度相关", "不能把 2/3 共识直接视为独立证据", "当前方法未证明有效"],
  ["下一步方向", "增加修复模型温度/提示多样性、答案级独立验证和校准", "先在开发集验证再跑测试集", "需要重新设计后再实验"],
];
protocol.getRange("A5:D13").format.borders = border;
protocol.getRange("A5:D13").format.wrapText = true;
protocol.getRange("A5:D13").format.verticalAlignment = "top";
protocol.getRange("A:A").format.columnWidth = 18;
protocol.getRange("B:B").format.columnWidth = 56;
protocol.getRange("C:C").format.columnWidth = 48;
protocol.getRange("D:D").format.columnWidth = 38;
protocol.getRange("A16:D16").merge();
protocol.getRange("A16").values = [["判定：本轮结果不支持直接采用“共享验证 + 再生成 + 再池化”作为最终方法。下一版必须先解决修复模型的答案塌缩和独立性问题，否则多数修复模型会把同一个错误放大。"]];
protocol.getRange("A16").format = { fill: paleRed, font: { name: font, size: 10, bold: true, color: "#9C0006" }, wrapText: true, verticalAlignment: "top" };
protocol.getRange("A16").format.rowHeight = 42;

wb.recalculate();
const check = await wb.inspect({ kind: "table", range: "实验结论!A6:D30", include: "values,formulas", tableMaxRows: 30, tableMaxCols: 7 });
console.log(check.ndjson);
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!", options: { useRegex: true, maxResults: 100 }, summary: "final formula error scan" });
console.log(errors.ndjson);
await fs.mkdir(outputDir, { recursive: true });
for (const [sheetName, range, filename] of [["实验结论", "A1:G30", "2026-09-21_共享验证再生成再池化_10题验证实验_实验结论.png"], ["逐题结果", "A1:X14", "2026-09-21_共享验证再生成再池化_10题验证实验_逐题结果.png"], ["协议与失败分析", "A1:D16", "2026-09-21_共享验证再生成再池化_10题验证实验_协议.png"]]) {
  const preview = await wb.render({ sheetName, range, scale: 1.2, format: "png" });
  await fs.writeFile(`${outputDir}/${filename}`, new Uint8Array(await preview.arrayBuffer()));
}
const output = await SpreadsheetFile.exportXlsx(wb);
await output.save(outPath);
console.log(outPath);
