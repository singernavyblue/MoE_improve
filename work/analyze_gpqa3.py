import json
import re
from collections import Counter

PATH = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/GPQA_test_merged.json"
data = json.load(open(PATH))

wrong = [d for d in data if d["answer"] != d["gold_answer"]]

# wrong predicted letter distribution
print("--- Wrong-case predicted letters ---")
print(Counter(d["answer"] for d in wrong).most_common())

# how many wrong cases mention the gold letter somewhere in final response
mention_gold = 0
for d in wrong:
    if re.search(rf"\(\s*{re.escape(d['gold_answer'])}\s*\)", d["final_response"]) or \
       re.search(rf"\banswer is {re.escape(d['gold_answer'])}\b", d["final_response"], re.I) or \
       re.search(rf"\b{re.escape(d['gold_answer'])}\b\)", d["final_response"]):
        mention_gold += 1
print(f"\nWrong cases that mention the GOLD letter somewhere in final_response: {mention_gold}/{len(wrong)} "
      f"({mention_gold/len(wrong)*100:.1f}%)")

# how many wrong cases contain BOTH the predicted and gold letters
both = 0
for d in wrong:
    fr = d["final_response"]
    if d["gold_answer"] in fr and d["answer"] in fr:
        both += 1
print(f"Wrong cases containing both gold and predicted letters in text: {both}/{len(wrong)} ({both/len(wrong)*100:.1f}%)")

# dump one wrong physics and one wrong biology case
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


out = []
for tag, dom in [("PHYSICS-WRONG", "physics"), ("BIOLOGY-WRONG", "biology")]:
    sub = [d for d in wrong if domain(d["question"]) == dom and d["answer"] != "|"]
    if sub:
        d = sub[0]
        out.append("=" * 90)
        out.append(f"[{tag}] gold={d['gold_answer']} predicted={d['answer']} nodes={d['sampled_nodes']}")
        out.append("QUESTION: " + d["question"][:700])
        out.append("FINAL: " + d["final_response"][:1200])
        out.append("")

text = "\n".join(out)
open("/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/gpqa_extra_bad_cases.txt", "w").write(text)
print("\nextra bad cases written.")
