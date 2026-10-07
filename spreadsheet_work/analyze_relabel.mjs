// 一致性检验：读取同学回传的复标表，与参考答案比对，输出四项指标与分歧清单。
// 用法：node analyze_relabel.mjs <回传的xlsx路径> [输出json路径]
import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const xlsxPath = process.argv[2] || "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/复标回传_同学A.xlsx";
const outJson = process.argv[3] || xlsxPath.replace(/\.xlsx$/i, "_一致性报告.json");

const sample = JSON.parse(
  await fs.readFile("/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/gpqa_repo/复标样本_15题.json", "utf8"),
);
// 参考答案（官方 150 题标定，按 record_id 取）
const refById = {};
for (const s of sample) refById[s.item.record_id] = s.orig_label;

const input = await FileBlob.load(xlsxPath);
const wb = await SpreadsheetFile.importXlsx(input);
const sheet = wb.worksheets.getItem("复标题目_15");

const rows = [];
for (let r = 5; r <= 19; r++) {
  const rec = sheet.getRange(`B${r}`).values[0][0];
  const prim = sheet.getRange(`L${r}`).values[0][0];
  const dims = sheet.getRange(`M${r}:P${r}`).values[0].map((v) => (v === 1 || v === "1" ? 1 : 0));
  const note = sheet.getRange(`Q${r}`).values[0][0] || "";
  rows.push({ record_id: rec, primary: prim || "", dims, note: note || "" });
}

if (rows.length !== sample.length) {
  console.error(`行数不匹配：回传 ${rows.length} 行，预期 ${sample.length} 行`);
  process.exit(1);
}

const detail = rows.map((row, i) => {
  const ref = refById[row.record_id];
  const refVec = ref.slice(1, 5).map(Number);
  const primaryAgree = row.primary === ref[0];
  const vectorAgree = JSON.stringify(row.dims) === JSON.stringify(refVec);
  const noteAgree = row.note === ref[5];
  return {
    index: sample[i].index,
    record_id: row.record_id,
    ref: { primary: ref[0], dims: refVec, note: ref[5] },
    got: { primary: row.primary, dims: row.dims, note: row.note },
    primary_agree: primaryAgree,
    vector_agree: vectorAgree,
    note_agree: noteAgree,
    disagreements: [
      primaryAgree ? null : `主维: ${row.primary} vs ${ref[0]}`,
      vectorAgree ? null : `D1-D4: ${row.dims.join("")} vs ${refVec.join("")}`,
      noteAgree ? null : `备注: ${row.note || "(空)"} vs ${ref[5] || "(空)"}`,
    ].filter(Boolean),
  };
});

const n = detail.length;
const pa = detail.filter((d) => d.primary_agree).length;
const va = detail.filter((d) => d.vector_agree).length;
const na = detail.filter((d) => d.note_agree).length;
const pairs = detail.map((d) => [d.ref.primary, d.got.primary]);
const po = pa / n;
const cats = ["D1", "D2", "D3", "D4"];
const pe = cats.reduce((acc, c) => {
  const r = pairs.filter((p) => p[0] === c).length / n;
  const g = pairs.filter((p) => p[1] === c).length / n;
  return acc + r * g;
}, 0);
const kappa = pe < 1 ? (po - pe) / (1 - pe) : 1;

const report = {
  file: xlsxPath,
  n,
  primary_agree_rate: pa / n,
  vector_agree_rate: va / n,
  note_agree_rate: na / n,
  cohen_kappa_primary: Number(kappa.toFixed(4)),
  pass: pa / n >= 0.85 && va / n >= 0.85,
  disagreements: detail.filter((d) => d.disagreements.length > 0).map((d) => ({
    index: d.index,
    record_id: d.record_id,
    issues: d.disagreements,
  })),
};

await fs.writeFile(outJson, JSON.stringify(report, null, 2));
console.log("===== 一致性报告 =====");
console.log(`样本量: ${n}`);
console.log(`主维一致率: ${pa}/${n} = ${(pa / n * 100).toFixed(1)}%`);
console.log(`维度向量一致率: ${va}/${n} = ${(va / n * 100).toFixed(1)}%`);
console.log(`备注一致率: ${na}/${n} = ${(na / n * 100).toFixed(1)}%`);
console.log(`Cohen's kappa（主维）: ${kappa.toFixed(4)}`);
console.log(`判定: ${report.pass ? "通过（≥85%）" : "未通过，需分歧复盘"}`);
if (report.disagreements.length) {
  console.log("分歧题:");
  for (const d of report.disagreements) console.log(`  #${d.index} ${d.record_id}: ${d.issues.join("；")}`);
} else {
  console.log("分歧题: 无");
}
console.log("报告已保存:", outJson);
