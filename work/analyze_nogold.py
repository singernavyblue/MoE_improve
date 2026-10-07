#!/usr/bin/env python3
"""Dedicated analysis of the no-gold (Variant A) judge experiment."""
import json
import re
from collections import Counter

OUT = "outputs"
BASE = f"{OUT}/GPQA_test_orig_baseline.json"
NOGOLD = f"{OUT}/GPQA_test_merged_6models_judge_nogold.json"
GOLD = f"{OUT}/GPQA_test_merged_6models_judge.json"


def load(p):
    return {r["idx"]: r for r in json.load(open(p))}


def acc(d, keys):
    return sum(1 for i in keys if d[i]["answer"] == d[i]["gold_answer"])


def domain(q):
    ql = q.lower()
    chem = ["carbon", "methyl", "reaction", "compound", "molecule", "bond", "acid",
            "alkene", "aldehyde", "isomer", "synthesis", "nmr", "grignard", "reagent",
            "protein", "dna", "amino", "enzyme", "bacteria", "cell", "gene", "peptide"]
    phys = ["quantum", "electron", "energy", "field", "velocity", "nucleus", "mass",
            "photon", "angular", "charge", "magnetic", "wave", "particle", "temperature",
            "star", "gravitational", "potential", "momentum"]
    c = sum(1 for w in chem if w in ql)
    p = sum(1 for w in phys if w in ql)
    return "chem" if c > p else ("phys" if p > c else "other")


def main():
    base = load(BASE)
    ng = load(NOGOLD)
    gold = load(GOLD)
    keys = list(base.keys())
    print(f"base={len(base)} nogold={len(ng)} gold={len(gold)}")

    print("\n=== 全量 198 ===")
    print(f"baseline : {acc(base, keys)}/198 = {acc(base, keys)/198*100:.2f}%")
    print(f"no-gold  : {acc(ng, keys)}/198 = {acc(ng, keys)/198*100:.2f}%")
    print(f"gold-judge: {acc(gold, keys)}/198 = {acc(gold, keys)/198*100:.2f}%")

    same = [i for i in keys if i in ng and sorted(base[i].get("sampled_nodes", [])) == sorted(ng[i].get("sampled_nodes", []))]
    print(f"\n=== 严格子集（节点一致）: {len(same)} ===")
    print(f"baseline : {acc(base, same)}/{len(same)} = {acc(base, same)/len(same)*100:.2f}%")
    print(f"no-gold  : {acc(ng, same)}/{len(same)} = {acc(ng, same)/len(same)*100:.2f}%")

    gained = [i for i in same if base[i]["answer"] != base[i]["gold_answer"] and ng[i]["answer"] == ng[i]["gold_answer"]]
    lost = [i for i in same if base[i]["answer"] == base[i]["gold_answer"] and ng[i]["answer"] != ng[i]["gold_answer"]]
    both_w = [i for i in same if base[i]["answer"] != base[i]["gold_answer"] and ng[i]["answer"] != ng[i]["gold_answer"]]
    both_r = [i for i in same if base[i]["answer"] == base[i]["gold_answer"] and ng[i]["answer"] == ng[i]["gold_answer"]]
    changed = [i for i in same if base[i]["answer"] != ng[i]["answer"]]
    print(f"gained (错→对): {len(gained)} {gained}")
    print(f"lost   (对→错): {len(lost)} {lost}")
    print(f"both wrong: {len(both_w)} | both right: {len(both_r)} | answers changed: {len(changed)}")

    print("\n=== 学科分布（严格子集翻转）===")
    for name, lst in [("gained", gained), ("lost", lost)]:
        c = Counter(domain(base[i]["question"]) for i in lst)
        print(f"{name}: {dict(c)}")

    # domain of all strict subset for reference
    dc = Counter(domain(base[i]["question"]) for i in same)
    print("strict subset domain:", dict(dc))

    # details
    out = []
    for i in gained + lost:
        b, n = base[i], ng[i]
        out.append({
            "idx": i, "flip": "gained" if i in gained else "lost",
            "domain": domain(b["question"]),
            "question": b["question"][:350],
            "gold": b["gold_answer"], "baseline_answer": b["answer"], "nogold_answer": n["answer"],
            "nodes": [str(x) for x in b.get("sampled_nodes", [])],
            "baseline_final": b.get("final_response", "")[-200:],
            "nogold_final": n.get("final_response", "")[-200:],
        })
    with open(f"{OUT}/nogold_strict_flips.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\nsaved outputs/nogold_strict_flips.json")

    # nogold vs gold-judge (same nodes)
    same2 = [i for i in keys if i in ng and i in gold and sorted(ng[i].get("sampled_nodes", [])) == sorted(gold[i].get("sampled_nodes", []))]
    print(f"\n=== 无gold vs 有gold（节点一致）: {len(same2)} ===")
    print(f"no-gold  : {acc(ng, same2)}/{len(same2)} = {acc(ng, same2)/len(same2)*100:.2f}%")
    print(f"gold-judge: {acc(gold, same2)}/{len(same2)} = {acc(gold, same2)/len(same2)*100:.2f}%")
    g2 = [i for i in same2 if ng[i]["answer"] != ng[i]["gold_answer"] and gold[i]["answer"] == gold[i]["gold_answer"]]
    l2 = [i for i in same2 if ng[i]["answer"] == ng[i]["gold_answer"] and gold[i]["answer"] != gold[i]["gold_answer"]]
    print(f"gold版相对无gold版: 多对 {len(g2)} 题, 多错 {len(l2)} 题")

    # judge score distribution from run8 log
    log = open(f"{OUT}/goa_run8.log", encoding="utf-8", errors="ignore").read()
    scores = [int(x) for x in re.findall(r"judge_score=(\d)", log)]
    print("\n=== 无gold裁判打分分布（run8, 共%d次）===" % len(scores))
    c = Counter(scores)
    for s in range(1, 6):
        print(f"  {s}分: {c.get(s,0)} ({c.get(s,0)/len(scores)*100:.1f}%)")
    print(f"  平均: {sum(scores)/len(scores):.2f}")


if __name__ == "__main__":
    main()
