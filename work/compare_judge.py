#!/usr/bin/env python3
"""Compare the original 6-model run vs the judge-edge-sampling run."""
import json
from collections import Counter

ORIG = "outputs/GPQA_test_orig_baseline.json"
JUDGE = "outputs/GPQA_test_merged_6models_judge.json"


def load(p):
    rows = json.load(open(p))
    by_idx = {}
    for r in rows:
        by_idx[r["idx"]] = r
    return by_idx


def main():
    orig = load(ORIG)
    judge = load(JUDGE)
    print(f"orig={len(orig)} judge={len(judge)}")

    acc_o = sum(1 for i in orig if orig[i]["answer"] == orig[i]["gold_answer"])
    acc_j = sum(1 for i in judge if judge[i]["answer"] == judge[i]["gold_answer"])
    print(f"orig acc: {acc_o}/198 = {acc_o/198*100:.2f}%")
    print(f"judge acc: {acc_j}/198 = {acc_j/198*100:.2f}%")

    # control check: sampled nodes
    same_nodes = 0
    diff_nodes = []
    for i in orig:
        if i in judge:
            no = sorted(orig[i].get("sampled_nodes", []))
            nj = sorted(judge[i].get("sampled_nodes", []))
            if no == nj:
                same_nodes += 1
            else:
                diff_nodes.append((i, no, nj))
    print(f"sampled_nodes identical: {same_nodes}/198; diff: {len(diff_nodes)}")
    for d in diff_nodes[:5]:
        print("  node diff:", d)

    gained = []   # judge correct, orig wrong
    lost = []     # judge wrong, orig correct
    both_wrong = []
    both_right = []
    for i in orig:
        o = orig[i]["answer"] == orig[i]["gold_answer"]
        j = judge[i]["answer"] == judge[i]["gold_answer"]
        if o and not j:
            lost.append(i)
        elif j and not o:
            gained.append(i)
        elif o and j:
            both_right.append(i)
        else:
            both_wrong.append(i)

    print(f"\ngained (wrong->right): {len(gained)} {gained}")
    print(f"lost (right->wrong): {len(lost)} {lost}")
    print(f"both right: {len(both_right)}")
    print(f"both wrong: {len(both_wrong)}")

    # judge answer changes summary
    changed = 0
    for i in orig:
        if orig[i]["answer"] != judge[i]["answer"]:
            changed += 1
    print(f"\nanswers changed between runs: {changed}")

    # save gained/lost details
    out = []
    for i in gained + lost:
        o = orig[i]
        j = judge[i]
        out.append({
            "idx": i,
            "question": o["question"][:300],
            "gold": o["gold_answer"],
            "orig_answer": o["answer"],
            "judge_answer": j["answer"],
            "orig_final": o.get("final_response", "")[:200],
            "judge_final": j.get("final_response", "")[:200],
            "nodes": o.get("sampled_nodes", []),
        })
    with open("outputs/judge_flip_details.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("saved outputs/judge_flip_details.json")

    # judge fallback check
    empty = sum(1 for i in judge if not judge[i].get("final_response", ""))
    print(f"judge rows with empty final_response: {empty}")

    # ---- strict control: only questions with identical sampled nodes ----
    same = [
        i for i in orig
        if i in judge
        and sorted(orig[i].get("sampled_nodes", [])) == sorted(judge[i].get("sampled_nodes", []))
    ]
    print(f"\n=== STRICT CONTROL (identical nodes): {len(same)} questions ===")
    acc_o_s = sum(1 for i in same if orig[i]["answer"] == orig[i]["gold_answer"])
    acc_j_s = sum(1 for i in same if judge[i]["answer"] == judge[i]["gold_answer"])
    print(f"orig acc: {acc_o_s}/{len(same)} = {acc_o_s/len(same)*100:.2f}%")
    print(f"judge acc: {acc_j_s}/{len(same)} = {acc_j_s/len(same)*100:.2f}%")
    g_s = [
        i for i in same
        if orig[i]["answer"] != orig[i]["gold_answer"] and judge[i]["answer"] == judge[i]["gold_answer"]
    ]
    l_s = [
        i for i in same
        if orig[i]["answer"] == orig[i]["gold_answer"] and judge[i]["answer"] != judge[i]["gold_answer"]
    ]
    print(f"gained: {len(g_s)} {g_s}")
    print(f"lost: {len(l_s)} {l_s}")

    out2 = []
    for i in g_s + l_s:
        o = orig[i]
        j = judge[i]
        out2.append({
            "idx": i,
            "question": o["question"][:400],
            "gold": o["gold_answer"],
            "orig_answer": o["answer"],
            "judge_answer": j["answer"],
            "nodes": [str(x) for x in o.get("sampled_nodes", [])],
            "orig_final": o.get("final_response", "")[:300],
            "judge_final": j.get("final_response", "")[:300],
        })
    with open("outputs/judge_strict_flips.json", "w") as f:
        json.dump(out2, f, ensure_ascii=False, indent=2)
    print("saved outputs/judge_strict_flips.json")


if __name__ == "__main__":
    main()
