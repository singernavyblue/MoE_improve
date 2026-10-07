# -*- coding: utf-8 -*-
"""Report for judge ablation: Prometheus-7B vs strong LLM on the same 40 questions.
Reads outputs/judge_ablation_40_prometheus.json (and optional _strong.json)."""
import json
import sys

CHAINS = json.load(open("outputs/judge_ablation_40_initial_chains.json"))
BASE = {int(x["idx"]): x for x in json.load(open("outputs/GPQA_test_merged_6models_judge_nogold_pairwise_margin.json"))}


def load(path):
    try:
        return json.load(open(path))
    except FileNotFoundError:
        return None


prom = load("outputs/judge_ablation_40_prometheus.json")
strong = load("outputs/judge_ablation_40_strong.json")

for name, data in (("Prometheus-7B", prom), ("Strong", strong)):
    if data is None:
        continue
    s = data["summary"]
    print(f"{name}: top-chain acc = {s['top_correct']}/{s['n']} = {s['acc']*100:.2f}% (fallback {s['fallback']})")

if prom and strong:
    prows = {r["idx"]: r for r in prom["rows"]}
    srows = {r["idx"]: r for r in strong["rows"]}
    common = sorted(set(prows) & set(srows))
    print(f"\ncommon questions: {len(common)}")
    both = agree = 0
    p_only = s_only = 0
    for i in common:
        p, s = prows[i], srows[i]
        pc, sc = p["top_correct"], s["top_correct"]
        both += pc and sc
        agree += p["top_node"] == s["top_node"]
        p_only += pc and not sc
        s_only += sc and not pc
    print(f"both correct: {both} | prom-only: {p_only} | strong-only: {s_only} | same top node: {agree}/{len(common)}")

# per-question detail
print("\nidx | gold | answers(chain0/1/2) | prom_top | strong_top")
for i in sorted(int(c["idx"]) for c in CHAINS):
    gold = CHAINS[[int(c["idx"]) for c in CHAINS].index(i)]["gold"]
    answers = CHAINS[[int(c["idx"]) for c in CHAINS].index(i)]["answers"]
    pt = prom["rows"][[r["idx"] for r in prom["rows"]].index(i)]["top_answer"] if prom else "?"
    st = strong["rows"][[r["idx"] for r in strong["rows"]].index(i)]["top_answer"] if strong else "?"
    print(f"{i:>3} | {gold} | {answers} | {pt} | {st}")
