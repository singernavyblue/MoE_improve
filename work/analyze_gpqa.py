import json
import re
from collections import Counter

PATH = "/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/GPQA_test_merged.json"

data = json.load(open(PATH))
N = len(data)


def conf_of(item):
    m = re.findall(r'"confidence_level"\s*:\s*([0-9.]+)', item.get("final_response", ""))
    if not m:
        m = re.findall(r'confidence[_ ]*level.{0,20}?([0-9.]+)', item.get("final_response", ""))
    return float(m[-1]) if m else None


correct = [d for d in data if d["answer"] == d["gold_answer"]]
wrong = [d for d in data if d["answer"] != d["gold_answer"]]

print(f"TOTAL: {N}  correct: {len(correct)} ({len(correct)/N*100:.2f}%)  wrong: {len(wrong)} ({len(wrong)/N*100:.2f}%)")

na = [d for d in data if d["answer"] == "N/A"]
print(f"\nParse failures (answer == N/A): {len(na)} ({len(na)/N*100:.2f}%)")
print(f"  of which actually-correct-reasoning impossible to tell; gold dist: {Counter(d['gold_answer'] for d in na)}")

print("\n--- Predicted letter distribution (all, incl N/A) ---")
print(Counter(d["answer"] for d in data).most_common())
print("\n--- Gold letter distribution ---")
print(Counter(d["gold_answer"] for d in data).most_common())

print("\n--- Accuracy by graph size (len(sampled_nodes)) ---")
for n in sorted(set(len(d["sampled_nodes"]) for d in data)):
    sub = [d for d in data if len(d["sampled_nodes"]) == n]
    ok = sum(1 for d in sub if d["answer"] == d["gold_answer"])
    print(f"  sampled_nodes={n}: {len(sub)} items, acc={ok/len(sub)*100:.2f}% ({ok}/{len(sub)})")

print("\n--- Accuracy by node combo ---")
combos = Counter(tuple(sorted(d["sampled_nodes"])) for d in data)
for c, cnt in combos.most_common():
    sub = [d for d in data if tuple(sorted(d["sampled_nodes"])) == c]
    ok = sum(1 for d in sub if d["answer"] == d["gold_answer"])
    print(f"  {c}: {cnt} items, acc={ok/cnt*100:.2f}% ({ok}/{cnt})")

print("\n--- Confidence stats (parsed from final_response) ---")
conf_c = [conf_of(d) for d in correct]
conf_w = [conf_of(d) for d in wrong]
conf_c = [c for c in conf_c if c is not None]
conf_w = [c for c in conf_w if c is not None]
print(f"  correct: n={len(conf_c)} mean={sum(conf_c)/len(conf_c):.3f}" if conf_c else "  correct: none")
print(f"  wrong:   n={len(conf_w)} mean={sum(conf_w)/len(conf_w):.3f}" if conf_w else "  wrong: none")
missing = sum(1 for d in data if conf_of(d) is None)
print(f"  missing confidence: {missing}")

print("\n--- final_response length (chars) ---")
len_c = [len(d["final_response"]) for d in correct]
len_w = [len(d["final_response"]) for d in wrong]
print(f"  correct mean={sum(len_c)/len(len_c):.0f}  wrong mean={sum(len_w)/len(len_w):.0f}")

print("\n--- Wrong cases: answer=N/A vs letter ---")
w_na = [d for d in wrong if d["answer"] == "N/A"]
w_letter = [d for d in wrong if d["answer"] != "N/A"]
print(f"  wrong&N/A: {len(w_na)}, wrong&letter: {len(w_letter)}")

# Dump typical bad cases to a file for review
out_lines = []


def dump(item, tag):
    out_lines.append("=" * 90)
    out_lines.append(f"[{tag}] idx={item['idx']}  gold={item['gold_answer']}  predicted={item['answer']}  nodes={item['sampled_nodes']}")
    out_lines.append(f"QUESTION: {item['question']}")
    fr = item["final_response"]
    out_lines.append(f"FINAL_RESPONSE ({len(fr)} chars): {fr[:1500]}")
    out_lines.append("")


# 1. a parse-failure bad case
if w_na:
    dump(w_na[0], "BAD1-parse-failure")
# 2. a two-node high-confidence wrong case
two_conf_wrong = [d for d in w_letter if len(d["sampled_nodes"]) == 2 and conf_of(d) is not None and conf_of(d) >= 0.9]
if two_conf_wrong:
    dump(two_conf_wrong[0], "BAD2-two-node-confident-wrong")
# 3. single-node wrong, short reasoning
single_wrong = [d for d in w_letter if len(d["sampled_nodes"]) == 1]
if single_wrong:
    dump(single_wrong[0], "BAD3-single-node-wrong")
# 4. wrong where answer letter appears in reasoning (possible extraction issue)
letter_wrong = []
for d in w_letter:
    fr = d["final_response"]
    if re.search(rf"\([{d['answer']}]\)", fr) and d["gold_answer"] in fr:
        letter_wrong.append(d)
if letter_wrong:
    dump(letter_wrong[0], "BAD4-answer-in-response")
# 5. N/A case with verbose response
if len(w_na) > 1:
    dump(w_na[1], "BAD5-parse-failure-2")

out = "\n".join(out_lines)
open("/Users/Zhuanz/Documents/Codex/2026-08-02/xia/outputs/gpqa_bad_cases_sample.txt", "w").write(out)
print("\nSample bad cases written to outputs/gpqa_bad_cases_sample.txt")
