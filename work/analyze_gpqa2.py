import json
import re
from collections import Counter

PATH = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/GPQA_test_merged.json"
data = json.load(open(PATH))


def domain(q):
    ql = q.lower()
    chem = ["carbon", "compound", "reaction", "mol", "atom", "acid", "bond", "solution",
            "chloride", "element", "ion", "hydrox", "oxide", "ph ", "synthesis", "alkene",
            "benzene", "hydrogen", "oxygen", "nitrogen", "catalyst", "isomer"]
    phys = ["energy", "field", "electron", "wave", "charge", "mass", "velocity", "force",
            "photon", "quantum", "momentum", "current", "voltage", "wavelength", "spin",
            "magnetic", "electric", "gravitational", "temperature", "entropy"]
    bio = ["cell", "protein", "gene", "dna", "rna", "enzyme", "organism", "membrane",
           "bacteria", "chromosome", "mutation", "amino", "receptor", "neur", "tissue",
           "virus", "ribosome", "metabolism"]
    scores = {"chemistry": sum(1 for w in chem if w in ql),
              "physics": sum(1 for w in phys if w in ql),
              "biology": sum(1 for w in bio if w in ql)}
    return max(scores, key=scores.get) if max(scores.values()) > 0 else "other"


domains = Counter(domain(d["question"]) for d in data)
print("--- Accuracy by rough domain ---")
for dom, cnt in domains.most_common():
    sub = [d for d in data if domain(d["question"]) == dom]
    ok = sum(1 for d in sub if d["answer"] == d["gold_answer"])
    print(f"  {dom}: {cnt} items, acc={ok/cnt*100:.2f}% ({ok}/{cnt})")

print("\n--- Accuracy by gold letter ---")
for g in "ABCD":
    sub = [d for d in data if d["gold_answer"] == g]
    ok = sum(1 for d in sub if d["answer"] == g)
    preds = Counter(d["answer"] for d in sub)
    print(f"  gold={g}: n={len(sub)}, acc={ok/len(sub)*100:.2f}%, predicted dist={dict(preds.most_common())}")

print("\n--- Predicted-vs-gold confusion matrix (rows=gold, cols=pred) ---")
for g in "ABCD":
    row = [sum(1 for d in data if d["gold_answer"] == g and d["answer"] == p) for p in "ABCD|"]
    print(f"  gold {g}: A={row[0]} B={row[1]} C={row[2]} D={row[3]} pipe={row[4]}")

print("\n--- special items ---")
for d in data:
    if d["answer"] == "|":
        print(f"idx={d['idx']} gold={d['gold_answer']} answer={d['answer']}")
        print("QUESTION:", d["question"][:300])
        print("FINAL:", d["final_response"][:600])
        print()
    if d["idx"] in (0, 2):
        print(f"--- idx={d['idx']} gold={d['gold_answer']} answer={d['answer']} nodes={d['sampled_nodes']}")
        print("QUESTION:", d["question"][:300])
        print("FINAL:", d["final_response"][:800])
        print()
