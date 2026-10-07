# -*- coding: utf-8 -*-
"""Compare pairwise_margin_4dim result vs pairwise_margin baseline (both 198 Qs)."""
import json
import sys
from collections import Counter

BASE = "outputs/GPQA_test_merged_6models_judge_nogold_pairwise_margin.json"
NEW = sys.argv[1] if len(sys.argv) > 1 else "outputs/GPQA_test_merged_6models_judge_nogold_pairwise_margin_4dim.json"

base = {int(x["idx"]): x for x in json.load(open(BASE))}
new = {int(x["idx"]): x for x in json.load(open(NEW))}

assert set(base) == set(new), "idx mismatch"

def acc(d):
    return sum(1 for x in d.values() if x["answer"] == x["gold_answer"]), len(d)

b_c, b_n = acc(base)
n_c, n_n = acc(new)
print(f"baseline margin : {b_c}/{b_n} = {b_c/b_n*100:.2f}%")
print(f"4dim margin     : {n_c}/{n_n} = {n_c/n_n*100:.2f}%")

# strict subset: same sampled_nodes
strict = [i for i in base if base[i]["sampled_nodes"] == new[i]["sampled_nodes"]]
sb_c = sum(1 for i in strict if base[i]["answer"] == base[i]["gold_answer"])
sn_c = sum(1 for i in strict if new[i]["answer"] == new[i]["gold_answer"])
print(f"strict subset ({len(strict)}): baseline {sb_c} ({sb_c/len(strict)*100:.2f}%) | 4dim {sn_c} ({sn_c/len(strict)*100:.2f}%)")

flip_ok = [i for i in strict if base[i]["answer"] != base[i]["gold_answer"] and new[i]["answer"] == new[i]["gold_answer"]]
flip_bad = [i for i in strict if base[i]["answer"] == base[i]["gold_answer"] and new[i]["answer"] != new[i]["gold_answer"]]
print(f"flips in strict: turn-good {len(flip_ok)} {sorted(flip_ok)} | turn-bad {len(flip_bad)} {sorted(flip_bad)}")

# three classic bad cases
for i in (1, 10, 27):
    if i in base and i in new:
        print(f"idx {i}: gold={base[i]['gold_answer']} | base={base[i]['answer']} | 4dim={new[i]['answer']}")

# answer distribution
print("base dist:", Counter(x["answer"] for x in base.values()))
print("4dim dist:", Counter(x["answer"] for x in new.values()))

# save strict flip lists for later detail
json.dump({"turn_good": flip_ok, "turn_bad": flip_bad},
          open("outputs/4dim_strict_flips.json", "w"), ensure_ascii=False, indent=1)
print("saved outputs/4dim_strict_flips.json")
