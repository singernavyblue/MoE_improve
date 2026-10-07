# -*- coding: utf-8 -*-
"""Sample 40 GPQA questions for the judge-ablation comparison (7B vs strong LLM)."""
import json
import re
import random

random.seed(42)

base = {int(x["idx"]): x for x in json.load(open("outputs/GPQA_test_merged_6models_judge_nogold_pairwise_margin.json"))}
new = {int(x["idx"]): x for x in json.load(open("outputs/GPQA_test_merged_6models_judge_nogold_pairwise_margin_4dim.json"))}
flips = json.load(open("outputs/4dim_strict_flips.json"))

def domain(q):
    low = q.lower()
    if re.search(r"\b(carbon|bond|molecule|aldehyde|ketone|acid|alkyl|methyl|phenyl|synthesis|isomer|reaction|reagent|enantiomer|stereo|hydroxyl|aromatic|nucleophile|oxidation|reduction|ether|amine|brom|chlor|fluor|iod|naphth|cyclo|nmr|ir\b)", low):
        return "chem"
    if re.search(r"\b(quantum|electron|photon|wave|spin|energy|hamilton|schr|planck|atom|nucleus|particle|field|charge|magnetic|circuit|velocity|force|mass|star|planet|galax|cosm|gravit|relativ)", low):
        return "phys"
    if re.search(r"\b(dna|rna|protein|gene|cell|virus|bacteri|amino|enzyme|chromosome|nucleot|transcription|translation|metabol|peptide)", low):
        return "bio"
    return "other"

must = [1, 10, 27, 61]
turn_good = flips["turn_good"]
turn_bad = flips["turn_bad"]

# candidates: prioritize flips, then balanced by domain and by base correctness
cand = [i for i in base if i not in must]
by_dom = {"chem": [], "phys": [], "bio": [], "other": []}
for i in cand:
    by_dom[domain(base[i]["question"])].append(i)

chosen = list(must)
chosen += [i for i in turn_good if i not in chosen][:6]
chosen += [i for i in turn_bad if i not in chosen][:8]

def fill(pool, n, chosen_set):
    random.shuffle(pool)
    out = []
    for i in pool:
        if len(out) >= n:
            break
        if i not in chosen_set:
            out.append(i)
            chosen_set.add(i)
    return out

chosen_set = set(chosen)
# domain balance target: chem 18, phys 12, bio 4, other 6 (of remaining)
for dom, n in (("chem", 18), ("phys", 12), ("bio", 4), ("other", 6)):
    cur = sum(1 for i in chosen if domain(base[i]["question"]) == dom)
    if cur < n:
        chosen += fill(by_dom[dom], n - cur, chosen_set)

# if still short, top up anywhere
if len(chosen) < 40:
    chosen += fill([i for i in cand], 40 - len(chosen), chosen_set)

chosen = sorted(chosen[:40])
print("n =", len(chosen))
from collections import Counter
print("domain:", Counter(domain(base[i]["question"]) for i in chosen))
print("base correct:", sum(1 for i in chosen if base[i]["answer"] == base[i]["gold_answer"]))
print("4dim correct:", sum(1 for i in chosen if new[i]["answer"] == new[i]["gold_answer"]))
print("in turn_good:", len(set(chosen) & set(turn_good)))
print("in turn_bad:", len(set(chosen) & set(turn_bad)))
print("idxs:", chosen)
json.dump(chosen, open("outputs/judge_ablation_40_idxs.json", "w"), indent=1)
print("saved outputs/judge_ablation_40_idxs.json")
