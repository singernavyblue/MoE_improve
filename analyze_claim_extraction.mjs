import fs from "node:fs/promises";
import path from "node:path";

const root = process.cwd();
const sources = [
  ["MedMCQA", "outputs/qae_localized_medmcqa.json"],
  ["MMLU", "outputs/qae_localized_mmlu.json"],
  ["MMLU-Pro", "outputs/qae_localized_mmlu_pro.json"],
  ["MATH", "outputs/qae_localized_math_free.json"],
  ["HumanEval", "outputs/qae_localized_humaneval_free.json"],
];

const cleanRaw = (raw) => String(raw || "")
  .replace(/^\s*```(?:json)?\s*/i, "")
  .replace(/\s*```\s*$/, "")
  .trim();
const norm = (value) => String(value || "").replace(/\s+/g, " ").trim();
const inc = (haystack, needle) => String(haystack || "").includes(String(needle || ""));

const totals = {
  records: 0, storedClaims: 0, rawClaims: 0, rawParseFailures: [],
  exactQuote: 0, normalizedQuote: 0, quoteMissing: [],
  validDependency: 0, invalidDependency: [], quoteReuse: 0,
  sourceCounts: {}, typeCounts: {}, impactCounts: {}, recordCoverage: [],
  rawVsStored: [],
};

for (const [dataset, rel] of sources) {
  const records = JSON.parse(await fs.readFile(path.join(root, rel), "utf8"));
  for (const record of records) {
    totals.records += 1;
    const chains = record.initial_responses || {};
    const stored = record.swarm_claims?.claims || [];
    const raw = record.swarm_claims?.raw || "";
    let rawClaims = [];
    try {
      rawClaims = JSON.parse(cleanRaw(raw)).claims || [];
    } catch (error) {
      totals.rawParseFailures.push({ dataset, idx: record.idx, message: error.message, preview: raw.slice(0, 160) });
    }
    totals.rawClaims += rawClaims.length;
    totals.storedClaims += stored.length;
    if (rawClaims.length !== stored.length) totals.rawVsStored.push({ dataset, idx: record.idx, raw: rawClaims.length, stored: stored.length });

    const models = new Set(stored.map(c => c.model));
    totals.recordCoverage.push({ dataset, idx: record.idx, stored: stored.length, models: [...models].sort().join(",") });
    const claimIds = new Set(stored.map(c => c.claim_id));
    const quotes = new Map();
    for (const claim of stored) {
      totals.sourceCounts[claim.model] = (totals.sourceCounts[claim.model] || 0) + 1;
      totals.typeCounts[claim.type] = (totals.typeCounts[claim.type] || 0) + 1;
      totals.impactCounts[claim.answer_impact] = (totals.impactCounts[claim.answer_impact] || 0) + 1;
      const slot = String(claim.model || "").replace(/^M/, "");
      const chain = chains[slot] ?? chains[claim.model] ?? "";
      const quote = claim.quote || "";
      const quoteKey = norm(quote);
      quotes.set(quoteKey, (quotes.get(quoteKey) || 0) + 1);
      if (inc(chain, quote)) totals.exactQuote += 1;
      else if (norm(chain).includes(quoteKey)) totals.normalizedQuote += 1;
      else totals.quoteMissing.push({ dataset, idx: record.idx, id: claim.claim_id, model: claim.model, quote: quote.slice(0, 190), chain: String(chain).slice(0, 360) });
      for (const dep of (claim.depends_on || [])) {
        if (claimIds.has(dep)) totals.validDependency += 1;
        else totals.invalidDependency.push({ dataset, idx: record.idx, id: claim.claim_id, model: claim.model, dependency: dep });
      }
    }
    totals.quoteReuse += [...quotes.values()].filter(n => n > 1).reduce((a, b) => a + b - 1, 0);
  }
}

const coverage = {};
for (const row of totals.recordCoverage) {
  const key = row.models || "none";
  coverage[key] = (coverage[key] || 0) + 1;
}
const out = {
  headline: {
    records: totals.records,
    storedClaims: totals.storedClaims,
    rawClaims: totals.rawClaims,
    rawParseFailures: totals.rawParseFailures.length,
    exactQuoteRate: Number((totals.exactQuote / totals.storedClaims).toFixed(4)),
    normalizedQuoteOnlyRate: Number((totals.normalizedQuote / totals.storedClaims).toFixed(4)),
    quoteMissingRate: Number((totals.quoteMissing.length / totals.storedClaims).toFixed(4)),
    dependencyValid: totals.validDependency,
    dependencyInvalid: totals.invalidDependency.length,
    quoteReuse: totals.quoteReuse,
    recordsWithClaims: totals.recordCoverage.filter(x => x.stored > 0).length,
    recordsWithCrossModelClaims: totals.recordCoverage.filter(x => x.models.split(",").filter(Boolean).length >= 2).length,
  },
  sourceCounts: totals.sourceCounts,
  typeCounts: totals.typeCounts,
  impactCounts: totals.impactCounts,
  claimModelCoverage: coverage,
  examples: {
    rawVsStored: totals.rawVsStored.slice(0, 20),
    quoteMissing: totals.quoteMissing.slice(0, 20),
    invalidDependency: totals.invalidDependency.slice(0, 20),
  },
};
console.log(JSON.stringify(out, null, 2));
