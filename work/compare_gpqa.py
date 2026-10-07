import json
from collections import Counter

A = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/GPQA_test_merged.json"        # 2 models
B = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/GPQA_test_merged_6models.json"  # 6 models

d2 = json.load(open(A))
d6 = json.load(open(B))

assert len(d2) == len(d6) == 198


def ok(d):
    return d["answer"] == d["gold_answer"]


ok2 = [i for i, d in enumerate(d2) if ok(d)]
ok6 = [i for i, d in enumerate(d6) if ok(d)]

print(f"2-model: {len(ok2)} correct ({len(ok2)/198*100:.2f}%)")
print(f"6-model: {len(ok6)} correct ({len(ok6)/198*100:.2f}%)")

both_right = set(ok2) & set(ok6)
both_wrong = set(range(198)) - set(ok2) - set(ok6)
only2 = set(ok2) - set(ok6)
only6 = set(ok6) - set(ok2)

print(f"both right: {len(both_right)}  both wrong: {len(both_wrong)}")
print(f"only 2-model right (6-model regressed): {len(only2)}")
print(f"only 6-model right (2-model regressed): {len(only6)}")

# per-batch comparison
print("\n--- Per-batch (chunks of 50/50/50/48) ---")
starts = [0, 50, 100, 150]
names = ["batch1", "batch2", "batch3", "batch4"]
for name, s in zip(names, starts):
    e = s + (50 if name != "batch4" else 48)
    a = sum(1 for i in range(s, e) if ok(d2[i]))
    b = sum(1 for i in range(s, e) if ok(d6[i]))
    print(f"{name}: 2-model={a} ({a/(e-s)*100:.2f}%)  6-model={b} ({b/(e-s)*100:.2f}%)")

# answer change stats
changed = [i for i in range(198) if d2[i]["answer"] != d6[i]["answer"]]
same = 198 - len(changed)
print(f"\nanswers identical between runs: {same}/198 ({same/198*100:.1f}%)")
print(f"answers changed: {len(changed)}/198 ({len(changed)/198*100:.1f}%)")

# sampled node counts in 6-model run
print("\n--- sampled_nodes size distribution (6-model) ---")
print(Counter(len(d["sampled_nodes"]) for d in d6).most_common())

# top node combos in 6-model run
combos = Counter(tuple(sorted(d["sampled_nodes"])) for d in d6)
print("\n--- node combos (6-model), top 8 ---")
for c, n in combos.most_common(8):
    okc = sum(1 for i, d in enumerate(d6) if tuple(sorted(d["sampled_nodes"])) == c and ok(d))
    print(f"  {c}: {n} items, acc={okc/n*100:.1f}%")

# dump a few items where 6-model is right and 2-model wrong, and vice versa
out = []
for tag, idxs in [("6-RIGHT-2-WRONG", sorted(only6)[:2]), ("2-RIGHT-6-WRONG", sorted(only2)[:2])]:
    for i in idxs:
        d6i, d2i = d6[i], d2[i]
        out.append("=" * 90)
        out.append(f"[{tag}] idx={i}  gold={d6i['gold_answer']}  "
                   f"2m_pred={d2i['answer']} nodes={d2i['sampled_nodes']} | "
                   f"6m_pred={d6i['answer']} nodes={d6i['sampled_nodes']}")
        out.append("QUESTION: " + d6i["question"][:400])
        out.append("6m FINAL: " + d6i["final_response"][:500])
        out.append("")

open("/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/gpqa_6v2_comparison.txt", "w").write("\n".join(out))
print("\ncomparison samples written.")
